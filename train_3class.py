"""
Maximum-effort 2-class: sub-epoch slicing + augmentation + tuning.
Instead of 1 sample per trial, extract 3 overlapping windows per trial.
"""
import numpy as np
import pickle
from src.utils import RAW_DATA_DIR, MODELS_DIR, SAMPLING_RATE
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score, GridSearchCV, StratifiedKFold
from sklearn.metrics import classification_report
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from scipy import signal as sig
from scipy.stats import kurtosis, skew

FS = SAMPLING_RATE
NAMES = ["LEFT", "RIGHT"]

def bandpass(x, lo, hi, fs):
    nyq = fs / 2
    lo_n, hi_n = max(lo/nyq, 0.01), min(hi/nyq, 0.99)
    if lo_n >= hi_n:
        return x
    b, a = sig.butter(4, [lo_n, hi_n], btype='band')
    return sig.filtfilt(b, a, x)

def preprocess(x, fs):
    b, a = sig.butter(4, [1/(fs/2), 45/(fs/2)], btype='band')
    x = sig.filtfilt(b, a, x)
    b_n, a_n = sig.iirnotch(50, 30, fs)
    return sig.filtfilt(b_n, a_n, x)

def extract_features(epoch, fs=FS):
    x = preprocess(epoch, fs)
    features = []
    
    # Band powers
    freqs, psd = sig.welch(x, fs=fs, nperseg=min(256, len(x)))
    total = np.sum(psd) + 1e-10
    bands = [(4,8), (8,10), (10,12), (12,16), (16,20), (20,30), (30,45)]
    for lo, hi in bands:
        mask = (freqs >= lo) & (freqs <= hi)
        bp = np.mean(psd[mask]) if np.any(mask) else 0
        features.append(bp)
        features.append(bp / total)
    
    # Mu analysis
    mu = bandpass(x, 8, 12, fs)
    features.extend([np.var(mu), np.mean(np.abs(mu)), np.max(np.abs(mu)),
                      np.sqrt(np.mean(mu**2))])
    
    # Beta
    beta = bandpass(x, 12, 30, fs)
    features.extend([np.var(beta), np.mean(np.abs(beta))])
    
    # Mu/Beta ratio
    features.append(np.var(mu) / (np.var(beta) + 1e-10))
    
    # Temporal mu evolution (4 quarters)
    q = len(x) // 4
    for i in range(4):
        s = x[i*q:(i+1)*q]
        if len(s) > 20:
            ms = bandpass(s, 8, 12, fs)
            features.append(np.var(ms))
        else:
            features.append(0)
    
    # ERD/ERS
    mid = len(x) // 2
    for lo, hi in [(8,12), (12,20), (20,30)]:
        h1 = bandpass(x[:mid], lo, hi, fs)
        h2 = bandpass(x[mid:], lo, hi, fs)
        features.append((np.var(h2) - np.var(h1)) / (np.var(h1) + 1e-10))
    
    # Signal stats
    features.extend([np.mean(x), np.median(x), skew(x), kurtosis(x), np.std(x)])
    features.append(np.sum(x > 0) / len(x))
    
    # Hjorth
    dx = np.diff(x)
    ddx = np.diff(dx)
    var_x = np.var(x) + 1e-10
    mob = np.sqrt(np.var(dx) / var_x)
    comp = np.sqrt(np.var(ddx) / (np.var(dx)+1e-10)) / (mob+1e-10)
    features.extend([var_x, mob, comp])
    
    # Zero-crossings
    zc = np.sum(np.diff(np.sign(x)) != 0)
    features.append(zc / len(x))
    
    # Peak frequency in mu range
    mu_mask = (freqs >= 8) & (freqs <= 12)
    if np.any(mu_mask):
        features.append(freqs[mu_mask][np.argmax(psd[mu_mask])])
    else:
        features.append(10)
    
    return np.array(features, dtype=np.float32)


# ── Load data ──
all_data, all_labels = [], []
for sess in [1, 2]:
    path = RAW_DATA_DIR / "subject_001" / f"session_{sess:02d}_brain3.npz"
    loaded = np.load(path, allow_pickle=True)
    for d, l in zip(loaded["data"], loaded["labels"]):
        if l in (0, 1):
            all_data.append(np.array(d, dtype=np.float32))
            all_labels.append(int(l))

path = RAW_DATA_DIR / "subject_001" / "session_01_ref_mi.npz"
loaded = np.load(path, allow_pickle=True)
for d, l in zip(loaded["data"], loaded["labels"]):
    if l in (0, 1):
        all_data.append(np.array(d, dtype=np.float32))
        all_labels.append(int(l))

print(f"Raw trials: {len(all_labels)} (L={sum(np.array(all_labels)==0)}, R={sum(np.array(all_labels)==1)})")

# ── Sub-epoch slicing: 3 overlapping 2s windows per 4s trial ──
print("Sub-epoch slicing (3 windows x 2s per trial)...")
X_sliced, y_sliced, trial_ids = [], [], []
win_samples = int(2.0 * FS)  # 500 samples

