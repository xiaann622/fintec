"""
Loads the trained artifacts exported from Fintech_Final_v5.ipynb and runs the
full 3-stage inference pipeline in the exact order used at training time:

    1. transaction_label            (TFIDF + 12 features)
    2. transaction_classification   (TFIDF + 13 features, uses label as input)
    3. transaction_category         (TFIDF + 14 features, uses label + classification)

Drop your exported .joblib files into backend/models_store/ using these
default names (override paths via env vars if yours differ):

  transaction_label_model.joblib
  transaction_label_tfidf.joblib
  transaction_label_encoder.joblib            (optional — omit if model outputs strings)

  transaction_classification_model.joblib
  transaction_classification_tfidf.joblib
  transaction_classification_encoder.joblib   (optional)

  transaction_category_model.joblib
  transaction_category_tfidf.joblib
  transaction_category_encoder.joblib         (optional)

Stage 3 (transaction_category) also applies a deterministic keyword-override
layer ported from the notebook's post_process_predictions() — see
app/ml/category_overrides.py for the full rationale, and
Settings.ENABLE_CATEGORY_OVERRIDES to toggle it off.
"""
import logging
import os
import time
from typing import Optional

import joblib
import numpy as np
import pandas as pd

from app.config import settings
from app.ml.preprocessing import preprocess_text
from app.ml.feature_engineering import (
    transform_for_label, transform_for_classification, transform_for_category,
)
from app.ml.category_overrides import post_process_category, extract_business_name, apply_classification_category_rule
from app.ml.classification_overrides import post_process_classification
from app.ml.label_overrides import post_process_label

logger = logging.getLogger("mpesa.ml")

_ARTIFACTS = {}
_LOADED = False
_FALLBACK_ENCODERS = {}


class OrdinalFallbackEncoder:
    """
    Safety net used only when a real training-time LabelEncoder .joblib
    wasn't supplied (see models_store/README.md). Assigns a stable integer
    to each distinct string the first time it's seen in this process, so the
    pipeline degrades gracefully instead of raising. Not equivalent to the
    original training encoding — supply the real encoder file for accurate
    predictions.
    """

    def __init__(self):
        self._map = {}

    def transform_one(self, value) -> int:
        if value not in self._map:
            self._map[value] = len(self._map)
        return self._map[value]


def get_fallback_encoder(name: str) -> OrdinalFallbackEncoder:
    if name not in _FALLBACK_ENCODERS:
        logger.warning(
            "No trained LabelEncoder found for '%s' — using a degraded ordinal "
            "fallback so the app keeps working. See models_store/README.md.", name
        )
        _FALLBACK_ENCODERS[name] = OrdinalFallbackEncoder()
    return _FALLBACK_ENCODERS[name]


def _p(name: str) -> str:
    return os.path.join(settings.MODELS_DIR, name)


def _try_load(*candidates):
    for c in candidates:
        path = _p(c)
        if os.path.exists(path):
            return joblib.load(path)
    return None


