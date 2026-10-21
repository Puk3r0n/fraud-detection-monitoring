import logging

from airflow.exceptions import AirflowSkipException

from pipeline.db import get_conn, read_month, read_state
from pipeline.settings import BATCHES_DIR

logger = logging.getLogger(__name__)


def extract_month_batch() -> dict:
    conn = get_conn()
    try:
        state = read_state(conn)
        month = state["next_batch_month"]
        frame = read_month(conn, month)
    finally:
        conn.close()
    if frame.empty:
        raise AirflowSkipException(f"В витрине нет строк за {month:%Y-%m}, новый месяц ещё не поставлен")

    BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    path = BATCHES_DIR / f"batch_{month:%Y%m}.parquet"
    frame.to_parquet(path, index=False)
    logger.info("Окно %s - %s, батч %s: %s строк, доля фрода %.4f",
                state["window_start"], state["window_end"], month, len(frame), frame["target"].mean())
    return {"batch_month": month.isoformat(), "batch_path": str(path)}
