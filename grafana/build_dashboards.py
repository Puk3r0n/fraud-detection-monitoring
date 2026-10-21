import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dashboards"
PROM = {"type": "prometheus", "uid": "prometheus"}
PG = {"type": "grafana-postgresql-datasource", "uid": "postgres"}


class Layout:

    def __init__(self):
        self.x = self.y = self.row_h = 0
        self.next_id = 1

    def place(self, panel, w, h):
        if self.x + w > 24:
            self.x, self.y, self.row_h = 0, self.y + self.row_h, 0
        panel["gridPos"] = {"x": self.x, "y": self.y, "w": w, "h": h}
        panel["id"] = self.next_id
        self.next_id += 1
        self.x += w
        self.row_h = max(self.row_h, h)
        return panel


def prom(expr, legend="", fmt=None):
    target = {"datasource": PROM, "expr": expr, "legendFormat": legend, "range": True}
    if fmt:
        target["format"] = fmt
    return target


def sql(query, fmt="table"):
    return {"datasource": PG, "rawSql": query, "format": fmt, "editorMode": "code", "rawQuery": True}


def timeseries(title, targets, unit="short", description="", stack=False, ds=PROM, decimals=None, soft_max=None):
    defaults = {
        "unit": unit,
        "custom": {"lineWidth": 2, "fillOpacity": 10, "showPoints": "never",
                   "stacking": {"mode": "normal" if stack else "none"}},
    }
    if soft_max is not None:
        defaults["min"] = 0
        defaults["custom"]["axisSoftMax"] = soft_max
    if decimals is not None:
        defaults["decimals"] = decimals
    return {
        "type": "timeseries", "title": title, "description": description, "datasource": ds,
        "targets": [dict(t, refId=chr(65 + i)) for i, t in enumerate(targets)],
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}},
    }


def stat(title, target, unit="short", description="", text_mode="auto", decimals=None, ds=PROM, thresholds=None):
    defaults = {"unit": unit, "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": thresholds or [{"color": "green", "value": None}]}}
    if decimals is not None:
        defaults["decimals"] = decimals
    return {
        "type": "stat", "title": title, "description": description, "datasource": ds,
        "targets": [dict(target, refId="A", **({"instant": True, "range": False} if ds is PROM else {}))],
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "textMode": text_mode, "colorMode": "value", "graphMode": "none"},
    }


def heatmap(title, expr, description=""):
    return {
        "type": "heatmap", "title": title, "description": description, "datasource": PROM,
        "targets": [dict(prom(expr, "{{le}}", fmt="heatmap"), refId="A")],
        "options": {
            "calculate": False,
            "yAxis": {"axisLabel": "score"},
            "color": {"mode": "scheme", "scheme": "Oranges", "scale": "exponential", "exponent": 0.5},
            "cellGap": 1,
            "tooltip": {"mode": "single", "yHistogram": True},
            "rowsFrame": {"layout": "auto"},
        },
    }


def barchart(title, query, unit="short", description="", x_field=None):
    defaults = {"unit": unit, "custom": {"fillOpacity": 80}}
    if unit == "percentunit":
        defaults["min"] = 0
        defaults["custom"]["axisSoftMax"] = 0.02
    return {
        "type": "barchart", "title": title, "description": description, "datasource": PG,
        "targets": [dict(sql(query), refId="A")],
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {"xField": x_field, "orientation": "auto", "showValue": "auto",
                    "legend": {"displayMode": "list", "placement": "bottom"}, "xTickLabelRotation": -45},
    }


def table(title, query, description="", overrides=None):
    return {
        "type": "table", "title": title, "description": description, "datasource": PG,
        "targets": [dict(sql(query), refId="A")],
        "fieldConfig": {"defaults": {}, "overrides": overrides or []},
        "options": {"showHeader": True},
    }


def dashboard(uid, title, panels, description, refresh="5s", time_from="now-15m",
              annotations=(), templating=(), tags=()):
    return {
        "uid": uid, "title": title, "description": description, "tags": ["fraud", *tags],
        "schemaVersion": 39, "version": 1, "editable": False, "graphTooltip": 1,
        "refresh": refresh, "time": {"from": time_from, "to": "now"},
        "timepicker": {"refresh_intervals": ["1s", "5s", "10s", "30s", "1m"]},
        "annotations": {"list": [
            {"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True,
             "hide": True, "iconColor": "rgba(0, 211, 255, 1)", "name": "Annotations & Alerts", "type": "dashboard"},
            *annotations,
        ]},
        "templating": {"list": list(templating)},
        "panels": panels,
    }


