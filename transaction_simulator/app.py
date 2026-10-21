import json
import logging
import os
import random
import time
import uuid
from datetime import datetime

import pandas as pd
from confluent_kafka import Producer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("transaction_simulator")

CSV_PATH = os.getenv("TRANSACTIONS_CSV_PATH", "/data/test.csv")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "transactions")
SEND_INTERVAL_SECONDS = float(os.getenv("SEND_INTERVAL_SECONDS", "0.2"))


def to_json_value(value):
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def main():
    frame = pd.read_csv(CSV_PATH).drop(columns=["target"], errors="ignore")
    records = [
        {column: to_json_value(value) for column, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]
    logger.info("Loaded %s transactions from %s", len(records), CSV_PATH)

    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS})
    sent = 0
    while True:
        data = dict(random.choice(records))
        data["transaction_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        message = {"transaction_id": str(uuid.uuid4()), "data": data}
        producer.produce(KAFKA_TOPIC, key=message["transaction_id"], value=json.dumps(message))
        producer.poll(0)
        sent += 1
        if sent % 500 == 0:
            producer.flush()
            logger.info("Sent %s transactions", sent)
        time.sleep(SEND_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
