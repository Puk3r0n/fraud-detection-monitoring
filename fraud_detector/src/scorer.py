import logging
import os
import shutil
import time
from pathlib import Path

import joblib
import pandas as pd

from preprocessing import transform

logger = logging.getLogger(__name__)

MODELS_DIR = Path(os.getenv("MODELS_DIR", "/artifacts/models"))
BUNDLED_MODEL = Path(os.getenv("BUNDLED_MODEL_PATH", "/app/models/fraud_model_initial.joblib"))
RELOAD_INTERVAL = float(os.getenv("MODEL_RELOAD_INTERVAL", "2"))
LATEST_FILE = "latest.txt"


def model_path(models_dir, version):
    return Path(models_dir) / f"fraud_model_{version}.joblib"


def read_latest_version(models_dir):
    path = Path(models_dir) / LATEST_FILE
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def publish_latest(models_dir, version):
    tmp = Path(models_dir) / f".{LATEST_FILE}.{version}.tmp"
    tmp.write_text(version + "\n", encoding="utf-8")
    os.replace(tmp, Path(models_dir) / LATEST_FILE)


def ensure_bootstrap(models_dir=MODELS_DIR):
    models_dir.mkdir(parents=True, exist_ok=True)
    if read_latest_version(models_dir):
        return
    dest = model_path(models_dir, "initial")
    if not dest.exists():
        shutil.copyfile(BUNDLED_MODEL, dest)
        logger.info("Initial model copied to %s", dest)
    publish_latest(models_dir, "initial")


def predict(artifact, raw):
    features = transform(raw, artifact["preproc"])
    scores = artifact["model"].predict_proba(features[artifact["features"]])[:, 1]
    return pd.DataFrame({
        "score": scores,
        "fraud_flag": (scores >= artifact["threshold"]).astype(int),
    }, index=raw.index)


class Scorer:
    def __init__(self, models_dir=MODELS_DIR):
        self.models_dir = Path(models_dir)
        ensure_bootstrap(self.models_dir)
        self.artifact = None
        self.version = None
        self._checked_at = 0.0
        self._refresh(force=True)

    def _refresh(self, force=False):
        now = time.monotonic()
        if not force and now - self._checked_at < RELOAD_INTERVAL:
            return
        self._checked_at = now
        version = read_latest_version(self.models_dir)
        if version is None or version == self.version:
            return
        try:
            artifact = joblib.load(model_path(self.models_dir, version))
        except Exception:
            if self.artifact is None:
                raise
            logger.exception("Cannot load model %s, keep scoring with %s", version, self.version)
            return
        self.artifact, self.version = artifact, version
        logger.info("Model %s loaded, threshold=%.4f", version, artifact["threshold"])

    def predict(self, raw):
        self._refresh()
        return predict(self.artifact, raw), self.version