MODEL_SWITCH = {
    "name": "Смена модели", "datasource": PROM, "enable": True, "iconColor": "#F2495C",
    "expr": "fraud_detector_model_reloads_total unless fraud_detector_model_reloads_total offset 30s",
    "step": "10s", "titleFormat": "Модель {{version}}", "textFormat": "Скоринг перешёл на {{version}}",
    "useValueForTime": False,
}

P95 = "histogram_quantile({q}, sum(rate({m}_bucket[30s])) by (le))"


def scoring_dashboard():
    lay = Layout()
    panels = [
        lay.place(stat("Модель в проде", prom("fraud_detector_model_info", "{{version}}"),
                       text_mode="name", description="Версия, которой сейчас скорит сервис"), 6, 4),
        lay.place(stat("TPS", prom("sum(rate(fraud_detector_transactions_total[30s]))"), "reqps", decimals=1), 3, 4),
        lay.place(stat("Доля фрода (1000 посл.)", prom("fraud_detector_fraud_ratio"), "percentunit", decimals=2,
                       thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 0.03}]), 4, 4),
        lay.place(stat("p95 обработки", prom(P95.format(q=0.95, m="fraud_detector_processing_seconds")), "s",
                       decimals=4), 4, 4),
        lay.place(stat("Отставание консьюмера", prom("fraud_detector_consumer_lag"), "short",
                       thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 100}]), 4, 4),
        lay.place(stat("Ошибки скоринга", prom("sum(fraud_detector_errors_total)"), "short",
                       thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 1}]), 3, 4),
        lay.place(timeseries("Скорость потока", [
            prom("sum(rate(fraud_detector_transactions_total[10s]))", "обработано, tx/s"),
            prom("sum(rate(fraud_detector_flagged_total[1m]))", "помечено фродом, tx/s"),
        ], "reqps", "Транзакции в секунду по счётчикам сервиса скоринга"), 12, 8),
        lay.place(timeseries("Время обработки транзакции", [
            prom(P95.format(q=0.5, m="fraud_detector_processing_seconds"), "p50"),
            prom(P95.format(q=0.95, m="fraud_detector_processing_seconds"), "p95"),
            prom(P95.format(q=0.99, m="fraud_detector_processing_seconds"), "p99"),
            prom("rate(fraud_detector_processing_seconds_sum[30s]) / rate(fraud_detector_processing_seconds_count[30s])",
                 "среднее"),
        ], "s", "Разбор сообщения, препроцессинг, predict_proba и отправка в scoring"), 12, 8),
        lay.place(timeseries("Доля фрода", [
            prom("fraud_detector_fraud_ratio", "среди последних 1000"),
            prom("sum(rate(fraud_detector_flagged_total[1m])) / sum(rate(fraud_detector_transactions_total[1m]))",
                 "за минуту"),
        ], "percentunit", "Доля транзакций с fraud_flag = 1", decimals=2), 12, 8),
        lay.place(heatmap("Распределение скоров во времени",
                          "sum(increase(fraud_detector_score_bucket[15s])) by (le)",
                          "Гистограмма fraud_detector_score по 15-секундным интервалам"), 12, 8),
        lay.place(timeseries("Неизвестные значения признаков", [
            prom("sum by (feature) (rate(fraud_detector_unknown_values_total[1m])) / scalar(sum(rate(fraud_detector_transactions_total[1m])))",
                 "{{feature}}"),
        ], "percentunit", "Доля транзакций, у которых мерчант, категория или штат не встречались в train модели. "
           "Для них признак берётся по умолчанию, рост доли - сигнал дрейфа входа", decimals=2, soft_max=0.05), 12, 8),
        lay.place(timeseries("Отставание от потока", [
            prom("fraud_detector_consumer_lag", "непрочитанные сообщения"),
        ], "short", "Сколько сообщений в transactions сервис ещё не прочитал. Растёт, если скоринг не успевает"), 6, 8),
        lay.place(timeseries("Медианная сумма транзакции", [
            prom(P95.format(q=0.5, m="fraud_detector_amount"), "p50"),
            prom(P95.format(q=0.9, m="fraud_detector_amount"), "p90"),
        ], "currencyUSD"), 6, 8),
    ]
    return dashboard("fraud-scoring", "Скоринг транзакций", panels,
                     "Обработка потока сервисом fraud_detector. Красные отметки - смена версии модели",
                     annotations=[MODEL_SWITCH], tags=["prometheus"])


