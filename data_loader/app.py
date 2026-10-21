import io
import logging
import os
import time
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg2
from dateutil.relativedelta import relativedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("data_loader")

CSV_PATH = Path(os.getenv("LABELED_CSV_PATH", "/data/train.csv"))
ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "/artifacts"))
WINDOW_MONTHS = int(os.getenv("WINDOW_MONTHS", "4"))
TRAINING_DIR = ARTIFACTS_DIR / "training"
CURRENT_DATASET = TRAINING_DIR / "current.parquet"

INITIAL_WINDOW_START = date(2019, 1, 1)

COLUMNS = [
    "transaction_time", "merch", "cat_id", "amount", "name_1", "name_2", "gender",
    "street", "one_city", "us_state", "post_code", "lat", "lon", "population_city",
    "jobs", "merchant_lat", "merchant_lon", "target",
]


def connect():
    last_error = None
    for attempt in range(1, 31):
        try:
            return psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "postgres"),
                port=os.getenv("POSTGRES_PORT", "5432"),
                dbname=os.getenv("POSTGRES_DB"),
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
            )
        except psycopg2.OperationalError as exc:
            last_error = exc
            logger.info("PostgreSQL not ready (%s/30): %s", attempt, exc)
            time.sleep(2)
    raise last_error


def load_csv_if_empty(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM labeled_transactions")
        if cur.fetchone()[0]:
            logger.info("labeled_transactions is not empty, skip CSV load")
            return
    frame = pd.read_csv(CSV_PATH, usecols=COLUMNS)[COLUMNS]
    frame["transaction_time"] = pd.to_datetime(frame["transaction_time"])
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, header=False, date_format="%Y-%m-%d %H:%M:%S")
    buffer.seek(0)
    with conn.cursor() as cur:
        cur.copy_expert(
            f"COPY labeled_transactions ({', '.join(COLUMNS)}) FROM STDIN WITH (FORMAT CSV)",
            buffer,
        )
    conn.commit()
    logger.info("Loaded %s rows into labeled_transactions, %s - %s", len(frame),
                frame["transaction_time"].min(), frame["transaction_time"].max())


def ensure_state(conn):
    window_end = INITIAL_WINDOW_START + relativedelta(months=WINDOW_MONTHS - 1)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO training_state (id, window_start, window_end, next_batch_month)
            VALUES (1, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (INITIAL_WINDOW_START, window_end, window_end + relativedelta(months=1)),
        )
        cur.execute("SELECT window_start, window_end FROM training_state WHERE id = 1")
        state = cur.fetchone()
    conn.commit()
    logger.info("Training window: %s - %s", *state)
    return state


def materialize_window(conn, window_start, window_end):
    if CURRENT_DATASET.exists():
        logger.info("%s already exists, keep it", CURRENT_DATASET)
        return
    frame = pd.read_sql(
        f"""
        SELECT {', '.join(COLUMNS)}
        FROM labeled_transactions
        WHERE transaction_time >= %s AND transaction_time < %s
        ORDER BY transaction_time
        """,
        conn,
        params=(window_start, window_end + relativedelta(months=1)),
    )
    tmp = CURRENT_DATASET.with_suffix(".tmp")
    frame.to_parquet(tmp, index=False)
    os.replace(tmp, CURRENT_DATASET)
    logger.info("Initial training window saved: %s rows -> %s", len(frame), CURRENT_DATASET)


def main():
    for path in (ARTIFACTS_DIR, TRAINING_DIR, ARTIFACTS_DIR / "models", ARTIFACTS_DIR / "dq_reports"):
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o777)

    conn = connect()
    try:
        load_csv_if_empty(conn)
        window_start, window_end = ensure_state(conn)
        materialize_window(conn, window_start, window_end)
    finally:
        conn.close()
    os.chmod(CURRENT_DATASET, 0o666)
    logger.info("Data loader finished")


if __name__ == "__main__":
    main()
