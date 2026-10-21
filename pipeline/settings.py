import os
from pathlib import Path

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "/artifacts"))
MODELS_DIR = ARTIFACTS_DIR / "models"
REJECTED_DIR = MODELS_DIR / "rejected"
DQ_REPORTS_DIR = ARTIFACTS_DIR / "dq_reports"
TRAINING_DIR = ARTIFACTS_DIR / "training"

CURRENT_DATASET = TRAINING_DIR / "current.parquet"
BATCHES_DIR = TRAINING_DIR / "batches"
WINDOWS_DIR = TRAINING_DIR / "windows"
SPLITS_DIR = TRAINING_DIR / "splits"
CANDIDATES_DIR = TRAINING_DIR / "candidates"
SUPPLY_DIR = TRAINING_DIR / "supply"

WINDOW_MONTHS = int(os.getenv("WINDOW_MONTHS", "4"))
SUPPLY_BATCH_ROWS = int(os.getenv("SUPPLY_BATCH_ROWS", "50000"))
HISTORY_MONTHS = int(os.getenv("HISTORY_MONTHS", "24"))
MIN_PR_AUC_DELTA = float(os.getenv("MIN_PR_AUC_DELTA", "0.0"))