def load_artifacts(force: bool = False):
    global _LOADED
    if _LOADED and not force:
        return _ARTIFACTS

    _ARTIFACTS["label_model"] = _try_load(
        "transaction_label_model.joblib",
        "transaction_label_RandomForestClassifier_Label.joblib",
    )
    _ARTIFACTS["label_tfidf"] = _try_load(
        "transaction_label_tfidf.joblib",
        "transaction_label_tfidf_vectorizer.joblib",
    )
    _ARTIFACTS["label_encoder"] = _try_load(
    "transaction_label_le_target.joblib",
    "transaction_label_encoder.joblib",
    "le_label_target.joblib",
    )

    _ARTIFACTS["classif_model"] = _try_load(
        "transaction_classification_model.joblib",
        "transaction_classification_RandomForestClassifier_Classif.joblib",
        "transaction_classification_LinearSVC_Classif.joblib",
    )
    _ARTIFACTS["classif_tfidf"] = _try_load(
        "transaction_classification_tfidf.joblib",
        "transaction_classification_tfidf_vectorizer.joblib",
    )
    _ARTIFACTS["classif_encoder"] = _try_load(
    "transaction_classification_le_target.joblib",
    "transaction_classification_encoder.joblib",
    "le_classif_target.joblib",
    )

    # label encoder used as an INPUT FEATURE to the classification model
    _ARTIFACTS["label_feat_encoder"] = _try_load(
    "transaction_classification_le_label_feature.joblib",
    "label_feature_encoder.joblib",
    "le_label_feat_for_classif.joblib",
    ) or _ARTIFACTS["label_encoder"]


    _ARTIFACTS["category_model"] = _try_load(
        "transaction_category_model.joblib",
        "transaction_category_LogisticRegression.joblib",
    )
    _ARTIFACTS["category_tfidf"] = _try_load(
        "transaction_category_tfidf.joblib",
        "transaction_category_tfidf_vectorizer.joblib",
    )
    _ARTIFACTS["category_encoder"] = _try_load(
    "transaction_category_le_target.joblib",
    "transaction_category_encoder.joblib",
    )

    _ARTIFACTS["classif_feat_encoder"] = _try_load(
    "transaction_category_le_classif_feature.joblib",
    "classif_feature_encoder.joblib",
    "le_classif_feat.joblib",
    ) or _ARTIFACTS["classif_encoder"]

    missing = [k for k in ("label_model", "label_tfidf", "classif_model",
                            "classif_tfidf", "category_model", "category_tfidf")
               if _ARTIFACTS.get(k) is None]
    if missing:
        logger.warning(
            "ML artifacts missing (place .joblib files in %s): %s",
            settings.MODELS_DIR, missing,
        )

    # Force single-threaded prediction on any ensemble model (e.g.
    # RandomForestClassifier) that was pickled with n_jobs=-1 or n_jobs>1.
    # Under uvicorn --reload on Windows, the server itself already runs as
    # a spawned subprocess; letting joblib's loky backend spawn *further*
    # worker subprocesses for every .predict() call is a well-known source
    # of silent failures / pickling errors on Windows -- and it fails the
    # same way on every single call, which is exactly the "every row comes
    # back Unclassified" symptom. Single-threaded is negligibly slower here
    # since predict_batch already runs one predict() call for the whole
    # batch, not per row.
    for key in ("label_model", "classif_model", "category_model"):
        model = _ARTIFACTS.get(key)
        if model is not None and hasattr(model, "n_jobs"):
            try:
                model.n_jobs = 1
            except Exception:
                pass

    _LOADED = True
    return _ARTIFACTS


def artifacts_ready() -> bool:
    a = load_artifacts()
    return all(a.get(k) is not None for k in
               ("label_model", "label_tfidf", "classif_model", "classif_tfidf",
                "category_model", "category_tfidf"))


def _predict_stage(model, X, encoder=None):
    """Runs .predict (+ .predict_proba if available) and decodes labels."""
    raw_pred = model.predict(X)
    confidence = None
    try:
        proba = model.predict_proba(X)
        confidence = float(np.max(proba, axis=1)[0])
    except Exception:
        try:
            # CalibratedClassifierCV / LinearSVC decision function fallback
            scores = model.decision_function(X)
            scores = np.atleast_2d(scores)
            confidence = float(1 / (1 + np.exp(-np.max(scores))))
        except Exception:
            confidence = None

    value = raw_pred[0]
    # If model output is numeric/encoded and we have an encoder, decode it
    if encoder is not None and isinstance(value, (int, np.integer)):
        try:
            value = encoder.inverse_transform([value])[0]
        except Exception:
            pass
    return str(value), confidence


def predict_one(details: str, completion_time=None, paid_in: float = 0.0,
                 withdrawn: float = 0.0) -> dict:
    return predict_batch(pd.DataFrame([{
        "completion_time": completion_time or pd.Timestamp.utcnow(),
        "Details": details,
        "paid_in_raw": paid_in,
        "withdrawn_raw": withdrawn,
        "amount_raw": paid_in - withdrawn,
    }]))[0]


def _predict_stage_batch(model, X, encoder=None):
    n = X.shape[0]
    raw_pred = model.predict(X)

    confidence = np.array([None] * n, dtype=object)
    try:
        proba = model.predict_proba(X)
        confidence = np.max(proba, axis=1)
    except Exception:
        try:
            scores = np.atleast_2d(model.decision_function(X))
            if scores.shape[0] != n and scores.shape[1] == n:
                scores = scores.T
            confidence = 1 / (1 + np.exp(-np.max(scores, axis=1)))
        except Exception:
            pass

    values = raw_pred
    if encoder is not None and len(values) and isinstance(values[0], (int, np.integer)):
        try:
            values = encoder.inverse_transform(values)
        except Exception:
            pass
    return np.array([str(v) for v in values]), confidence


