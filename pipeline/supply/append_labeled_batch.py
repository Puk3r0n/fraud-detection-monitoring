import logging
from datetime import date

import pandas as pd

from pipeline.db import get_conn, replace_month

logger = logging.getLogger(__name__)


def append_labeled_batch(batch_info: dict) -> dict:
    month = date.fromisoformat(batch_info["batch_month"])
    frame = pd.read_parquet(batch_info["batch_path"])
    conn = get_conn()
    try:
        replace_month(conn, month, frame)
    finally:
        conn.close()
    logger.info("В витрину записан месяц %s: %s строк", month, len(frame))
    return batch_info