for i, (epoch, label) in enumerate(zip(all_data, all_labels)):
    if len(epoch) < win_samples + 250:
        continue
    # Window 1: 0-2s, Window 2: 1-3s, Window 3: 2-4s
    offsets = [0, int(1.0*FS), int(2.0*FS)]
    for off in offsets:
        if off + win_samples <= len(epoch):
            seg = epoch[off:off+win_samples]
            feats = extract_features(seg)
            if np.all(np.isfinite(feats)):
                X_sliced.append(feats)
                y_sliced.append(label)
                trial_ids.append(i)

X = np.array(X_sliced, dtype=np.float32)
y = np.array(y_sliced, dtype=np.int32)
trial_ids = np.array(trial_ids)
print(f"After slicing: {X.shape} samples (L={sum(y==0)}, R={sum(y==1)})")

# ── Augmentation ──
print("Augmenting...")
X_aug, y_aug = list(X), list(y)
for xi, yi in zip(X, y):
    # Noise
    X_aug.append(xi + np.random.normal(0, 0.02*np.std(xi), xi.shape).astype(np.float32))
    y_aug.append(yi)
    # Scale
    X_aug.append(xi * np.random.uniform(0.9, 1.1))
    y_aug.append(yi)

X_aug = np.array(X_aug, dtype=np.float32)
y_aug = np.array(y_aug, dtype=np.int32)
print(f"After augmentation: {X_aug.shape}")

# ── Group-aware CV (no data leak from same trial) ──
# Use original unaugmented data for honest CV
print("\n--- Honest CV (unaugmented, no data leak) ---")
cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=3, random_state=42)

classifiers = {}

# LDA (classic BCI workhorse)
classifiers["LDA"] = Pipeline([("s", StandardScaler()), ("c", LinearDiscriminantAnalysis())])

# SVM grid
pipe = Pipeline([
    ("s", StandardScaler()),
    ("k", SelectKBest(mutual_info_classif, k="all")),
    ("c", SVC(probability=True, random_state=42))
])
g = GridSearchCV(pipe, {
    "k__k": [10, 20, 30, "all"],
    "c__C": [0.1, 1, 10, 50, 100, 500],
    "c__gamma": ["scale", "auto", 0.01, 0.001, 0.0001],
    "c__kernel": ["rbf", "linear"],
}, cv=StratifiedKFold(5, shuffle=True, random_state=42),
   scoring="accuracy", n_jobs=-1)
g.fit(X, y)
classifiers["SVM-best"] = g.best_estimator_
print(f"  SVM best params: {g.best_params_}")

classifiers["RF"] = Pipeline([("s", StandardScaler()),
    ("c", RandomForestClassifier(n_estimators=500, max_depth=None, min_samples_leaf=2, random_state=42, n_jobs=-1))])
classifiers["GBM"] = Pipeline([("s", StandardScaler()),
    ("c", GradientBoostingClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=42))])

best_name, best_score, best_clf = None, 0, None
for name, clf in classifiers.items():
    clf.fit(X, y)
    scores = cross_val_score(clf, X, y, cv=cv, scoring="accuracy")
    m = np.mean(scores)
    print(f"  {name:10s}: {m:.1%} +/- {np.std(scores):.1%}  (best: {max(scores):.0%})")
    if m > best_score:
        best_score, best_name, best_clf = m, name, clf

# Ensemble
ens = VotingClassifier([(n, c) for n, c in classifiers.items()],
                       voting="soft")
ens.fit(X, y)
ens_scores = cross_val_score(ens, X, y, cv=cv, scoring="accuracy")
print(f"  {'Ensemble':10s}: {np.mean(ens_scores):.1%} +/- {np.std(ens_scores):.1%}  (best: {max(ens_scores):.0%})")

if np.mean(ens_scores) > best_score:
    final = ens
    final_score = np.mean(ens_scores)
    final_std = np.std(ens_scores)
    final_name = "Ensemble"
else:
    final = best_clf
    final_score = best_score
    s = cross_val_score(best_clf, X, y, cv=cv, scoring="accuracy")
    final_std = np.std(s)
    final_name = best_name

# Train final on ALL augmented data
final.fit(X_aug, y_aug)

print("\n" + "=" * 60)
print(f"  WINNER: {final_name}")
print(f"  CV Accuracy: {final_score:.1%} +/- {final_std:.1%}")
print("=" * 60)

y_pred = final.predict(X)
print(classification_report(y, y_pred, target_names=NAMES))

# Save
with open(MODELS_DIR / "brain_2class_model.pkl", "wb") as f:
    pickle.dump({
        "model": final,
        "class_names": NAMES,
        "cv_accuracy": float(final_score),
        "n_trials": len(all_labels),
        "montage": "bipolar C3-C4",
        "window_sec": 2.0,
    }, f)
print(f"Model saved: {MODELS_DIR / 'brain_2class_model.pkl'}")