def _predict_batch_row_by_row(d: pd.DataFrame, a: dict) -> list:
    results = []
    for i in range(len(d)):
        row_df = d.iloc[[i]].copy()
        try:
            X_lbl = transform_for_label(row_df, a["label_tfidf"])
            label_val_raw, label_conf = _predict_stage(a["label_model"], X_lbl, a["label_encoder"])

            if settings.ENABLE_LABEL_OVERRIDES:
                label_val, label_override_applied = post_process_label(label_val_raw, row_df["Details"].iloc[0])
            else:
                label_val, label_override_applied = label_val_raw, False
            row_df["transaction_label"] = label_val  # corrected label feeds downstream stages too

            X_cls = transform_for_classification(row_df, a["classif_tfidf"], a["label_feat_encoder"])
            classif_val_raw, classif_conf = _predict_stage(a["classif_model"], X_cls, a["classif_encoder"])
            if settings.ENABLE_CLASSIFICATION_OVERRIDES:
                classif_val, classif_override_applied = post_process_classification(
                    classif_val_raw, row_df["Details"].iloc[0]
                )
            else:
                classif_val, classif_override_applied = classif_val_raw, False
            row_df["transaction_classification"] = classif_val

            X_cat = transform_for_category(
                row_df, a["category_tfidf"], a["label_feat_encoder"], a["classif_feat_encoder"]
            )
            cat_val_raw, cat_conf = _predict_stage(a["category_model"], X_cat, a["category_encoder"])

            business_name = extract_business_name(row_df["Details"].iloc[0])
            if settings.ENABLE_CATEGORY_OVERRIDES:
                cat_val, applied_1 = apply_classification_category_rule(cat_val_raw, classif_val)
                cat_val, applied_2 = post_process_category(cat_val, row_df["Details"].iloc[0])
                override_applied = applied_1 or applied_2
            else:
                cat_val, override_applied = cat_val_raw, False

            results.append({
                "details": row_df["Details"].iloc[0],
                "details_nlp": row_df["details_nlp"].iloc[0],
                "transaction_label": label_val,
                "transaction_label_raw_model": label_val_raw,
                "label_override_applied": label_override_applied,
                "transaction_classification": classif_val,
                "transaction_classification_raw_model": classif_val_raw,
                "classification_override_applied": classif_override_applied,
                "transaction_category": cat_val,
                "transaction_category_raw_model": cat_val_raw,
                "category_override_applied": override_applied,
                "counterparty_alias": business_name or None,
                "label_confidence": round(label_conf, 4) if label_conf is not None else None,
                "classification_confidence": round(classif_conf, 4) if classif_conf is not None else None,
                "category_confidence": round(cat_conf, 4) if cat_conf is not None else None,
            })
        except Exception as e:
            logger.exception(
                "Prediction failed for row %s\nDetails: %s",
                i,
                row_df["Details"].iloc[0] if "Details" in row_df.columns else "?",
            )
            # FIX: this used to store the literal string "Unclassified" for
            # transaction_label/classification/category on failure. That's
            # actively harmful: (1) frontend/js/transactions.js renders
            # `t.transaction_label || "—"`, so a real null shows as an
            # honest "—" but the string "Unclassified" renders as if it
            # were a legitimate model prediction, indistinguishable from
            # real data; (2) it permanently poisons the label/
            # classification/category filter dropdowns with a fake value;
            # (3) most importantly, POST /api/predictions/backfill only
            # re-queries rows WHERE transaction_label IS NULL, so a row
            # that failed this way could never be retried automatically
            # once the underlying error (e.g. the n_jobs/Windows-
            # multiprocessing issue fixed above, or any other transient
            # failure) was fixed. None keeps these rows honestly
            # "unpredicted" and backfill-eligible. The real exception is
            # preserved in "error" for the caller to log/persist.
            results.append({
                "details": row_df["Details"].iloc[0] if "Details" in row_df.columns else "",
                "details_nlp": row_df["details_nlp"].iloc[0] if "details_nlp" in row_df.columns else "",
                "transaction_label": None,
                "transaction_classification": None,
                "transaction_category": None,
                "transaction_category_raw_model": None,
                "category_override_applied": False,
                "counterparty_alias": None,
                "label_confidence": None,
                "classification_confidence": None,
                "category_confidence": None,
                "error": str(e),
            })
    return results


