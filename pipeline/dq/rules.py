from dataclasses import dataclass

CATEGORIES = (
    "entertainment", "food_dining", "gas_transport", "grocery_net", "grocery_pos",
    "health_fitness", "home", "kids_pets", "misc_net", "misc_pos", "personal_care",
    "shopping_net", "shopping_pos", "travel",
)
MAX_AMOUNT = 100_000
MIN_MONTH_ROWS = 10_000
FRAUD_RATE_RANGE = (0.001, 0.03)
MAX_DUPLICATE_SHARE = 0.01


@dataclass(frozen=True)
class Rule:
    name: str
    severity: str
    description: str
    sql: str


RULES = [
    Rule(
        "not_null_key_columns", "critical",
        "В ключевых колонках (время, сумма, target, мерчант, категория, координаты) нет NULL",
        """
        SELECT count(*) FILTER (WHERE transaction_time IS NULL OR amount IS NULL OR target IS NULL
                                   OR merch IS NULL OR cat_id IS NULL OR lat IS NULL OR lon IS NULL
                                   OR merchant_lat IS NULL OR merchant_lon IS NULL),
               count(*)
        FROM labeled_transactions
        """,
    ),
    Rule(
        "target_is_binary", "critical",
        "target принимает только значения 0 и 1",
        "SELECT count(*) FILTER (WHERE target NOT IN (0, 1)), count(*) FROM labeled_transactions",
    ),
    Rule(
        "amount_in_range", "critical",
        f"Сумма транзакции больше 0 и не больше {MAX_AMOUNT}",
        f"SELECT count(*) FILTER (WHERE amount <= 0 OR amount > {MAX_AMOUNT}), count(*) FROM labeled_transactions",
    ),
    Rule(
        "coordinates_valid", "critical",
        "Широта клиента и мерчанта в [-90, 90], долгота в [-180, 180]",
        """
        SELECT count(*) FILTER (WHERE lat NOT BETWEEN -90 AND 90 OR merchant_lat NOT BETWEEN -90 AND 90
                                   OR lon NOT BETWEEN -180 AND 180 OR merchant_lon NOT BETWEEN -180 AND 180),
               count(*)
        FROM labeled_transactions
        """,
    ),
    Rule(
        "no_month_gaps", "critical",
        "Между первым и последним месяцем витрины нет пропущенных месяцев",
        """
        WITH m AS (SELECT DISTINCT date_trunc('month', transaction_time) AS month FROM labeled_transactions)
        SELECT (SELECT count(*) FROM generate_series((SELECT min(month) FROM m), (SELECT max(month) FROM m),
                                                     interval '1 month'))
               - (SELECT count(*) FROM m),
               (SELECT count(*) FROM m)
        """,
    ),
    Rule(
        "category_in_domain", "warning",
        "cat_id входит в справочник из 14 категорий обучающих данных",
        f"""
        SELECT count(*) FILTER (WHERE cat_id NOT IN ({', '.join(f"'{c}'" for c in CATEGORIES)})), count(*)
        FROM labeled_transactions
        """,
    ),
    Rule(
        "gender_in_domain", "warning",
        "gender принимает значения M или F",
        "SELECT count(*) FILTER (WHERE gender NOT IN ('M', 'F') OR gender IS NULL), count(*) FROM labeled_transactions",
    ),
    Rule(
        "monthly_volume", "warning",
        f"В каждом месяце не меньше {MIN_MONTH_ROWS} размеченных транзакций",
        f"""
        SELECT count(*) FILTER (WHERE rows < {MIN_MONTH_ROWS}), count(*)
        FROM (SELECT count(*) AS rows FROM labeled_transactions GROUP BY date_trunc('month', transaction_time)) t
        """,
    ),
    Rule(
        "monthly_fraud_rate", "warning",
        f"Доля фрода в каждом месяце в диапазоне {FRAUD_RATE_RANGE[0]:.1%} - {FRAUD_RATE_RANGE[1]:.0%}",
        f"""
        SELECT count(*) FILTER (WHERE rate NOT BETWEEN {FRAUD_RATE_RANGE[0]} AND {FRAUD_RATE_RANGE[1]}), count(*)
        FROM (SELECT avg(target) AS rate FROM labeled_transactions GROUP BY date_trunc('month', transaction_time)) t
        """,
    ),
    Rule(
        "duplicate_share", "warning",
        f"Полных дублей строк не больше {MAX_DUPLICATE_SHARE:.0%} витрины",
        f"""
        WITH d AS (SELECT count(*) - count(DISTINCT t) AS dups, count(*) AS total FROM labeled_transactions t)
        SELECT CASE WHEN dups > total * {MAX_DUPLICATE_SHARE} THEN dups ELSE 0 END, total FROM d
        """,
    ),
]
