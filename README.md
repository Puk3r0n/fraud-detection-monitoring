# Fraud Detection: мониторинг в Prometheus и Grafana

ДЗ 5 по ML System Design. Сервис из [ДЗ 3](https://github.com/Puk3r0n/fraud-detection-airflow) плюс метрики Prometheus, дашборды и алерты Grafana и срез из PostgreSQL.

## Запуск

    cp .env.example .env
    mkdir -p data    # train.csv и test.csv с Kaggle
    docker compose up -d --build

- Grafana: http://localhost:3000, admin / admin
- Prometheus: http://localhost:9090/targets
- Airflow: http://localhost:8081, admin / admin

## Метрики

fraud_detector (:8000/metrics): transactions_total, flagged_total, errors_total, processing_seconds, score, fraud_ratio, model_reloads_total, model_info, unknown_values_total, consumer_lag, amount.

scoring_writer (:8001/metrics): scores_total, fraud_total, write_seconds, batch_rows, score, malformed_total.

Своя метрика - fraud_detector_unknown_values_total{feature}: мерчанты, категории и штаты, которых не было в train текущей модели. Это ранний сигнал дрейфа входа. Панель «Неизвестные значения признаков», проверка: `scripts/send_unknown_merchant.sh 50`.

## Дашборды

Папка Fraud Detection: «Скоринг транзакций», «Запись результатов», «Системные метрики», «Фрод по штатам и мерчантам» (PostgreSQL, фильтры по штату и мерчанту). Скриншоты в screenshots/.

## Алерты

    Доля фрода выше 3%                    fraud_ratio > 0.03
    Поток скоринга остановился            rate(transactions_total) < 0.5 tx/s
    p95 обработки выше 250 мс             processing_seconds p95 > 0.25
    Скоринг отстаёт от потока             consumer_lag > 500

Проверка: `docker compose stop transaction_simulator`, через минуту алерт в Alerting -> Alert rules.

## Проверка

    curl -s http://localhost:9090/api/v1/query --data-urlencode 'query=fraud_detector_transactions_total'
    docker compose exec airflow airflow dags trigger retrain_fraud_model

После публикации модели на дашборде «Скоринг транзакций» появляется красная отметка «Модель <версия>».
