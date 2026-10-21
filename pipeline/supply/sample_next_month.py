import calendar
import logging

import pandas as pd

from pipeline.db import LABELED_COLUMNS, get_conn
from pipeline.settings import SUPPLY_BATCH_ROWS, SUPPLY_DIR

logger = logging.getLogger(__name__)


def shift_into_month(times: pd.Series, month: pd.Timestamp) -> pd.Series:
    times = pd.to_datetime(times)
    last_day = calendar.monthrange(month.year, month.month)[1]
    return pd.to_datetime(pd.DataFrame({
        "year": month.year,
        "month": month.month,
        "day": times.dt.day.clip(upper=last_day),
        "hour": times.dt.hour,
        "minute": times.dt.minute,
    }))


def sample_next_month() -> dict:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT max(transaction_time), count(*) FROM labeled_transactions")
            max_time, total = cur.fetchone()
        if not total:
            raise RuntimeError("Витрина пуста: сначала должен отработать data_loader")
        frame = pd.read_sql(
            f"SELECT {', '.join(LABELED_COLUMNS)} FROM labeled_transactions ORDER BY random() LIMIT %s",
            conn,
            params=(min(SUPPLY_BATCH_ROWS, total),),
        )
    finally:
        conn.close()

    month = (pd.Timestamp(max_time).to_period("M") + 1).to_timestamp()
    frame["transaction_time"] = shift_into_month(frame["transaction_time"], month)

    SUPPLY_DIR.mkdir(parents=True, exist_ok=True)
    path = SUPPLY_DIR / f"supply_{month:%Y%m}.parquet"
    frame.to_parquet(path, index=False)
    logger.info("Батч %s: %s строк из %s, доля фрода %.4f",
                month.strftime("%Y-%m"), len(frame), total, frame["target"].mean())
    return {"batch_month": month.date().isoformat(), "batch_path": str(path), "rows": int(len(frame))}
