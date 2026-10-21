import json
import logging
from datetime import datetime, timezone

from pipeline.db import get_conn
from pipeline.dq.rules import RULES
from pipeline.settings import DQ_REPORTS_DIR

logger = logging.getLogger(__name__)


def profile_showcase() -> dict:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*), min(transaction_time), max(transaction_time),
                       count(DISTINCT date_trunc('month', transaction_time)), avg(target)
                FROM labeled_transactions
                """
            )
            rows, first, last, months, fraud_rate = cur.fetchone()
    finally:
        conn.close()
    profile = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "rows": int(rows),
        "first_transaction": str(first),
        "last_transaction": str(last),
        "months": int(months),
        "fraud_rate": float(fraud_rate or 0),
    }
    logger.info("Профиль витрины: %s", profile)
    return profile


def run_checks(profile: dict) -> dict:
    results = []
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for rule in RULES:
                cur.execute(rule.sql)
                violations, checked = cur.fetchone()
                passed = int(violations) == 0
                results.append({
                    "name": rule.name,
                    "severity": rule.severity,
                    "description": rule.description,
                    "violations": int(violations),
                    "checked": int(checked),
                    "passed": passed,
                })
                logger.info("%s [%s]: %s (%s из %s)", rule.name, rule.severity,
                            "OK" if passed else "FAIL", violations, checked)
    finally:
        conn.close()

    DQ_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = DQ_REPORTS_DIR / f"dq_{stamp}.json"
    path.write_text(json.dumps({"profile": profile, "results": results}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return {"stamp": stamp, "json_path": str(path), "profile": profile, "results": results}
