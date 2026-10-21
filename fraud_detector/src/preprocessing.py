import json
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TARGET_COL = "target"
CODE_COLS = ["cat_id", "us_state", "gender"]
TE_COLS = ["merch"]
CLIENT_KEY_COLS = ["name_1", "name_2", "street", "post_code"]
TE_SMOOTHING = 50

FEATURES = [
    "amount_log", "hour", "day_of_week", "is_night", "distance_km",
    "population_log", "amount_to_client_mean",
    *[f"{c}_code" for c in CODE_COLS],
    *[f"{c}_te" for c in TE_COLS],
    *[f"{c}_freq" for c in TE_COLS],
]
CATEGORICAL_FEATURES = [f"{c}_code" for c in CODE_COLS]


def _client_key(df):
    return df[CLIENT_KEY_COLS].astype(str).agg("|".join, axis=1)


def _haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def fit_preprocessor(train):
    prior = float(train[TARGET_COL].mean())
    params = {"prior": prior, "codes": {}, "te": {}, "freq": {}}

    for col in CODE_COLS:
        values = sorted(train[col].dropna().astype(str).unique())
        params["codes"][col] = {v: i for i, v in enumerate(values)}

    for col in TE_COLS:
        stats = train.groupby(col)[TARGET_COL].agg(["sum", "count"])
        te = (stats["sum"] + prior * TE_SMOOTHING) / (stats["count"] + TE_SMOOTHING)
        params["te"][col] = te.to_dict()
        params["freq"][col] = (stats["count"] / len(train)).to_dict()

    client = train.assign(client=_client_key(train)).groupby("client")["amount"]
    params["client_mean_amount"] = client.mean().to_dict()
    params["global_mean_amount"] = float(train["amount"].mean())
    params["median_population"] = float(train["population_city"].median())

    logger.info("Preprocessor fitted on %d rows", len(train))
    return params


def transform(df, params):
    df = df.copy()
    out = pd.DataFrame(index=df.index)

    amount = pd.to_numeric(df["amount"], errors="coerce").fillna(params["global_mean_amount"])
    out["amount_log"] = np.log1p(amount.clip(lower=0))

    ts = pd.to_datetime(df["transaction_time"], errors="coerce")
    out["hour"] = ts.dt.hour.fillna(-1)
    out["day_of_week"] = ts.dt.dayofweek.fillna(-1)
    out["is_night"] = out["hour"].isin([22, 23, 0, 1, 2, 3]).astype(int)

    coords = df[["lat", "lon", "merchant_lat", "merchant_lon"]].apply(pd.to_numeric, errors="coerce")
    out["distance_km"] = _haversine_km(coords["lat"], coords["lon"],
                                       coords["merchant_lat"], coords["merchant_lon"]).fillna(-1)

    population = pd.to_numeric(df["population_city"], errors="coerce").fillna(params["median_population"])
    out["population_log"] = np.log1p(population)

    client = _client_key(df)
    client_mean = client.map(params["client_mean_amount"]).fillna(params["global_mean_amount"])
    out["amount_to_client_mean"] = amount / client_mean

    for col in CODE_COLS:
        out[f"{col}_code"] = df[col].astype(str).map(params["codes"][col]).fillna(-1).astype(int)

    for col in TE_COLS:
        out[f"{col}_te"] = df[col].map(params["te"][col]).fillna(params["prior"])
        out[f"{col}_freq"] = df[col].map(params["freq"][col]).fillna(0.0)

    return out[FEATURES]


def save_params(params, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False)


def load_params(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)
