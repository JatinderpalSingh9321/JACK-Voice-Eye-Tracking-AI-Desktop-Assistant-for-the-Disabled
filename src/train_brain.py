"""
BCI Assistive Control — Advanced 4-Class MI Training Pipeline
=============================================================
Maximizes accuracy for 4-class motor imagery from single C3 referential.

Strategy:
  1. 80+ features (band power, ratios, ERD/ERS, Hjorth, wavelets, entropy)
  2. 5x data augmentation (noise, shift, scale, flip, mixup)
  3. Ensemble voting (SVM + RandomForest + GradientBoosting)
  4. Exhaustive grid search
  5. Feature selection via mutual information

Usage:
  python -m src.train_brain --simulate --trials 50
  python -m src.train_brain --subject 1 --session 1
  python -m src.train_brain --subject 1 --grid-search

Group No. 7 | 8th Semester Major Project
"""

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
from scipy import signal as sig
from scipy.stats import kurtosis, skew, entropy as sp_entropy
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.ensemble import (
    RandomForestClassifier, GradientBoostingClassifier,
    VotingClassifier, BaggingClassifier
)
from sklearn.pipeline import Pipeline
from sklearn.model_selection import (
    StratifiedKFold, cross_val_score, GridSearchCV,
    RepeatedStratifiedKFold
)
from sklearn.metrics import (
    classification_report, confusion_matrix, accuracy_score
)
from sklearn.feature_selection import SelectKBest, mutual_info_classif

from src.utils import SAMPLING_RATE, RAW_DATA_DIR, MODELS_DIR, RESULTS_DIR, setup_logger

logger = setup_logger("train_brain")

MI_NAMES = ["LEFT", "RIGHT", "UP", "DOWN"]

BANDS = {
    "delta":      (0.5, 4),
    "theta":      (4, 8),
    "low_alpha":  (8, 10),
    "high_alpha": (10, 12),
    "low_beta":   (12, 20),
    "high_beta":  (20, 30),
    "low_gamma":  (30, 40),
    "high_gamma": (40, 50),
}


# ──────────────────────────────────────────────
# SIGNAL PROCESSING
# ──────────────────────────────────────────────

def bandpass(data, lo, hi, fs=SAMPLING_RATE, order=4):
    nyq = fs / 2
    lo_n = max(lo / nyq, 0.001)
    hi_n = min(hi / nyq, 0.999)
    if lo_n >= hi_n:
        return data
    b, a = sig.butter(order, [lo_n, hi_n], btype='band')
    return sig.filtfilt(b, a, data)


def preprocess(x, fs=SAMPLING_RATE):
    """Clean a raw epoch: remove DC, notch 50Hz, bandpass 0.5-50Hz."""
    x = x.copy().astype(np.float64)
    x -= np.mean(x)
    # Notch 50 Hz
    b, a = sig.iirnotch(50.0, 30.0, fs)
    x = sig.filtfilt(b, a, x)
    # Bandpass 0.5-50 Hz
    x = bandpass(x, 0.5, 50, fs)
    return x


# ──────────────────────────────────────────────
# FEATURE EXTRACTION (80+ features)
# ──────────────────────────────────────────────

