import logging

import pandas as pd

from pipeline.settings import SPLITS_DIR

logger = logging.getLogger(__name__)


def time_train_test_split(window_info: dict) -> dict:
    frame = pd.read_parquet(window_info["window_path"])
    periods = pd.to_datetime(frame["transaction_time"]).dt.to_period("M")
    latest = periods.max()
    train, test = frame[periods < latest], frame[periods == latest]
    if train.empty or test.empty:
        raise RuntimeError(f"Пустая часть разбиения: train={len(train)}, test={len(test)}")

    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = latest.strftime("%Y%m")
    train_path = SPLITS_DIR / f"train_{suffix}.parquet"
    test_path = SPLITS_DIR / f"test_{suffix}.parquet"
    train.to_parquet(train_path, index=False)
    test.to_parquet(test_path, index=False)

    train_months = sorted(periods[periods < latest].astype(str).unique())
    logger.info("train %s: %s строк, test %s: %s строк", train_months, len(train), latest, len(test))
    return {
        "batch_month": window_info["batch_month"],
        "window_path": window_info["window_path"],
        "train_path": str(train_path),
        "test_path": str(test_path),
        "train_months": train_months,
        "test_month": str(latest),
    }
