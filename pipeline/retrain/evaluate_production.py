import logging

import joblib
import pandas as pd

from pipeline.model import evaluate
from pipeline.settings import MODELS_DIR
from scorer import ensure_bootstrap, model_path, read_latest_version

logger = logging.getLogger(__name__)


def evaluate_production(split_info: dict) -> dict:
    ensure_bootstrap(MODELS_DIR)
    version = read_latest_version(MODELS_DIR)
    artifact = joblib.load(model_path(MODELS_DIR, version))
    metrics = evaluate(artifact, pd.read_parquet(split_info["test_path"]))
    logger.info("Прод-модель %s на %s: %s", version, split_info["test_month"], metrics)
    return {"version": version, "metrics": metrics}