def writer_dashboard():
    lay = Layout()
    panels = [
        lay.place(stat("Записано скоров", prom("sum(scoring_writer_scores_total)")), 6, 4),
        lay.place(stat("Выявлено фрода", prom("sum(scoring_writer_fraud_total)"),
                       thresholds=[{"color": "orange", "value": None}]), 6, 4),
        lay.place(stat("Скорость записи", prom("sum(rate(scoring_writer_scores_total[30s]))"), "reqps", decimals=1), 6, 4),
        lay.place(stat("p95 записи батча", prom(P95.format(q=0.95, m="scoring_writer_write_seconds")), "s",
                       decimals=4), 6, 4),
        lay.place(timeseries("Скорость записи в PostgreSQL", [
            prom("sum(rate(scoring_writer_scores_total[10s]))", "скоров/с"),
            prom("sum(rate(scoring_writer_fraud_total[1m]))", "фрод/с"),
        ], "reqps"), 12, 8),
        lay.place(timeseries("Время записи батча", [
            prom(P95.format(q=0.5, m="scoring_writer_write_seconds"), "p50"),
            prom(P95.format(q=0.95, m="scoring_writer_write_seconds"), "p95"),
            prom("rate(scoring_writer_write_seconds_sum[30s]) / rate(scoring_writer_write_seconds_count[30s])", "среднее"),
        ], "s", "execute_values и коммит оффсетов в Kafka"), 12, 8),
        lay.place(timeseries("Выявленный фрод", [
            prom("sum(increase(scoring_writer_fraud_total[1m]))", "фрод за минуту"),
        ], "short"), 8, 8),
        lay.place(timeseries("Размер батча", [
            prom("rate(scoring_writer_batch_rows_sum[30s]) / rate(scoring_writer_batch_rows_count[30s])", "строк в батче"),
        ], "short"), 8, 8),
        lay.place(timeseries("Битые сообщения", [
            prom("sum(rate(scoring_writer_malformed_total[1m]))", "msg/s"),
        ], "short"), 8, 8),
        lay.place(heatmap("Распределение записанных скоров",
                          "sum(increase(scoring_writer_score_bucket[15s])) by (le)"), 24, 8),
    ]
    return dashboard("fraud-writer", "Запись результатов", panels,
                     "Сервис scoring_writer: топик scoring -> таблица scores", tags=["prometheus"])


NODE_DEV = 'device=~"eth.*|en.*|wl.*"'
NODE_FS = 'fstype=~"ext4|xfs|btrfs"'


