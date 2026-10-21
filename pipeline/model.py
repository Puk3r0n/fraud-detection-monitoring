import pickle

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, f1_score, precision_recall_curve, roc_auc_score

from preprocessing import CATEGORICAL_FEATURES, FEATURES, TARGET_COL, fit_preprocessor, transform

RANDOM_STATE = 42


def make_model():
    return HistGradientBoostingClassifier(
        learning_rate=0.08,
        max_iter=300,
        max_leaf_nodes=31,
        l2_regularization=1.0,
        categorical_features=[FEATURES.index(c) for c in CATEGORICAL_FEATURES],
        early_stopping=True,
        validation_fraction=0.1,
        random_state=RANDOM_STATE,
    )


def fit_artifact(train):
    preproc = fit_preprocessor(train)
    model = make_model().fit(transform(train, preproc), train[TARGET_COL])
    return {"model": model, "preproc": preproc, "features": FEATURES, "threshold": 0.5}


def save_artifact(artifact, path):
    with open(path, "wb") as f:
        pickle.dump(artifact, f, protocol=pickle.HIGHEST_PROTOCOL)


def best_f1_threshold(y_true, scores):
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-9, None)
    return float(thresholds[int(np.nanargmax(f1[:-1]))])


def score(artifact, frame):
    features = transform(frame, artifact["preproc"])
    return artifact["model"].predict_proba(features[artifact["features"]])[:, 1]


def evaluate(artifact, test):
    y_true = test[TARGET_COL].to_numpy()
    scores = score(artifact, test)
    has_both = len(np.unique(y_true)) == 2
    return {
        "pr_auc": float(average_precision_score(y_true, scores)) if has_both else None,
        "roc_auc": float(roc_auc_score(y_true, scores)) if has_both else None,
        "f1": float(f1_score(y_true, scores >= artifact["threshold"], zero_division=0)),
        "rows": int(len(test)),
        "fraud_rate": float(y_true.mean()),
    }
