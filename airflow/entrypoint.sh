#!/usr/bin/env bash
set -euo pipefail

mkdir -p /opt/airflow/state /opt/airflow/logs
chown -R airflow: /opt/airflow/state /opt/airflow/logs

as_airflow() {
  /usr/sbin/runuser --preserve-environment --user airflow -- "$@"
}

as_airflow airflow db migrate
as_airflow airflow users create \
  --username "${_AIRFLOW_WWW_USER_USERNAME:-admin}" \
  --password "${_AIRFLOW_WWW_USER_PASSWORD:-admin}" \
  --firstname Admin --lastname User --role Admin --email admin@example.com \
  || true

unset _AIRFLOW_DB_MIGRATE _AIRFLOW_WWW_USER_CREATE
exec /usr/sbin/runuser --preserve-environment --user airflow -- /entrypoint standalone
