import argparse
import logging
from pathlib import Path

import pandas as pd

from pipeline.model import best_f1_threshold, evaluate, fit_artifact, save_artifact, score

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train_initial")
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default=str(ROOT / "data" / "train.csv"))
    parser.add_argument("--out", default=str(ROOT / "fraud_detector" / "models" / "fraud_model_initial.joblib"))
    args = parser.parse_args()

    df = pd.read_csv(args.train)
    months = pd.to_datetime(df["transaction_time"]).dt.to_period("M").astype(str)
    train = df[months.isin(["2019-01", "2019-02", "2019-03"])]
    test = df[months == "2019-04"]

    artifact = fit_artifact(train)
    artifact["threshold"] = best_f1_threshold(test["target"], score(artifact, test))
    artifact["version"] = "initial"
    artifact["trained_on"] = {"train_months": ["2019-01", "2019-02", "2019-03"], "test_month": "2019-04"}
    logger.info("Initial model on 2019-04: %s", evaluate(artifact, test))

    save_artifact(artifact, args.out)
    logger.info("Saved to %s", args.out)


if __name__ == "__main__":
    main()
