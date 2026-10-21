from datetime import datetime, timedelta

from airflow.decorators import dag, task

from pipeline.dq.enforce_critical import enforce_critical
from pipeline.dq.render_report import render_report
from pipeline.dq.run_checks import profile_showcase, run_checks


@dag(
    dag_id="data_quality_report",
    description="Каждые 10 минут проверяет витрину по правилам DQ и публикует HTML-отчёт в dq_reports",
    schedule="*/10 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=10),
    default_args={"retries": 1, "retry_delay": timedelta(seconds=30)},
    tags=["mlops", "data-quality"],
    doc_md=__doc__,
)
def data_quality_report():
    profile = task(profile_showcase, task_id="profile_showcase")()
    checks = task(run_checks, task_id="run_checks")(profile)
    report = task(render_report, task_id="render_report")(checks)
    report >> task(enforce_critical, task_id="enforce_critical")(checks)


data_quality_report()
