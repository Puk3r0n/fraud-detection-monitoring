import logging
from datetime import date

import pandas as pd
from dateutil.relativedelta import relativedelta

from pipeline.settings import CURRENT_DATASET, WINDOW_MONTHS, WINDOWS_DIR

logger = logging.getLogger(__name__)


def slide_training_window(batch_info: dict) -> dict:
    month = pd.Timestamp(date.fromisoformat(batch_info["batch_month"]))
    first = month - relativedelta(months=WINDOW_MONTHS - 1)

    current = pd.read_parquet(CURRENT_DATASET)
    batch = pd.read_parquet(batch_info["batch_path"])
    for frame in (current, batch):
        frame["transaction_time"] = pd.to_datetime(frame["transaction_time"])

    current = current[current["transaction_time"].dt.to_period("M") != month.to_period("M")]
    window = pd.concat([current, batch], ignore_index=True)
    window = window[(window["transaction_time"] >= first)
                    & (window["transaction_time"] < month + relativedelta(months=1))]
    window = window.sort_values("transaction_time", kind="stable").reset_index(drop=True)

    months = sorted(window["transaction_time"].dt.to_period("M").astype(str).unique())
    if len(months) != WINDOW_MONTHS:
        logger.warning("В окне %s месяцев вместо %s: %s", len(months), WINDOW_MONTHS, months)

    WINDOWS_DIR.mkdir(parents=True, exist_ok=True)
    path = WINDOWS_DIR / f"window_{month:%Y%m}.parquet"
    window.to_parquet(path, index=False)
    logger.info("Новое окно %s: %s строк", months, len(window))
    return {"batch_month": batch_info["batch_month"], "window_path": str(path), "months": months}
