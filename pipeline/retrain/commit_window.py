import logging
import os
import shutil
from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta

from pipeline.db import get_conn, next_month, read_state
from pipeline.settings import CURRENT_DATASET, WINDOW_MONTHS

logger = logging.getLogger(__name__)


def commit_window(candidate: dict) -> dict:
    month = date.fromisoformat(candidate["batch_month"])
    window_start = month - relativedelta(months=WINDOW_MONTHS - 1)
    conn = get_conn()
    try:
        if read_state(conn)["next_batch_month"] != month:
            logger.info("Указатель уже сдвинут за %s, окно и состояние не трогаем", month)
            return {"window_start": window_start.isoformat(), "window_end": month.isoformat(), "moved": False}

        tmp = CURRENT_DATASET.with_name(".current.parquet.tmp")
        shutil.copyfile(Path(candidate["window_path"]), tmp)
        os.replace(tmp, CURRENT_DATASET)

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE training_state
                SET window_start = %s, window_end = %s, next_batch_month = %s, updated_at = now()
                WHERE id = 1 AND next_batch_month = %s
                """,
                (window_start, month, next_month(month), month),
            )
            moved = cur.rowcount == 1
        conn.commit()
    finally:
        conn.close()
    if moved:
        logger.info("Окно %s - %s, следующий месяц %s", window_start, month, next_month(month))
    else:
        logger.info("Указатель уже сдвинут за %s, повторно не двигаем", month)
    return {"window_start": window_start.isoformat(), "window_end": month.isoformat(), "moved": moved}