def predict_batch(df_input: pd.DataFrame) -> list:
    """
    df_input needs columns: completion_time, Details, amount_raw
    (paid_in_raw / withdrawn_raw optional).
    Returns a list of dicts, one per row, each with label/classification/
    category predictions + confidences + latency.

    Runs all three stages VECTORIZED across the entire batch (one
    model.predict() call per stage, not per row) since transform_for_*
    already builds a full (n_rows x n_features) matrix. Looping per-row was
    pure overhead: each RandomForest .predict() call pays a fixed 1s+ cost
    to spin up its parallel backend, so a 3,700-row upload could take over
    an hour in the old per-row loop vs. a few seconds batched.
    """
    a = load_artifacts()
    if not artifacts_ready():
        raise RuntimeError(
            "ML models are not loaded. Place your exported .joblib files in "
            f"{settings.MODELS_DIR} (see README for required filenames)."
        )

    t0 = time.time()
    d = df_input.copy().reset_index(drop=True)
    if "Details" not in d.columns and "details" in d.columns:
        d["Details"] = d["details"]
    d["details_nlp"] = d["Details"].apply(preprocess_text)
    if "amount_raw" not in d.columns:
        d["amount_raw"] = d.get("paid_in_raw", 0) - d.get("withdrawn_raw", 0)

    n = len(d)
    d["transaction_label"] = "Other"  # placeholder required by the amount-feature block

    try:
        X_lbl = transform_for_label(d, a["label_tfidf"])
        label_vals_raw, label_confs = _predict_stage_batch(a["label_model"], X_lbl, a["label_encoder"])

        if settings.ENABLE_LABEL_OVERRIDES:
            label_vals = []
            label_override_applied = []
            for i in range(n):
                final_label, applied = post_process_label(label_vals_raw[i], d["Details"].iloc[i])
                label_vals.append(final_label)
                label_override_applied.append(applied)
            label_vals = np.array(label_vals)
        else:
            label_vals = label_vals_raw
            label_override_applied = [False] * n

        d["transaction_label"] = label_vals  # corrected label feeds downstream stages too

        X_cls = transform_for_classification(d, a["classif_tfidf"], a["label_feat_encoder"])
        classif_vals_raw, classif_confs = _predict_stage_batch(a["classif_model"], X_cls, a["classif_encoder"])

        if settings.ENABLE_CLASSIFICATION_OVERRIDES:
            classif_vals = []
            classif_override_applied = []
            for i in range(n):
                final_c, applied = post_process_classification(
                    classif_vals_raw[i], d["Details"].iloc[i]
                )
                classif_vals.append(final_c)
                classif_override_applied.append(applied)
            classif_vals = np.array(classif_vals)
        else:
            classif_vals = classif_vals_raw
            classif_override_applied = [False] * n

        d["transaction_classification"] = classif_vals

        X_cat = transform_for_category(
            d, a["category_tfidf"], a["label_feat_encoder"], a["classif_feat_encoder"]
        )
        cat_vals_raw, cat_confs = _predict_stage_batch(a["category_model"], X_cat, a["category_encoder"])

        results = []
        for i in range(n):
            details_i = d["Details"].iloc[i]
            business_name = extract_business_name(details_i)
            if settings.ENABLE_CATEGORY_OVERRIDES:
                cat_val, applied_1 = apply_classification_category_rule(cat_vals_raw[i], classif_vals[i])
                cat_val, applied_2 = post_process_category(cat_val, details_i)
                override_applied = applied_1 or applied_2
            else:
                cat_val, override_applied = cat_vals_raw[i], False

            lc, cc, gc = label_confs[i], classif_confs[i], cat_confs[i]
            results.append({
                "details": details_i,
                "details_nlp": d["details_nlp"].iloc[i],
                "transaction_label": label_vals[i],
                "transaction_label_raw_model": label_vals_raw[i],
                "label_override_applied": label_override_applied[i],
                "transaction_classification": classif_vals[i],
                "transaction_classification_raw_model": classif_vals_raw[i],
                "classification_override_applied": classif_override_applied[i],
                "transaction_category": cat_val,
                "transaction_category_raw_model": cat_vals_raw[i],
                "category_override_applied": override_applied,
                "counterparty_alias": business_name or None,
                "label_confidence": round(float(lc), 4) if lc is not None else None,
                "classification_confidence": round(float(cc), 4) if cc is not None else None,
                "category_confidence": round(float(gc), 4) if gc is not None else None,
            })
    except Exception:
        logger.exception(
            "Vectorized batch prediction failed (n=%d rows) — falling back "
            "to slower row-by-row prediction so good rows still succeed.", n
        )
        results = _predict_batch_row_by_row(d, a)

    latency_ms = (time.time() - t0) * 1000 / max(n, 1)
    for r in results:
        r["latency_ms"] = round(latency_ms, 2)
    return results