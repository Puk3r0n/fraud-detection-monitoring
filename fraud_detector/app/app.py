import json
import logging
import os
import sys
import time
from collections import deque

import pandas as pd
from confluent_kafka import Consumer, Producer
from prometheus_client import Counter, Gauge, Histogram, start_http_server

sys.path.append(os.path.abspath("./src"))
from scorer import Scorer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("/app/logs/service.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TRANSACTIONS_TOPIC = os.getenv("KAFKA_TRANSACTIONS_TOPIC", "transactions")
SCORING_TOPIC = os.getenv("KAFKA_SCORING_TOPIC", "scoring")
CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "ml-scorer")
METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))
FRAUD_WINDOW = int(os.getenv("FRAUD_RATIO_WINDOW", "1000"))
LAG_INTERVAL = float(os.getenv("LAG_CHECK_INTERVAL", "5"))

PROCESSED = Counter("fraud_detector_transactions_total", "Обработанные транзакции")
FLAGGED = Counter("fraud_detector_flagged_total", "Транзакции с fraud_flag = 1")
ERRORS = Counter("fraud_detector_errors_total", "Сообщения, которые не удалось отскорить")
PROCESSING_SECONDS = Histogram(
    "fraud_detector_processing_seconds",
    "Время обработки одной транзакции: разбор, препроцессинг, скоринг, отправка",
    buckets=(0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0, 2.0),
)
SCORE = Histogram(
    "fraud_detector_score",
    "Распределение скоров модели",
    buckets=(0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0),
)
AMOUNT = Histogram(
    "fraud_detector_amount",
    "Суммы входящих транзакций",
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
)
FRAUD_RATIO = Gauge(
    "fraud_detector_fraud_ratio",
    f"Доля транзакций с fraud_flag = 1 среди последних {FRAUD_WINDOW}",
)
MODEL_RELOADS = Counter(
    "fraud_detector_model_reloads_total",
    "Загрузки новой версии модели без перезапуска контейнера",
    ["version"],
)
MODEL_INFO = Gauge("fraud_detector_model_info", "Версия модели, которой сейчас скорит сервис", ["version"])
UNKNOWN_VALUES = Counter(
    "fraud_detector_unknown_values_total",
    "Значения признаков, которых не было в train текущей модели (дрейф входа)",
    ["feature"],
)
CONSUMER_LAG = Gauge("fraud_detector_consumer_lag", "Сообщения в transactions, которые сервис ещё не прочитал")


class ProcessingService:
    def __init__(self):
        self.consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
            "group.id": CONSUMER_GROUP,
            "auto.offset.reset": "earliest",
        })
        self.consumer.subscribe([TRANSACTIONS_TOPIC])
        self.producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})
        self.scorer = Scorer()
        self.version = None
        self.scored = 0
        self.recent_flags = deque(maxlen=FRAUD_WINDOW)
        self.lag_checked_at = 0.0
        for feature in ("merch", "cat_id", "us_state"):
            UNKNOWN_VALUES.labels(feature=feature)

    def track_model(self, version):
        if version == self.version:
            return
        if self.version is not None:
            MODEL_INFO.remove(self.version)
        MODEL_INFO.labels(version=version).set(1)
        MODEL_RELOADS.labels(version=version).inc()
        logger.info("Scoring with model %s (was %s)", version, self.version)
        self.version = version

    def track_unknown(self, data):
        preproc = self.scorer.artifact["preproc"]
        if data.get("merch") not in preproc["te"]["merch"]:
            UNKNOWN_VALUES.labels(feature="merch").inc()
        if str(data.get("cat_id")) not in preproc["codes"]["cat_id"]:
            UNKNOWN_VALUES.labels(feature="cat_id").inc()
        if str(data.get("us_state")) not in preproc["codes"]["us_state"]:
            UNKNOWN_VALUES.labels(feature="us_state").inc()

    def handle(self, raw_value):
        message = json.loads(raw_value)
        data = message["data"]
        result, model_version = self.scorer.predict(pd.DataFrame([data]))
        self.track_model(model_version)
        self.track_unknown(data)
        row = result.iloc[0]
        return {
            "transaction_id": message["transaction_id"],
            "score": float(row["score"]),
            "fraud_flag": int(row["fraud_flag"]),
            "model_version": model_version,
            "us_state": data.get("us_state"),
            "merch": data.get("merch"),
            "cat_id": data.get("cat_id"),
            "amount": data.get("amount"),
        }

    def observe(self, output, started):
        PROCESSED.inc()
        SCORE.observe(output["score"])
        if output["amount"] is not None:
            AMOUNT.observe(float(output["amount"]))
        if output["fraud_flag"]:
            FLAGGED.inc()
        self.recent_flags.append(output["fraud_flag"])
        FRAUD_RATIO.set(sum(self.recent_flags) / len(self.recent_flags))
        PROCESSING_SECONDS.observe(time.perf_counter() - started)

    def update_lag(self):
        now = time.monotonic()
        if now - self.lag_checked_at < LAG_INTERVAL:
            return
        self.lag_checked_at = now
        try:
            lag = 0
            for tp in self.consumer.position(self.consumer.assignment()):
                _, high = self.consumer.get_watermark_offsets(tp, timeout=1.0)
                if tp.offset >= 0:
                    lag += max(high - tp.offset, 0)
            CONSUMER_LAG.set(lag)
        except Exception:
            logger.exception("Cannot compute consumer lag")

    def run(self):
        logger.info("Listening topic '%s', writing to '%s'", TRANSACTIONS_TOPIC, SCORING_TOPIC)
        while True:
            msg = self.consumer.poll(1.0)
            self.update_lag()
            if msg is None:
                continue
            if msg.error():
                logger.error("Kafka error: %s", msg.error())
                continue
            started = time.perf_counter()
            try:
                output = self.handle(msg.value().decode("utf-8"))
                self.producer.produce(
                    SCORING_TOPIC,
                    key=output["transaction_id"],
                    value=json.dumps(output),
                )
                self.producer.poll(0)
                self.observe(output, started)
                self.scored += 1
                if self.scored % 500 == 0:
                    logger.info("Scored %s messages, last: %s", self.scored, output)
            except Exception:
                ERRORS.inc()
                logger.exception("Error processing message")

    def close(self):
        self.producer.flush()
        self.consumer.close()


if __name__ == "__main__":
    logger.info("Starting Kafka ML scoring service, metrics on :%s", METRICS_PORT)
    start_http_server(METRICS_PORT)
    service = ProcessingService()
    try:
        service.run()
    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    finally:
        service.close()
