import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_db import Transaction, User, PredictionLog
from app.security import get_current_user
from app.schemas import PredictTextIn, PredictionResult
from app.ml.pipeline import predict_one, predict_batch, artifacts_ready

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("/status")
def model_status():
    return {"ready": artifacts_ready()}


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
    """Re-run predictions for transactions that were ingested before the models were loaded."""
    if not artifacts_ready():
        raise HTTPException(503, "ML models are not loaded on the server yet.")

    rows = (
        db.query(Transaction)
        .filter(Transaction.transaction_label.is_(None))
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
                              predicted_value=p["transaction_category"],
                              confidence=p["category_confidence"],
                              latency_ms=p.get("latency_ms")))
    db.commit()
    return {"updated": len(rows)}
