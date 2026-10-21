import html
import logging
import os

from pipeline.settings import DQ_REPORTS_DIR

logger = logging.getLogger(__name__)

PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>DQ report {stamp}</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 32px; color: #1f2328; }}
table {{ border-collapse: collapse; margin-top: 16px; }}
th, td {{ border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; }}
th {{ background: #f6f8fa; }}
.ok {{ color: #1a7f37; font-weight: 600; }}
.fail {{ color: #cf222e; font-weight: 600; }}
.warn {{ color: #9a6700; font-weight: 600; }}
</style></head><body>
<h1>Качество данных labeled_transactions</h1>
<p>Проверено: {checked_at}. Итог: <span class="{summary_class}">{summary}</span></p>
<p>Строк: {rows}, месяцев: {months}, период: {first} &mdash; {last}, доля фрода: {fraud_rate:.4%}</p>
<table>
<tr><th>Правило</th><th>Уровень</th><th>Описание</th><th>Нарушений</th><th>Проверено</th><th>Статус</th></tr>
{rows_html}
</table>
</body></html>
"""


def render_report(check_info: dict) -> str:
    results = check_info["results"]
    critical_failed = [r for r in results if not r["passed"] and r["severity"] == "critical"]
    warnings = [r for r in results if not r["passed"] and r["severity"] == "warning"]
    if critical_failed:
        summary, summary_class = f"FAIL, критичных нарушений: {len(critical_failed)}", "fail"
    elif warnings:
        summary, summary_class = f"OK с предупреждениями: {len(warnings)}", "warn"
    else:
        summary, summary_class = "OK, все правила пройдены", "ok"

    rows_html = "\n".join(
        "<tr><td>{name}</td><td>{severity}</td><td>{description}</td><td>{violations}</td>"
        "<td>{checked}</td><td class=\"{cls}\">{status}</td></tr>".format(
            name=html.escape(r["name"]),
            severity=r["severity"],
            description=html.escape(r["description"]),
            violations=r["violations"],
            checked=r["checked"],
            cls="ok" if r["passed"] else ("fail" if r["severity"] == "critical" else "warn"),
            status="OK" if r["passed"] else "FAIL",
        )
        for r in results
    )
    profile = check_info["profile"]
    page = PAGE.format(
        stamp=check_info["stamp"],
        checked_at=profile["checked_at"],
        summary=summary,
        summary_class=summary_class,
        rows=profile["rows"],
        months=profile["months"],
        first=profile["first_transaction"],
        last=profile["last_transaction"],
        fraud_rate=profile["fraud_rate"],
        rows_html=rows_html,
    )
    path = DQ_REPORTS_DIR / f"dq_{check_info['stamp']}.html"
    path.write_text(page, encoding="utf-8")
    tmp = DQ_REPORTS_DIR / ".latest.html.tmp"
    tmp.write_text(page, encoding="utf-8")
    os.replace(tmp, DQ_REPORTS_DIR / "latest.html")
    logger.info("Отчёт: %s (%s)", path, summary)
    return str(path)
