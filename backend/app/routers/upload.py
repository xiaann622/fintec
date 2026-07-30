import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_db import Transaction, UploadBatch, User, PredictionLog
from app.security import get_current_user
from app.config import settings
from app.ocr.extractor import extract
from app.ml.pipeline import predict_batch, artifacts_ready

logger = logging.getLogger("mpesa.upload")
router = APIRouter(prefix="/api/upload", tags=["upload"])

FILE_TYPE_MAP = {
    "csv": "csv", "xlsx": "excel", "xls": "excel",
    "pdf": "pdf", "jpg": "image", "jpeg": "image", "png": "image",
}


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in FILE_TYPE_MAP:
        raise HTTPException(400, f"Unsupported file type: .{ext}")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {settings.MAX_UPLOAD_MB}MB limit.")

    batch = UploadBatch(
        filename=file.filename, file_type=FILE_TYPE_MAP[ext],
        status="processing", uploaded_by=current_user.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    try:
        df = extract(content, file.filename)
    except Exception as e:
        batch.status = "failed"
        batch.error_message = str(e)
        db.commit()
        raise HTTPException(422, f"Could not extract transactions: {e}")

    if df.empty:
        batch.status = "failed"
        batch.error_message = "No transactions could be detected in this document."
        db.commit()
        raise HTTPException(422, "No transactions detected. Try a clearer scan or a CSV/XLSX export.")

    predictions = None
    if artifacts_ready():
        df_for_predict = df.rename(columns={"details": "Details"})
        try:
            predictions = predict_batch(df_for_predict)
        except Exception as e:
            db.rollback()  
            logger.exception("Prediction failed during upload")
            predictions = None

    rows_ok, rows_failed = 0, 0
    df = df.reset_index(drop=True)
    txns_and_preds = []  # [(Transaction, pred_dict), ...] -- staged, not yet added to session

    for i, row in enumerate(df.to_dict("records")):
        try:
            pred = predictions[i] if predictions else {}

            txn = Transaction(
                receipt_no=row.get("receipt_no"),
                completion_time=row["completion_time"] if pd_notna(row.get("completion_time")) else None,
                details=row["details"],
                details_nlp=pred.get("details_nlp"),
                paid_in=float(row.get("paid_in") or 0),
                withdrawn=float(row.get("withdrawn") or 0),
                balance=float(row["balance"]) if pd_notna(row.get("balance")) else None,
                amount=float(row.get("amount") or 0),
                amount_raw=float(row.get("amount_raw") or 0),
                transaction_label=pred.get("transaction_label"),
                transaction_classification=pred.get("transaction_classification"),
                transaction_category=pred.get("transaction_category"),
                label_confidence=pred.get("label_confidence"),
                classification_confidence=pred.get("classification_confidence"),
                category_confidence=pred.get("category_confidence"),
                counterparty_alias=pred.get("counterparty_alias"),
                source_file=file.filename,
                source_type=FILE_TYPE_MAP[ext],
                uploaded_by=current_user.id,
            )
            if txn.completion_time is None:
                rows_failed += 1
                continue
            txns_and_preds.append((txn, pred))
            rows_ok += 1
        except Exception as e:
            logger.warning("Row %s failed to build: %s", i, e)
            rows_failed += 1

    # Bulk-add every Transaction, then flush ONCE (not once per row) so the DB
    # assigns all primary keys in a single round trip instead of 1 per row --
    # with a networked Postgres instance, thousands of individual flushes
    # inside the loop was the single biggest contributor to slow uploads.
    db.add_all([t for t, _ in txns_and_preds])
    db.flush()

    log_entries = []
    for txn, pred in txns_and_preds:
        if not pred:
            continue
        for stage, key, conf_key in [
            ("label", "transaction_label", "label_confidence"),
            ("classification", "transaction_classification", "classification_confidence"),
            ("category", "transaction_category", "category_confidence"),
        ]:
            log_entries.append(PredictionLog(
                transaction_id=txn.id, model_stage=stage,
                predicted_value=pred.get(key) or "Unknown",
                confidence=pred.get(conf_key),
                latency_ms=pred.get("latency_ms"),
            ))
        # Surface per-row prediction failures somewhere queryable -- see
        # GET /api/monitoring/prediction-errors. Previously the only trace
        # was a server-log exception, invisible without hosting-platform
        # log access. predicted_value is String(60), truncate defensively.
        if pred.get("error"):
            log_entries.append(PredictionLog(
                transaction_id=txn.id, model_stage="error",
                predicted_value=str(pred["error"])[:60],
                confidence=None,
                latency_ms=pred.get("latency_ms"),
            ))
    db.add_all(log_entries)

    batch.rows_ingested = rows_ok
    batch.rows_failed = rows_failed
    batch.status = "completed"
    db.commit()

    return {
        "batch_id": batch.id,
        "filename": file.filename,
        "rows_ingested": rows_ok,
        "rows_failed": rows_failed,
        "predictions_applied": predictions is not None,
        "message": (
            "Upload processed and classified successfully."
            if predictions is not None
            else "Upload ingested. ML models are not yet loaded on the server, "
                 "so rows were stored without predictions — run /api/predictions/backfill later."
        ),
    }


def pd_notna(v):
    import pandas as pd
    return v is not None and pd.notna(v)