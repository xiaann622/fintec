import datetime
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_db import Transaction, UploadBatch, PredictionLog, User
from app.security import get_current_user
from app.ml.pipeline import artifacts_ready

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    total_txns = db.query(func.count(Transaction.id)).scalar() or 0
    unclassified = db.query(func.count(Transaction.id)).filter(
        Transaction.transaction_label.is_(None)
    ).scalar() or 0
    total_uploads = db.query(func.count(UploadBatch.id)).scalar() or 0
    failed_uploads = db.query(func.count(UploadBatch.id)).filter(
        UploadBatch.status == "failed"
    ).scalar() or 0
    avg_conf = db.query(func.avg(Transaction.category_confidence)).scalar()

    return {
        "models_ready": artifacts_ready(),
        "total_transactions": total_txns,
        "unclassified_transactions": unclassified,
        "classification_coverage_pct": round(
            100 * (total_txns - unclassified) / total_txns, 1
        ) if total_txns else 0,
        "total_uploads": total_uploads,
        "failed_uploads": failed_uploads,
        "avg_category_confidence": round(float(avg_conf), 3) if avg_conf else None,
    }


@router.get("/confidence-trend")
def confidence_trend(
    days: int = 30, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    rows = (
        db.query(
            func.date(PredictionLog.created_at).label("day"),
            PredictionLog.model_stage,
            func.avg(PredictionLog.confidence).label("avg_confidence"),
            func.count(PredictionLog.id).label("count"),
        )
        .filter(PredictionLog.created_at >= since)
        .group_by("day", PredictionLog.model_stage)
        .order_by("day")
        .all()
    )
    return [
        {"day": str(r.day), "stage": r.model_stage,
         "avg_confidence": float(r.avg_confidence or 0), "count": r.count}
        for r in rows
    ]


@router.get("/low-confidence")
def low_confidence(
    threshold: float = 0.55, limit: int = 50,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Transactions the model is least sure about — useful for manual review / active learning."""
    rows = (
        db.query(Transaction)
        .filter(Transaction.category_confidence.isnot(None))
        .filter(Transaction.category_confidence < threshold)
        .order_by(Transaction.category_confidence.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": t.id, "details": t.details, "amount": t.amount,
            "transaction_category": t.transaction_category,
            "category_confidence": t.category_confidence,
            "completion_time": t.completion_time,
        }
        for t in rows
    ]


@router.get("/prediction-errors")
def prediction_errors(
    limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    Recent per-row prediction failures (model_stage='error'), written by
    the upload/backfill routers whenever a row's prediction dict came back
    with pred["error"] set -- see app/ml/pipeline.py's row-by-row fallback.
    Direct way to see WHY a batch of rows ended up unclassified without
    needing hosting-platform log access.
    """
    rows = (
        db.query(PredictionLog, Transaction.details)
        .join(Transaction, Transaction.id == PredictionLog.transaction_id)
        .filter(PredictionLog.model_stage == "error")
        .order_by(PredictionLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "transaction_id": log.transaction_id,
            "details": details,
            "error": log.predicted_value,
            "created_at": log.created_at,
        }
        for log, details in rows
    ]


@router.get("/upload-batches")
def upload_batches(
    limit: int = 20, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    rows = (
        db.query(UploadBatch).order_by(UploadBatch.created_at.desc()).limit(limit).all()
    )
    return [
        {
            "id": b.id, "filename": b.filename, "file_type": b.file_type,
            "rows_ingested": b.rows_ingested, "rows_failed": b.rows_failed,
            "status": b.status, "created_at": b.created_at,
        }
        for b in rows
    ]


@router.get("/category-drift")
def category_drift(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Compares category mix in the last 30 days vs the prior 30 days, to flag behavioural drift."""
    now = datetime.datetime.utcnow()
    recent_start = now - datetime.timedelta(days=30)
    prior_start = now - datetime.timedelta(days=60)

    def _dist(start, end):
        rows = (
            db.query(Transaction.transaction_category, func.count(Transaction.id))
            .filter(Transaction.completion_time >= start, Transaction.completion_time < end)
            .group_by(Transaction.transaction_category).all()
        )
        total = sum(r[1] for r in rows) or 1
        return {(r[0] or "Unclassified"): round(100 * r[1] / total, 2) for r in rows}

    recent = _dist(recent_start, now)
    prior = _dist(prior_start, recent_start)
    cats = set(recent) | set(prior)
    return [
        {"category": c, "recent_pct": recent.get(c, 0), "prior_pct": prior.get(c, 0),
         "delta": round(recent.get(c, 0) - prior.get(c, 0), 2)}
        for c in cats
    ]