def extract_features(epoch_1d, fs=SAMPLING_RATE):
    """Extract comprehensive features from single C3 referential epoch."""
    x = preprocess(epoch_1d, fs)
    features = []

    # === 1. Band Power (8 bands × 2 = 16 features) ===
    freqs, psd = sig.welch(x, fs=fs, nperseg=min(256, len(x)))
    total_power = np.sum(psd) + 1e-10

    powers = {}
    for bname, (flo, fhi) in BANDS.items():
        mask = (freqs >= flo) & (freqs <= fhi)
        bp = np.mean(psd[mask]) if np.any(mask) else 0.0
        powers[bname] = bp + 1e-10
        features.append(bp)                    # Absolute
        features.append(bp / total_power)      # Relative

    # === 2. Band Ratios (10 features) ===
    alpha_total = powers["low_alpha"] + powers["high_alpha"]
    beta_total = powers["low_beta"] + powers["high_beta"]
    features.append(powers["theta"] / alpha_total)           # Theta/Alpha
    features.append(beta_total / alpha_total)                 # Beta/Alpha
    features.append(powers["high_beta"] / powers["low_beta"]) # HiBeta/LoBeta
    features.append(powers["theta"] / powers["low_beta"])     # Theta/Beta
    features.append(powers["delta"] / alpha_total)            # Delta/Alpha
    features.append(powers["low_gamma"] / beta_total)         # Gamma/Beta
    features.append(alpha_total / total_power)                # Alpha dominance
    features.append(beta_total / total_power)                 # Beta dominance
    features.append(powers["theta"] / total_power)            # Theta dominance
    features.append(powers["delta"] / total_power)            # Delta dominance

    # === 3. Peak Frequencies (3 features) ===
    for band_lo, band_hi in [(8, 12), (12, 30), (4, 8)]:
        mask = (freqs >= band_lo) & (freqs <= band_hi)
        if np.any(mask) and np.sum(psd[mask]) > 0:
            features.append(np.average(freqs[mask], weights=psd[mask]))
        else:
            features.append((band_lo + band_hi) / 2)

    # === 4. Temporal Statistics (10 features) ===
    features.append(np.var(x))
    features.append(np.std(x))
    features.append(kurtosis(x))
    features.append(skew(x))
    features.append(np.sqrt(np.mean(x**2)))              # RMS
    features.append(np.max(np.abs(x)))                    # Peak
    features.append(np.sum(np.abs(np.diff(x))))           # Line length
    features.append(np.sum(np.diff(np.sign(x)) != 0))    # Zero crossings
    features.append(np.percentile(np.abs(x), 75))        # P75
    features.append(np.median(np.abs(x)))                 # MAD

    # === 5. Hjorth Parameters (3 features) ===
    dx = np.diff(x)
    ddx = np.diff(dx)
    var_x = np.var(x) + 1e-10
    var_dx = np.var(dx) + 1e-10
    var_ddx = np.var(ddx) + 1e-10
    mobility = np.sqrt(var_dx / var_x)
    complexity = np.sqrt(var_ddx / var_dx) / (mobility + 1e-10)
    features.extend([var_x, mobility, complexity])

    # === 6. Sub-band Energies per Quarter (8×4 = 32 features) ===
    quarter = len(x) // 4
    for q in range(4):
        seg = x[q * quarter : (q + 1) * quarter]
        if len(seg) > 20:
            for bname in ["low_alpha", "high_alpha", "low_beta", "high_beta",
                          "theta", "delta", "low_gamma", "high_gamma"]:
                flo, fhi = BANDS[bname]
                try:
                    filtered = bandpass(seg, flo, fhi, fs)
                    features.append(np.var(filtered))
                except Exception:
                    features.append(0.0)
        else:
            features.extend([0.0] * 8)

    # === 7. ERD/ERS (6 features) ===
    mid = len(x) // 2
    if mid > 20:
        for bname in ["low_alpha", "high_alpha", "low_beta",
                       "high_beta", "theta", "delta"]:
            flo, fhi = BANDS[bname]
            try:
                first_half = bandpass(x[:mid], flo, fhi, fs)
                second_half = bandpass(x[mid:], flo, fhi, fs)
                erd = (np.var(second_half) - np.var(first_half)) / (np.var(first_half) + 1e-10)
                features.append(erd)
            except Exception:
                features.append(0.0)
    else:
        features.extend([0.0] * 6)

    # === 8. Spectral Entropy (1 feature) ===
    psd_norm = psd / (np.sum(psd) + 1e-10)
    psd_pos = psd_norm[psd_norm > 0]
    features.append(sp_entropy(psd_pos) if len(psd_pos) > 0 else 0.0)

    # === 9. Wavelet Energy (4 features) ===
    try:
        from scipy.signal import cwt, morlet2
        widths = np.arange(1, 31)
        cwtm = cwt(x[:min(500, len(x))], morlet2, widths)
        for w_idx in [4, 9, 14, 24]:
            if w_idx < len(cwtm):
                features.append(np.mean(np.abs(cwtm[w_idx]) ** 2))
            else:
                features.append(0.0)
    except Exception:
        features.extend([0.0] * 4)

    return np.array(features, dtype=np.float32)


# ──────────────────────────────────────────────
# DATA AUGMENTATION
# ──────────────────────────────────────────────

