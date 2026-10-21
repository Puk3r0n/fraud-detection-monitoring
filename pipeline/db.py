import io
import logging
import os
from datetime import date

import pandas as pd
import psycopg2
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)

LABELED_COLUMNS = [
    "transaction_time", "merch", "cat_id", "amount", "name_1", "name_2", "gender",
    "street", "one_city", "us_state", "post_code", "lat", "lon", "population_city",
    "jobs", "merchant_lat", "merchant_lon", "target",
]


def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def next_month(month: date) -> date:
    return month + relativedelta(months=1)


def read_state(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT window_start, window_end, next_batch_month FROM training_state WHERE id = 1")
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("training_state пуста: сначала должен отработать data_loader")
    return {"window_start": row[0], "window_end": row[1], "next_batch_month": row[2]}


def read_month(conn, month: date) -> pd.DataFrame:
    return pd.read_sql(
        f"""
        SELECT {', '.join(LABELED_COLUMNS)}
        FROM labeled_transactions
        WHERE transaction_time >= %s AND transaction_time < %s
        ORDER BY transaction_time
        """,
        conn,
        params=(month, next_month(month)),
    )


def replace_month(conn, month: date, frame: pd.DataFrame) -> None:
    payload = frame.loc[:, LABELED_COLUMNS].copy()
    payload["transaction_time"] = pd.to_datetime(payload["transaction_time"])
    buffer = io.StringIO()
    payload.to_csv(buffer, index=False, header=False, date_format="%Y-%m-%d %H:%M:%S")
    buffer.seek(0)
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM labeled_transactions WHERE transaction_time >= %s AND transaction_time < %s",
            (month, next_month(month)),
        )
        cur.copy_expert(
            f"COPY labeled_transactions ({', '.join(LABELED_COLUMNS)}) FROM STDIN WITH (FORMAT CSV)",
            buffer,
        )
    conn.commit()
