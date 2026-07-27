from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_db import Feedback, User
from app.security import get_current_user
from app.schemas import FeedbackIn, FeedbackOut

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackOut, status_code=201)
def submit_feedback(payload: FeedbackIn, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    fb = Feedback(user_id=current_user.id, **payload.model_dump())
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


@router.get("")
def list_feedback(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = db.query(Feedback).order_by(Feedback.created_at.desc()).limit(100).all()
    return [
        {"id": f.id, "subject": f.subject, "message": f.message, "rating": f.rating,
         "category": f.category, "created_at": f.created_at}
        for f in rows
    ]