def system_dashboard():
    lay = Layout()
    panels = [
        lay.place(stat("CPU", prom('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[30s])))'), "percent",
                       decimals=1), 6, 4),
        lay.place(stat("Память", prom("100 * (1 - max(node_memory_MemAvailable_bytes) / max(node_memory_MemTotal_bytes))"),
                       "percent", decimals=1), 6, 4),
        lay.place(stat("Ядер", prom('count(count by (cpu) (node_cpu_seconds_total{mode="idle"}))')), 6, 4),
        lay.place(stat("Uptime", prom("time() - max(node_boot_time_seconds)"), "s"), 6, 4),
        lay.place(timeseries("CPU по режимам", [
            prom('100 * sum by (mode) (rate(node_cpu_seconds_total{mode!="idle"}[30s])) / scalar(count(node_cpu_seconds_total{mode="idle"}))',
                 "{{mode}}"),
        ], "percent", stack=True), 12, 8),
        lay.place(timeseries("Память", [
            prom("max(node_memory_MemTotal_bytes) - max(node_memory_MemAvailable_bytes)", "занято"),
            prom("max(node_memory_Cached_bytes) + max(node_memory_Buffers_bytes)", "кеш и буферы"),
            prom("max(node_memory_MemTotal_bytes)", "всего"),
        ], "bytes"), 12, 8),
        lay.place(timeseries("Сеть", [
            prom(f"sum by (device) (rate(node_network_receive_bytes_total{{{NODE_DEV}}}[30s]))", "{{device}} rx"),
            prom(f"-sum by (device) (rate(node_network_transmit_bytes_total{{{NODE_DEV}}}[30s]))", "{{device}} tx"),
        ], "Bps", "Приём вверх, передача вниз"), 8, 8),
        lay.place(timeseries("Диск: чтение и запись", [
            prom("sum(rate(node_disk_read_bytes_total[30s]))", "чтение"),
            prom("-sum(rate(node_disk_written_bytes_total[30s]))", "запись"),
        ], "Bps"), 8, 8),
        lay.place(timeseries("Диск: заполнение", [
            prom(f"100 * (1 - max by (device) (node_filesystem_avail_bytes{{{NODE_FS}}}) "
                 f"/ max by (device) (node_filesystem_size_bytes{{{NODE_FS}}}))", "{{device}}"),
        ], "percent"), 8, 8),
    ]
    return dashboard("fraud-system", "Системные метрики", panels,
                     "Node Exporter: CPU, память, сеть и диск хоста Docker", tags=["prometheus", "node"])


FILTER = ("('__all' IN ($state) OR us_state IN ($state)) "
          "AND ('__all' IN ($merch) OR merch IN ($merch))")


def variable(name, label, query):
    return {
        "name": name, "label": label, "type": "query", "datasource": PG, "query": query,
        "definition": query, "refresh": 2, "multi": True, "includeAll": True, "allValue": "'__all'",
        "current": {"selected": True, "text": ["All"], "value": ["$__all"]}, "sort": 1,
    }