def augment_epoch(epoch, fs=SAMPLING_RATE, n_augments=5):
    """Generate augmented versions of an epoch."""
    augmented = []
    for i in range(n_augments):
        x = epoch.copy()
        r = np.random.rand()
        if r < 0.25:
            # Add Gaussian noise
            x += np.random.randn(len(x)) * np.std(x) * 0.08
        elif r < 0.50:
            # Time shift
            shift = np.random.randint(-20, 20)
            x = np.roll(x, shift)
        elif r < 0.75:
            # Amplitude scaling
            x *= (0.8 + 0.4 * np.random.rand())
        else:
            # Smooth jitter (slow baseline drift)
            t = np.linspace(0, 2 * np.pi, len(x))
            drift = np.sin(t * np.random.uniform(0.5, 2)) * np.std(x) * 0.1
            x += drift
        augmented.append(x.astype(np.float32))
    return augmented


# ──────────────────────────────────────────────
# DATA LOADING
# ──────────────────────────────────────────────

def load_data(subject_id, session_id=1, block="mi"):
    path = RAW_DATA_DIR / f"subject_{subject_id:03d}" / f"session_{session_id:02d}_ref_{block}.npz"
    if not path.exists():
        logger.error(f"Not found: {path}")
        return None, None
    loaded = np.load(path, allow_pickle=True)
    return loaded["data"], loaded["labels"]


def generate_simulated(n_per_class=50):
    from src.experiment_referential import simulate_referential_epoch
    all_data, all_labels = [], []
    n_samples = int(4.0 * SAMPLING_RATE)

    for cid in range(4):
        for _ in range(n_per_class):
            epoch = simulate_referential_epoch(cid, n_samples)
            # Add subject variability
            epoch += np.random.randn() * np.random.uniform(0.5, 2.0)
            epoch *= np.random.uniform(0.7, 1.3)
            all_data.append(epoch)
            all_labels.append(cid)

    return np.array(all_data, dtype=object), np.array(all_labels, dtype=np.int32)


# ──────────────────────────────────────────────
# TRAINING
# ──────────────────────────────────────────────

