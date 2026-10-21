import json
import logging
import os
import shutil
from pathlib import Path

from pipeline.settings import MODELS_DIR, REJECTED_DIR
from scorer import model_path, publish_latest

logger = logging.getLogger(__name__)


def _copy_atomic(src: Path, dest: Path) -> None:
    tmp = dest.with_name(f".{dest.name}.tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dest)


def _write_report(path: Path, candidate: dict, production: dict, decision: str) -> None:
    path.write_text(json.dumps({
        "version": candidate["version"],
        "decision": decision,
        "train_months": candidate["train_months"],
        "test_month": candidate["test_month"],
        "threshold": candidate["threshold"],
        "metrics": candidate["metrics"],
        "production_version": production["version"],
        "production_metrics": production["metrics"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def publish_model(candidate: dict, production: dict) -> str:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = model_path(MODELS_DIR, candidate["version"])
    _copy_atomic(Path(candidate["path"]), dest)
    _write_report(dest.with_suffix(".metrics.json"), candidate, production, "published")
    publish_latest(MODELS_DIR, candidate["version"])
    logger.info("Опубликована модель %s вместо %s", candidate["version"], production["version"])
    return candidate["version"]


def reject_model(candidate: dict, production: dict) -> str:
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    dest = model_path(REJECTED_DIR, candidate["version"])
    _copy_atomic(Path(candidate["path"]), dest)
    _write_report(dest.with_suffix(".metrics.json"), candidate, production, "rejected")
    logger.info("Кандидат %s хуже прод-модели %s, остаётся в %s",
                candidate["version"], production["version"], REJECTED_DIR)
    return candidate["version"]
