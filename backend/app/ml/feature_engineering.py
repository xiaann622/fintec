"""
Feature engineering — ported 1:1 from Fintech_Final_v5 (Cells 119, 138, 140, 142).

CRITICAL: feature order/count must match exactly what each joblib model was
fitted on, or sklearn will raise a shape-mismatch error (or silently score
garbage). The three models were trained with different feature widths:

  transaction_label model         -> TFIDF(label vectorizer)   + 12 extra cols
      [hour, dow, is_weekend]  (3)
      + amount block            (9)   -> 3 + 9 = 12

  transaction_classification model-> TFIDF(classif vectorizer) + 13 extra cols
      [label_encoded]           (1)
      + [hour, dow, is_weekend] (3)
      + amount block            (9)   -> 1 + 3 + 9 = 13

  transaction_category model      -> TFIDF(category vectorizer) + 14 extra cols
      [label_encoded, classification_encoded] (2)
      + [hour, dow, is_weekend]              (3)
      + amount block                         (9) -> 2 + 3 + 9 = 14

This is exactly the "14 extra features vs TF-IDF" behaviour you described for
the category model (e.g. TFIDF 1502 -> model input 1516).
"""
import numpy as np
import pandas as pd
from scipy.sparse import hstack, csr_matrix

AMOUNT_FEATURE_NAMES = [
    "log_amount", "is_micro", "is_small", "is_medium", "is_large",
    "rush_micro", "eve_small", "large_buy", "is_buy_goods",
]


def get_amount_features(d: pd.DataFrame) -> np.ndarray:
    """Build amount + interaction feature matrix. Returns dense ndarray (n, 9)."""
    if "amount_raw" in d.columns:
        amt_raw = pd.to_numeric(d["amount_raw"], errors="coerce").fillna(0)
    elif "amount" in d.columns:
        amt_raw = pd.to_numeric(d["amount"], errors="coerce").fillna(0)
    elif "paid_in_raw" in d.columns and "withdrawn_raw" in d.columns:
        amt_raw = (
            pd.to_numeric(d["paid_in_raw"], errors="coerce").fillna(0)
            - pd.to_numeric(d["withdrawn_raw"], errors="coerce").fillna(0)
        )
    else:
        amt_raw = pd.Series(np.zeros(len(d)), index=d.index)

    amt_abs = amt_raw.abs()
    log_amt = np.log1p(amt_abs).values.reshape(-1, 1)

    is_micro = (amt_abs < 100).astype(int).values.reshape(-1, 1)
    is_small = ((amt_abs >= 100) & (amt_abs < 500)).astype(int).values.reshape(-1, 1)
    is_medium = ((amt_abs >= 500) & (amt_abs < 2000)).astype(int).values.reshape(-1, 1)
    is_large = (amt_abs >= 2000).astype(int).values.reshape(-1, 1)

    dt = pd.to_datetime(d["completion_time"], errors="coerce")
    is_morning = ((dt.dt.hour >= 6) & (dt.dt.hour <= 9)).fillna(False).astype(int).values
    is_evening = ((dt.dt.hour >= 17) & (dt.dt.hour <= 21)).fillna(False).astype(int).values

    rush_micro = ((amt_abs < 100).astype(int).values & (is_morning | is_evening)).reshape(-1, 1)
    eve_small = ((amt_abs < 400).astype(int).values & is_evening).reshape(-1, 1)
    is_buy_goods = (d["transaction_label"] == "Buy Goods").astype(int).values.reshape(-1, 1)

    large_buy = (
        ((amt_abs >= 1000).astype(int).values)
        & (d["transaction_label"] == "Buy Goods").astype(int).values
    ).reshape(-1, 1)

    return np.hstack(
        [log_amt, is_micro, is_small, is_medium, is_large,
         rush_micro, eve_small, large_buy, is_buy_goods]
    )


def _time_block(d: pd.DataFrame) -> np.ndarray:
    dt = pd.to_datetime(d["completion_time"], errors="coerce")
    hour = dt.dt.hour.fillna(0).values.reshape(-1, 1)
    dow = dt.dt.dayofweek.fillna(0).values.reshape(-1, 1)
    is_weekend = (dt.dt.dayofweek >= 5).astype(int).values.reshape(-1, 1)
    return np.hstack([hour, dow, is_weekend])


def _safe_encode(label_encoder, values, fallback_name: str = "generic") -> np.ndarray:
    """
    Encodes a categorical feature column (e.g. the predicted label, used as an
    input feature to a downstream model) to match training-time encoding.

    Never raises: if `label_encoder` is missing entirely (real sklearn
    LabelEncoder .joblib not supplied — see models_store/README.md), falls
    back to a stable ordinal encoder so the pipeline still returns a result
    instead of crashing. This is a *degraded-quality* fallback, not
    equivalent to the real training-time encoding — supply the real encoder
    file for correct predictions.
    """
    if label_encoder is None:
        from app.ml.pipeline import get_fallback_encoder
        label_encoder = get_fallback_encoder(fallback_name)

    if hasattr(label_encoder, "classes_"):
        known = set(label_encoder.classes_)
        return np.array(
            [label_encoder.transform([v])[0] if v in known else 0 for v in values]
        ).reshape(-1, 1)

    # Ordinal fallback encoder (see app.ml.pipeline.OrdinalFallbackEncoder)
    return np.array([label_encoder.transform_one(v) for v in values]).reshape(-1, 1)


def _text_col(d: pd.DataFrame) -> pd.Series:
    if "details_nlp" in d.columns:
        return d["details_nlp"].fillna("")
    return d["Details"].fillna("").str.replace("\n", " ").str.strip().str.lower()


def transform_for_label(df_input: pd.DataFrame, tfidf_label_model) -> "csr_matrix":
    """TFIDF + 12 extra features -> transaction_label model input."""
    d = df_input.copy()
    X_text = tfidf_label_model.transform(_text_col(d))
    X_num = csr_matrix(
        np.hstack([_time_block(d), get_amount_features(d)]).astype(float)
    )
    return hstack([X_text, X_num]).tocsr()


def transform_for_classification(
    df_input: pd.DataFrame, tfidf_classif_model, le_label_feat
) -> "csr_matrix":
    """TFIDF + 13 extra features -> transaction_classification model input."""
    d = df_input.copy()
    X_text = tfidf_classif_model.transform(_text_col(d))
    lbl = _safe_encode(le_label_feat, d["transaction_label"], fallback_name="label_feat")
    X_num = csr_matrix(
        np.hstack([lbl, _time_block(d), get_amount_features(d)]).astype(float)
    )
    return hstack([X_text, X_num]).tocsr()


def transform_for_category(
    df_input: pd.DataFrame, tfidf_category_model, le_label_feat, le_classif_feat
) -> "csr_matrix":
    """TFIDF + 14 extra features -> transaction_category model input."""
    d = df_input.copy()
    X_text = tfidf_category_model.transform(_text_col(d))
    lbl = _safe_encode(le_label_feat, d["transaction_label"], fallback_name="label_feat")
    cls = _safe_encode(le_classif_feat, d["transaction_classification"], fallback_name="classif_feat")
    X_num = csr_matrix(
        np.hstack([lbl, cls, _time_block(d), get_amount_features(d)]).astype(float)
    )
    return hstack([X_text, X_num]).tocsr()