def train(data, labels, do_grid_search=False, augment=True):
    logger.info("=" * 60)
    logger.info("  ADVANCED 4-CLASS MI TRAINING (C3 Referential)")
    logger.info("=" * 60)

    # Filter MI classes only
    mi_mask = labels < 4
    data = data[mi_mask]
    labels = labels[mi_mask]

    for cid in range(4):
        logger.info(f"  {MI_NAMES[cid]:6s}: {np.sum(labels == cid)} trials")

    # Data augmentation
    if augment:
        logger.info("  Augmenting data (5x)...")
        aug_data, aug_labels = [], []
        for epoch, label in zip(data, labels):
            arr = np.array(epoch, dtype=np.float32)
            aug_data.append(arr)
            aug_labels.append(label)
            for aug_epoch in augment_epoch(arr):
                aug_data.append(aug_epoch)
                aug_labels.append(label)
        data = np.array(aug_data, dtype=object)
        labels = np.array(aug_labels, dtype=np.int32)
        logger.info(f"  After augmentation: {len(data)} total trials")

    # Extract features
    logger.info("  Extracting features...")
    X, valid = [], []
    for i, epoch in enumerate(data):
        try:
            arr = np.array(epoch, dtype=np.float32)
            if len(arr) < 100:
                continue
            feats = extract_features(arr)
            if np.all(np.isfinite(feats)):
                X.append(feats)
                valid.append(i)
        except Exception as e:
            if i < 5:
                logger.warning(f"  Trial {i} failed: {e}")

    X = np.array(X, dtype=np.float32)
    y = labels[valid]
    logger.info(f"  Features shape: {X.shape} ({X.shape[1]} per trial)")

    # Build ensemble
    logger.info("  Building ensemble classifier...")

    svm = SVC(C=50, gamma='scale', kernel='rbf', probability=True, random_state=42)
    rf = RandomForestClassifier(
        n_estimators=300, max_depth=15, min_samples_split=3,
        random_state=42, n_jobs=-1
    )
    gbm = GradientBoostingClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.1,
        subsample=0.8, random_state=42
    )

    if do_grid_search:
        logger.info("  Running GridSearchCV on SVM...")
        svm_pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("select", SelectKBest(mutual_info_classif, k="all")),
            ("svm", SVC(probability=True, random_state=42)),
        ])
        grid_params = {
            "select__k": [30, 50, "all"],
            "svm__C": [1, 10, 50, 100],
            "svm__gamma": ["scale", "auto", 0.01],
            "svm__kernel": ["rbf"],
        }
        n_splits = min(5, min(np.bincount(y)))
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        grid = GridSearchCV(svm_pipe, grid_params, cv=cv, scoring="accuracy",
                           n_jobs=-1, verbose=0)
        grid.fit(X, y)
        best_svm = grid.best_estimator_
        logger.info(f"  Best SVM params: {grid.best_params_}")
        logger.info(f"  Best SVM CV: {grid.best_score_:.4f}")
    else:
        best_svm = Pipeline([
            ("scaler", StandardScaler()),
            ("select", SelectKBest(mutual_info_classif, k=min(50, X.shape[1]))),
            ("svm", svm),
        ])

    # Ensemble
    ensemble = VotingClassifier(
        estimators=[
            ("svm", best_svm),
            ("rf", Pipeline([("scaler", StandardScaler()), ("rf", rf)])),
            ("gbm", Pipeline([("scaler", StandardScaler()), ("gbm", gbm)])),
        ],
        voting="soft",
        weights=[3, 2, 2],  # SVM gets more weight
    )

    logger.info("  Training ensemble...")
    ensemble.fit(X, y)

    # Evaluate
    n_splits = min(5, min(np.bincount(y)))
    cv = RepeatedStratifiedKFold(n_splits=n_splits, n_repeats=3, random_state=42)
    cv_scores = cross_val_score(ensemble, X, y, cv=cv, scoring="accuracy")

    y_pred = ensemble.predict(X)
    train_acc = accuracy_score(y, y_pred)

    logger.info(f"\n  Training accuracy:  {train_acc:.4f}")
    logger.info(f"  CV accuracy:        {np.mean(cv_scores):.4f} ± {np.std(cv_scores):.4f}")
    logger.info(f"\n{classification_report(y, y_pred, target_names=MI_NAMES)}")

    cm = confusion_matrix(y, y_pred)
    logger.info("  Confusion Matrix:")
    logger.info(f"  {MI_NAMES}")
    for i, row in enumerate(cm):
        logger.info(f"  {MI_NAMES[i]:6s} {row}")

    # Save model
    model_path = MODELS_DIR / "brain_mi_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": ensemble,
            "class_names": MI_NAMES,
            "n_features": X.shape[1],
            "train_accuracy": float(train_acc),
            "cv_accuracy": float(np.mean(cv_scores)),
            "cv_std": float(np.std(cv_scores)),
            "montage": "referential (C3 to earlobe)",
            "augmented": augment,
        }, f)
    logger.info(f"  ✓ Model saved: {model_path}")

    return {
        "model": ensemble,
        "accuracy": train_acc,
        "cv_accuracy": float(np.mean(cv_scores)),
        "cv_std": float(np.std(cv_scores)),
        "confusion_matrix": cm.tolist(),
        "report": classification_report(y, y_pred, target_names=MI_NAMES, output_dict=True),
    }


def main():
    parser = argparse.ArgumentParser(description="Advanced 4-Class MI Training")
    parser.add_argument("--subject", type=int, help="Subject ID")
    parser.add_argument("--session", type=int, default=1)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--grid-search", action="store_true")
    parser.add_argument("--no-augment", action="store_true")
    parser.add_argument("--trials", type=int, default=50,
                        help="Simulated trials per class")
    args = parser.parse_args()

    from src.utils import print_banner
    print_banner()
    print("  >> ADVANCED 4-CLASS MI TRAINING (Brain Mouse)\n")

    if args.simulate:
        logger.info("Generating simulated referential data...")
        data, labels = generate_simulated(n_per_class=args.trials)
    else:
        if not args.subject:
            logger.error("Need --subject or --simulate")
            return
        data, labels = load_data(args.subject, args.session)
        if data is None:
            return

    results = train(data, labels,
                    do_grid_search=args.grid_search,
                    augment=not args.no_augment)

    print("\n" + "=" * 60)
    print("  RESULT")
    print("=" * 60)
    print(f"  4-class MI (C3): "
          f"{results['accuracy']:.1%} train, "
          f"{results['cv_accuracy']:.1%} ± {results['cv_std']:.1%} CV")
    print(f"  Model: {MODELS_DIR / 'brain_mi_model.pkl'}")
    print("=" * 60)

    out = {k: v for k, v in results.items() if k != "model"}
    with open(RESULTS_DIR / "brain_mi_results.json", "w") as f:
        json.dump(out, f, indent=2, default=str)


if __name__ == "__main__":
    main()
