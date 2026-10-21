import logging

from pipeline.settings import MIN_PR_AUC_DELTA

logger = logging.getLogger(__name__)


def is_better(candidate: dict, production: dict) -> bool:
    new, old = candidate["metrics"]["pr_auc"], production["metrics"]["pr_auc"]
    if new is None or old is None:
        return False
    return new >= old + MIN_PR_AUC_DELTA


def quality_gate(candidate: dict, production: dict) -> str:
    better = is_better(candidate, production)
    logger.info("PR-AUC кандидата %s = %s, прод-модели %s = %s, дельта %s -> %s",
                candidate["version"], candidate["metrics"]["pr_auc"],
                production["version"], production["metrics"]["pr_auc"],
                MIN_PR_AUC_DELTA, "publish" if better else "reject")
    return "publish_model" if better else "reject_model"
