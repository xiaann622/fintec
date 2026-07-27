from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_db import Transaction, User
from app.security import get_current_user

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _apply_filters(q, label, classification, category, date_from, date_to, search):
    if label:
        q = q.filter(Transaction.transaction_label == label)
    if classification:
        q = q.filter(Transaction.transaction_classification == classification)
    if category:
        q = q.filter(Transaction.transaction_category == category)
    if date_from:
        q = q.filter(Transaction.completion_time >= date_from)
    if date_to:
        q = q.filter(Transaction.completion_time <= date_to)
    if search:
        q = q.filter(Transaction.details.ilike(f"%{search}%"))
    return q


@router.get("")
def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    label: Optional[str] = None,
    classification: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "completion_time_desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Transaction)
    q = _apply_filters(q, label, classification, category, date_from, date_to, search)

    total = q.count()
    order_col = Transaction.completion_time
    q = q.order_by(desc(order_col) if sort.endswith("desc") else order_col)
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": t.id,
                "receipt_no": t.receipt_no,
                "completion_time": t.completion_time,
                "details": t.details,
                "paid_in": t.paid_in,
                "withdrawn": t.withdrawn,
                "balance": t.balance,
                "amount": t.amount,
                "transaction_label": t.transaction_label,
                "transaction_classification": t.transaction_classification,
                "transaction_category": t.transaction_category,
                "label_confidence": t.label_confidence,
                "classification_confidence": t.classification_confidence,
                "category_confidence": t.category_confidence,
                "source_type": t.source_type,
            }
            for t in items
        ],
    }


@router.get("/{txn_id}")
def get_transaction(txn_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    t = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not t:
        raise HTTPException(404, "Transaction not found")
    return t


@router.get("/facets/labels")
def facet_labels(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (db.query(Transaction.transaction_label, func.count(Transaction.id))
            .group_by(Transaction.transaction_label).all())
    return [{"label": r[0] or "Unclassified", "count": r[1]} for r in rows]


@router.get("/facets/classifications")
def facet_classifications(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (db.query(Transaction.transaction_classification, func.count(Transaction.id))
            .group_by(Transaction.transaction_classification).all())
    return [{"classification": r[0] or "Unclassified", "count": r[1]} for r in rows]


@router.get("/facets/categories")
def facet_categories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (db.query(Transaction.transaction_category, func.count(Transaction.id))
            .group_by(Transaction.transaction_category).all())
    return [{"category": r[0] or "Unclassified", "count": r[1]} for r in rows]


@router.delete("/{txn_id}")
def delete_transaction(txn_id: int, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    t = db.query(Transaction).filter(Transaction.id == txn_id).first()
    if not t:
        raise HTTPException(404, "Transaction not found")
    db.delete(t)
    db.commit()
    return {"deleted": txn_id}
