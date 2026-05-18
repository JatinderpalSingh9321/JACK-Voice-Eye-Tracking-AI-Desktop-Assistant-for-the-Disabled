"""Quick 2-class LEFT vs RIGHT test using existing data."""
import numpy as np
from src.train_brain import extract_features
from src.utils import RAW_DATA_DIR, MODELS_DIR
from sklearn.svm import SVC
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.feature_selection import SelectKBest, mutual_info_classif
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report
import pickle

# Load data
path = RAW_DATA_DIR / 'subject_001' / 'session_01_ref_mi.npz'
loaded = np.load(path, allow_pickle=True)
data, labels = loaded['data'], loaded['labels']

# Keep only LEFT (0) and RIGHT (1)
mask = labels < 2
data = data[mask]
labels = labels[mask]
print(f'LEFT: {sum(labels==0)}, RIGHT: {sum(labels==1)}')

# Extract features
X, valid = [], []
for i, epoch in enumerate(data):
    arr = np.array(epoch, dtype=np.float32)
    if len(arr) < 100:
        continue
    feats = extract_features(arr)
    if np.all(np.isfinite(feats)):
        X.append(feats)
        valid.append(i)
X = np.array(X, dtype=np.float32)
y = labels[valid]
print(f'Features: {X.shape}')

# Train 2-class SVM
model = Pipeline([
    ('scaler', StandardScaler()),
    ('select', SelectKBest(mutual_info_classif, k=min(40, X.shape[1]))),
    ('svm', SVC(C=10, gamma='scale', kernel='rbf', probability=True, random_state=42)),
])
model.fit(X, y)

# CV
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_val_score(model, X, y, cv=cv, scoring='accuracy')
print()
print('=== 2-CLASS (LEFT vs RIGHT) RESULTS ===')
print(f'CV Accuracy: {np.mean(scores):.1%} +/- {np.std(scores):.1%}')
print(f'Per fold: {[f"{s:.0%}" for s in scores]}')
print()

y_pred = model.predict(X)
print(classification_report(y, y_pred, target_names=['LEFT', 'RIGHT']))

# Save
with open(MODELS_DIR / 'brain_2class_model.pkl', 'wb') as f:
    pickle.dump({
        'model': model,
        'class_names': ['LEFT', 'RIGHT'],
        'cv_accuracy': float(np.mean(scores)),
    }, f)
print(f'Model saved: {MODELS_DIR / "brain_2class_model.pkl"}')
