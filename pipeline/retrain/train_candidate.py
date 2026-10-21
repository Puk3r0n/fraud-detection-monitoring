import logging
from datetime import datetime, timezone

import pandas as pd

from pipeline.model import best_f1_threshold, evaluate, fit_artifact, save_artifact, score
from pipeline.settings import CANDIDATES_DIR

logger = logging.getLogger(__name__)


def train_candidate(split_info: dict) -> dict:
    train = pd.read_parquet(split_info["train_path"])
    test = pd.read_parquet(split_info["test_path"])

    artifact = fit_artifact(train)
    artifact["threshold"] = best_f1_threshold(test["target"], score(artifact, test))
    metrics = evaluate(artifact, test)

    version = f"{split_info['test_month'].replace('-', '')}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
    artifact["version"] = version
    artifact["trained_on"] = {"train_months": split_info["train_months"], "test_month": split_info["test_month"]}

    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    path = CANDIDATES_DIR / f"candidate_{split_info['test_month'].replace('-', '')}.joblib"
    save_artifact(artifact, path)
    logger.info("Кандидат %s: %s", version, metrics)
    return {
        "version": version,
        "path": str(path),
        "metrics": metrics,
        "threshold": artifact["threshold"],
        "batch_month": split_info["batch_month"],
        "window_path": split_info["window_path"],
        "train_months": split_info["train_months"],
        "test_month": split_info["test_month"],
    }
