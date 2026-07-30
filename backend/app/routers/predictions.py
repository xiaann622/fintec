import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models_db import Transaction, User, PredictionLog
from app.security import get_current_user
from app.schemas import PredictTextIn, PredictionResult
from app.config import settings
from app.ml.pipeline import predict_one, predict_batch, artifacts_ready, load_artifacts

router = APIRouter(prefix="/api/predictions", tags=["predictions"])

_REQUIRED_ARTIFACTS = (
    "label_model", "label_tfidf", "classif_model",
    "classif_tfidf", "category_model", "category_tfidf",
)


@router.get("/status")
def model_status():
    """
    Was `{"ready": bool}` -- which is exactly why the "everything is
    Unclassified" failure mode was hard to diagnose from outside: a
    misconfigured MODELS_DIR (see app/config.py's _resolve_models_dir)
    silently produced `ready: false` with no indication of *why* or *where
    the app was even looking*. Now returns the resolved directory and
    exactly which .joblib artifacts weren't found there.
    """
    a = load_artifacts()
    missing = [k for k in _REQUIRED_ARTIFACTS if a.get(k) is None]
    return {
        "ready": len(missing) == 0,
        "models_dir": settings.MODELS_DIR,
        "missing_artifacts": missing,
    }


@router.post("/predict", response_model=PredictionResult)
def predict_single(payload: PredictTextIn, current_user: User = Depends(get_current_user)):
    if not artifacts_ready():
        raise HTTPException(503, "ML models are not loaded on the server yet.")
    result = predict_one(
        details=payload.details,
        completion_time=payload.completion_time,
        paid_in=payload.paid_in,
        withdrawn=payload.withdrawn,
    )
    return result


@router.post("/backfill")
def backfill_predictions(
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Re-run predictions for transactions that were never successfully
    classified. Two cases:
      1. transaction_label IS NULL -- rows ingested while artifacts_ready()
         was False (models not loaded / not found at MODELS_DIR at upload
         time), or a row whose prediction failed after the pipeline.py fix
         that stops writing the literal string "Unclassified".
      2. transaction_label == 'Unclassified' -- rows from BEFORE that fix,
         whose failed prediction stored the literal string "Unclassified"
         instead of NULL. The old `IS NULL`-only filter could never find or
         retry these; widened so existing affected rows get picked up too.
    """
    if not artifacts_ready():
        raise HTTPException(503, "ML models are not loaded on the server yet.")

    rows = (
        db.query(Transaction)
        .filter(or_(
            Transaction.transaction_label.is_(None),
            Transaction.transaction_label == "Unclassified",
        ))
        .limit(limit)
        .all()
    )
    if not rows:
        return {"updated": 0}

    df = pd.DataFrame([{
        "completion_time": r.completion_time,
        "Details": r.details,
        "amount_raw": r.amount_raw or r.amount or 0,
        "paid_in_raw": r.paid_in or 0,
        "withdrawn_raw": r.withdrawn or 0,
    } for r in rows])

    preds = predict_batch(df)
    still_failing = 0
    for r, p in zip(rows, preds):
        r.details_nlp = p["details_nlp"]
        r.transaction_label = p["transaction_label"]
        r.transaction_classification = p["transaction_classification"]
        r.transaction_category = p["transaction_category"]
        r.label_confidence = p["label_confidence"]
        r.classification_confidence = p["classification_confidence"]
        r.category_confidence = p["category_confidence"]
        r.counterparty_alias = p.get("counterparty_alias")
        db.add(PredictionLog(transaction_id=r.id, model_stage="category",
                              predicted_value=p["transaction_category"] or "Unknown",
                              confidence=p["category_confidence"],
                              latency_ms=p.get("latency_ms")))
        if p.get("error"):
            still_failing += 1
            db.add(PredictionLog(transaction_id=r.id, model_stage="error",
                                  predicted_value=str(p["error"])[:60],
                                  confidence=None, latency_ms=p.get("latency_ms")))
    db.commit()
    return {"updated": len(rows), "still_failing": still_failing}