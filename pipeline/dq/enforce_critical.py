import logging

logger = logging.getLogger(__name__)


def enforce_critical(check_info: dict) -> None:
    failed = [r["name"] for r in check_info["results"] if not r["passed"] and r["severity"] == "critical"]
    if failed:
        raise ValueError(f"Нарушены критичные правила качества данных: {', '.join(failed)}")
    logger.info("Критичные правила пройдены")
