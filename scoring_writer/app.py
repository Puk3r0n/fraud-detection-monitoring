import json
import logging
import os
import time

import psycopg2
from confluent_kafka import Consumer, KafkaError
from prometheus_client import Counter, Histogram, start_http_server
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
SCORING_TOPIC = os.getenv("KAFKA_SCORING_TOPIC", "scoring")
CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "scoring-writer")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "200"))
FLUSH_INTERVAL = float(os.getenv("FLUSH_INTERVAL", "1.0"))
METRICS_PORT = int(os.getenv("METRICS_PORT", "8001"))

DSN = (
    f"host={os.getenv('POSTGRES_HOST', 'postgres')} "
    f"port={os.getenv('POSTGRES_PORT', '5432')} "
    f"user={os.getenv('POSTGRES_USER', 'fraud')} "
    f"password={os.getenv('POSTGRES_PASSWORD', 'fraud')} "
    f"dbname={os.getenv('POSTGRES_DB', 'fraud')}"
)

UPSERT = """
INSERT INTO scores (transaction_id, score, fraud_flag, model_version, us_state, merch, cat_id, amount)
VALUES %s
ON CONFLICT (transaction_id) DO UPDATE
SET score = EXCLUDED.score,
    fraud_flag = EXCLUDED.fraud_flag,
    model_version = EXCLUDED.model_version,
    us_state = EXCLUDED.us_state,
    merch = EXCLUDED.merch,
    cat_id = EXCLUDED.cat_id,
    amount = EXCLUDED.amount,
    scored_at = now()
"""

WRITTEN = Counter("scoring_writer_scores_total", "Скоры, записанные в PostgreSQL")
WRITTEN_FRAUD = Counter("scoring_writer_fraud_total", "Записанные скоры с fraud_flag = 1")
MALFORMED = Counter("scoring_writer_malformed_total", "Сообщения scoring, которые не удалось разобрать")
WRITE_SECONDS = Histogram(
    "scoring_writer_write_seconds",
    "Время записи одного батча в PostgreSQL вместе с коммитом оффсетов",
    buckets=(0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0),
)
BATCH_ROWS = Histogram(
    "scoring_writer_batch_rows",
    "Число строк в одном батче записи",
    buckets=(1, 5, 10, 25, 50, 100, 200),
)
WRITTEN_SCORE = Histogram(
    "scoring_writer_score",
    "Распределение записанных скоров",
    buckets=(0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0),
)


def connect_with_retry(attempts=30, delay=2.0):
    for attempt in range(1, attempts + 1):
        try:
            conn = psycopg2.connect(DSN)
            conn.autocommit = False
            logger.info("Connected to PostgreSQL")
            return conn
        except psycopg2.OperationalError as exc:
            logger.warning("PostgreSQL not ready (%s/%s): %s", attempt, attempts, exc)
            time.sleep(delay)
    raise RuntimeError("PostgreSQL is not reachable")


def flush(conn, consumer, rows):
    if not rows:
        return 0
    started = time.perf_counter()
    with conn.cursor() as cur:
        execute_values(cur, UPSERT, rows)
    conn.commit()
    consumer.commit(asynchronous=False)
    WRITE_SECONDS.observe(time.perf_counter() - started)
    BATCH_ROWS.observe(len(rows))
    WRITTEN.inc(len(rows))
    for row in rows:
        WRITTEN_SCORE.observe(row[1])
        if row[2]:
            WRITTEN_FRAUD.inc()
    logger.debug("Wrote %s scores to PostgreSQL", len(rows))
    return len(rows)


def main():
    start_http_server(METRICS_PORT)
    conn = connect_with_retry()

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "group.id": CONSUMER_GROUP,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe([SCORING_TOPIC])
    logger.info("Listening topic '%s', writing to PostgreSQL, metrics on :%s", SCORING_TOPIC, METRICS_PORT)

    rows = []
    last_flush = time.monotonic()
    try:
        while True:
            msg = consumer.poll(0.5)
            if msg is not None:
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        logger.error("Kafka error: %s", msg.error())
                else:
                    try:
                        payload = json.loads(msg.value().decode("utf-8"))
                        amount = payload.get("amount")
                        rows.append((
                            payload["transaction_id"],
                            float(payload["score"]),
                            int(payload["fraud_flag"]),
                            str(payload["model_version"]),
                            payload.get("us_state"),
                            payload.get("merch"),
                            payload.get("cat_id"),
                            float(amount) if amount is not None else None,
                        ))
                    except (ValueError, KeyError, TypeError):
                        MALFORMED.inc()
                        logger.exception("Skipping malformed message")

            expired = time.monotonic() - last_flush >= FLUSH_INTERVAL
            if len(rows) >= BATCH_SIZE or (rows and expired):
                flush(conn, consumer, rows)
                rows = []
                last_flush = time.monotonic()
    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    finally:
        try:
            flush(conn, consumer, rows)
        except Exception:
            logger.exception("Final flush failed")
        consumer.close()
        conn.close()


if __name__ == "__main__":
    main()