def business_dashboard():
    lay = Layout()
    panels = [
        lay.place(stat("Транзакций в выборке", sql(
            f"SELECT count(*) AS value FROM scores WHERE $__timeFilter(scored_at) AND {FILTER}"), ds=PG), 6, 4),
        lay.place(stat("Доля фрода в выборке", sql(
            f"SELECT avg(fraud_flag)::float AS value FROM scores WHERE $__timeFilter(scored_at) AND {FILTER}"),
            "percentunit", decimals=2, ds=PG), 6, 4),
        lay.place(stat("Средний скор", sql(
            f"SELECT avg(score) AS value FROM scores WHERE $__timeFilter(scored_at) AND {FILTER}"),
            decimals=4, ds=PG), 6, 4),
        lay.place(stat("Сумма под подозрением", sql(
            f"SELECT coalesce(sum(amount) FILTER (WHERE fraud_flag = 1), 0) AS value FROM scores "
            f"WHERE $__timeFilter(scored_at) AND {FILTER}"), "currencyUSD", ds=PG), 6, 4),
        lay.place(barchart("Плотность распределения скоров", f"""
            WITH s AS (SELECT score FROM scores WHERE $__timeFilter(scored_at) AND {FILTER}),
                 b AS (SELECT least(floor(score * 20), 19)::int AS bin, count(*) AS n FROM s GROUP BY 1)
            SELECT to_char(g.bin / 20.0, 'FM0.00') || '-' || to_char((g.bin + 1) / 20.0, 'FM0.00') AS score,
                   coalesce(b.n, 0) / greatest((SELECT count(*) FROM s), 1)::float * 20 AS density
            FROM generate_series(0, 19) AS g(bin) LEFT JOIN b USING (bin)
            ORDER BY g.bin
        """, description="Гистограмма скоров с шагом 0.05, нормированная на плотность: "
                         "площадь столбцов равна 1. Учитывает фильтры штата и мерчанта", x_field="score"), 12, 9),
        lay.place(timeseries("TPS отфильтрованных транзакций", [sql(f"""
            SELECT $__timeGroupAlias(scored_at, '10s'), count(*) / 10.0 AS "tx/s",
                   count(*) FILTER (WHERE fraud_flag = 1) / 10.0 AS "фрод tx/s"
            FROM scores WHERE $__timeFilter(scored_at) AND {FILTER}
            GROUP BY 1 ORDER BY 1
        """, fmt="time_series")], "reqps", "Транзакции в секунду по 10-секундным интервалам", ds=PG), 12, 9),
        lay.place(barchart("Доля фрода по категориям, последние 1000 транзакций", f"""
            SELECT cat_id, avg(fraud_flag)::float AS fraud_share
            FROM (SELECT cat_id, fraud_flag FROM scores WHERE {FILTER} ORDER BY scored_at DESC LIMIT 1000) t
            GROUP BY cat_id ORDER BY fraud_share DESC
        """, "percentunit", "Средний fraud_flag по cat_id среди последних 1000 транзакций с учётом фильтров",
            x_field="cat_id"), 12, 9),
        lay.place(table("Скоры и доля фрода по версиям модели", """
            SELECT model_version AS "версия", count(*) AS "скоров",
                   avg(fraud_flag)::float AS "доля фрода", avg(score) AS "средний скор",
                   min(scored_at) AS "первый скор", max(scored_at) AS "последний скор"
            FROM scores GROUP BY model_version ORDER BY min(scored_at) DESC
        """, "Какая версия модели сколько насчитала. Фильтры не применяются", overrides=[
            {"matcher": {"id": "byName", "options": "доля фрода"},
             "properties": [{"id": "unit", "value": "percentunit"}, {"id": "decimals", "value": 2}]},
            {"matcher": {"id": "byName", "options": "средний скор"}, "properties": [{"id": "decimals", "value": 4}]},
        ]), 12, 9),
        lay.place(timeseries("Скоры по версиям модели", [sql("""
            SELECT $__timeGroupAlias(scored_at, '30s'), model_version AS metric, count(*) AS value
            FROM scores WHERE $__timeFilter(scored_at)
            GROUP BY 1, 2 ORDER BY 1
        """, fmt="time_series")], "short", "Число скоров за 30 секунд в разрезе версии: видно, когда новая версия "
                                           "сменила старую", stack=True, ds=PG), 12, 8),
        lay.place(timeseries("Сумма под подозрением фрода", [sql(f"""
            SELECT $__timeGroupAlias(scored_at, '1m'),
                   coalesce(sum(amount) FILTER (WHERE fraud_flag = 1), 0) AS "помечено фродом, $",
                   sum(amount) AS "весь оборот, $"
            FROM scores WHERE $__timeFilter(scored_at) AND {FILTER}
            GROUP BY 1 ORDER BY 1
        """, fmt="time_series")], "currencyUSD", "Свой бизнес-график: сколько денег в минуту проходит через "
                                                 "транзакции с fraud_flag = 1 на фоне всего оборота. Это объём, "
                                                 "который придётся проверять вручную или блокировать", ds=PG), 12, 8),
        lay.place(barchart("Штаты с наибольшей долей фрода", f"""
            SELECT us_state, avg(fraud_flag)::float AS fraud_share
            FROM scores WHERE $__timeFilter(scored_at) AND {FILTER}
            GROUP BY us_state HAVING count(*) >= 20
            ORDER BY fraud_share DESC LIMIT 10
        """, "percentunit", "Топ-10 штатов по доле фрода за выбранный период, штаты от 20 транзакций",
            x_field="us_state"), 24, 8),
    ]
    templating = [
        variable("state", "Штат", "SELECT DISTINCT us_state FROM scores WHERE us_state IS NOT NULL ORDER BY 1"),
        variable("merch", "Мерчант",
                 "SELECT DISTINCT merch FROM scores WHERE merch IS NOT NULL "
                 "AND ('__all' IN ($state) OR us_state IN ($state)) ORDER BY 1"),
    ]
    return dashboard("fraud-business", "Фрод по штатам и мерчантам", panels,
                     "Срез из PostgreSQL (таблица scores) с фильтрами по штату и мерчанту",
                     refresh="10s", templating=templating, annotations=[MODEL_SWITCH], tags=["postgresql"])


def main():
    OUT.mkdir(exist_ok=True)
    for name, build in [("scoring", scoring_dashboard), ("writer", writer_dashboard),
                        ("system", system_dashboard), ("business", business_dashboard)]:
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
