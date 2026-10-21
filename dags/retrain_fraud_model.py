from datetime import datetime, timedelta

from airflow.decorators import dag, task

from pipeline.retrain.commit_window import commit_window
from pipeline.retrain.evaluate_production import evaluate_production
from pipeline.retrain.extract_month_batch import extract_month_batch
from pipeline.retrain.publish_model import publish_model, reject_model
from pipeline.retrain.quality_gate import quality_gate
from pipeline.retrain.slide_training_window import slide_training_window
from pipeline.retrain.time_train_test_split import time_train_test_split
from pipeline.retrain.train_candidate import train_candidate


@dag(
    dag_id="retrain_fraud_model",
    description="Каждые 5 минут сдвигает окно на месяц, учит кандидата и выкатывает его, если он не хуже прода",
    schedule="*/5 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=20),
    default_args={"retries": 1, "retry_delay": timedelta(seconds=30)},
    tags=["mlops", "retrain"],
    doc_md=__doc__,
)
def retrain_fraud_model():
    batch = task(extract_month_batch, task_id="extract_month_batch")()
    window = task(slide_training_window, task_id="slide_training_window")(batch)
    split = task(time_train_test_split, task_id="time_train_test_split")(window)
    candidate = task(train_candidate, task_id="train_candidate")(split)
    production = task(evaluate_production, task_id="evaluate_production")(split)
    gate = task.branch(quality_gate, task_id="quality_gate")(candidate, production)
    published = task(publish_model, task_id="publish_model")(candidate, production)
    rejected = task(reject_model, task_id="reject_model")(candidate, production)
    committed = task(commit_window, task_id="commit_window",
                     trigger_rule="none_failed_min_one_success")(candidate)
    gate >> [published, rejected] >> committed


retrain_fraud_model()
