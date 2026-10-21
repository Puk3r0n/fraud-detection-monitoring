import logging

from dateutil.relativedelta import relativedelta

from pipeline.db import get_conn
from pipeline.settings import HISTORY_MONTHS

logger = logging.getLogger(__name__)


def prune_old_months(batch_info: dict) -> dict:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT date_trunc('month', max(transaction_time))::date FROM labeled_transactions")
            newest = cur.fetchone()[0]
            cutoff = newest - relativedelta(months=HISTORY_MONTHS)
            cur.execute("DELETE FROM labeled_transactions WHERE transaction_time < %s", (cutoff,))
            deleted = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    logger.info("Последний месяц %s, граница хранения %s, удалено строк: %s", newest, cutoff, deleted)
    return {"batch_month": batch_info["batch_month"], "cutoff": cutoff.isoformat(), "deleted": int(deleted)}
