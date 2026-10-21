#!/usr/bin/env bash
set -euo pipefail
N="${1:-50}"
for i in $(seq 1 "$N"); do
  printf '{"transaction_id":"drift-test-%s-%s","data":{"transaction_time":"%s","merch":"fraud_New Merchant LLC","cat_id":"crypto","amount":120.5,"name_1":"Test","name_2":"Drift","gender":"F","street":"1 Main St","one_city":"Los Angeles","us_state":"CA","post_code":90001,"lat":34.05,"lon":-118.24,"population_city":3900000,"jobs":"Engineer","merchant_lat":34.1,"merchant_lon":-118.3}}\n' \
    "$(date +%s)" "$i" "$(date '+%Y-%m-%d %H:%M')"
done | docker compose exec -T kafka kafka-console-producer --bootstrap-server kafka:9092 --topic transactions
echo "Отправлено $N транзакций с незнакомым мерчантом"
