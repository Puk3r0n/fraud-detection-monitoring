CREATE TABLE IF NOT EXISTS scores (
    transaction_id TEXT PRIMARY KEY,
    score DOUBLE PRECISION NOT NULL,
    fraud_flag SMALLINT NOT NULL,
    model_version TEXT NOT NULL,
    us_state TEXT,
    merch TEXT,
    cat_id TEXT,
    amount DOUBLE PRECISION,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS scores_scored_at_idx ON scores (scored_at DESC);
CREATE INDEX IF NOT EXISTS scores_state_merch_idx ON scores (us_state, merch, scored_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana') THEN
        CREATE ROLE grafana LOGIN PASSWORD 'grafana';
    END IF;
END
$$;
GRANT SELECT ON scores TO grafana;

CREATE TABLE IF NOT EXISTS labeled_transactions (
    transaction_time TIMESTAMP NOT NULL,
    merch TEXT,
    cat_id TEXT,
    amount DOUBLE PRECISION,
    name_1 TEXT,
    name_2 TEXT,
    gender TEXT,
    street TEXT,
    one_city TEXT,
    us_state TEXT,
    post_code INTEGER,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    population_city INTEGER,
    jobs TEXT,
    merchant_lat DOUBLE PRECISION,
    merchant_lon DOUBLE PRECISION,
    target SMALLINT
);
CREATE INDEX IF NOT EXISTS labeled_transactions_time_idx ON labeled_transactions (transaction_time);

CREATE TABLE IF NOT EXISTS training_state (
    id INT PRIMARY KEY,
    window_start DATE NOT NULL,
    window_end DATE NOT NULL,
    next_batch_month DATE NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
