"""
Run this from your backend/ folder with your venv active:
    python diagnose_pipeline.py
It isolates each stage of the pipeline to show exactly where it breaks.
"""
import sys, traceback
sys.path.insert(0, ".")

import pandas as pd
from app.ml.pipeline import load_artifacts, artifacts_ready

print("=== 1. artifacts_ready() ===")
a = load_artifacts()
print("ready:", artifacts_ready())
for k, v in a.items():
    print(f"  {k:20s} -> {type(v).__name__ if v is not None else 'MISSING'}")

df = pd.DataFrame([{
    "completion_time": pd.Timestamp("2026-02-20 12:00:00"),
    "Details": "Customer Send Money to 2547XXXXXXXX Fuliza M-Pesa",
    "paid_in_raw": 0, "withdrawn_raw": 200, "amount_raw": -200,
}])

from app.ml.feature_engineering import transform_for_label, transform_for_classification, transform_for_category
from app.ml.pipeline import _predict_stage_batch

d = df.copy()
d["details_nlp"] = d["Details"]
d["transaction_label"] = "Other"

print("\n=== 2. LABEL stage ===")
try:
    X_lbl = transform_for_label(d, a["label_tfidf"])
    print("X_lbl shape:", X_lbl.shape)
    label_vals, label_confs = _predict_stage_batch(a["label_model"], X_lbl, a["label_encoder"])
    print("label:", label_vals, "confidence:", label_confs)
    d["transaction_label"] = label_vals
except Exception:
    print("LABEL STAGE FAILED:")
    traceback.print_exc()
    sys.exit(1)

print("\n=== 3. CLASSIFICATION stage ===")
try:
    X_cls = transform_for_classification(d, a["classif_tfidf"], a["label_feat_encoder"])
    print("X_cls shape:", X_cls.shape)
    classif_vals, classif_confs = _predict_stage_batch(a["classif_model"], X_cls, a["classif_encoder"])
    print("classification:", classif_vals, "confidence:", classif_confs)
    d["transaction_classification"] = classif_vals
except Exception:
    print("CLASSIFICATION STAGE FAILED:")
    traceback.print_exc()
    sys.exit(1)

print("\n=== 4. CATEGORY stage ===")
try:
    X_cat = transform_for_category(d, a["category_tfidf"], a["label_feat_encoder"], a["classif_feat_encoder"])
    print("X_cat shape:", X_cat.shape)
    cat_vals, cat_confs = _predict_stage_batch(a["category_model"], X_cat, a["category_encoder"])
    print("category:", cat_vals, "confidence:", cat_confs)
except Exception:
    print("CATEGORY STAGE FAILED:")
    traceback.print_exc()
    sys.exit(1)

print("\n=== ALL STAGES OK ===")