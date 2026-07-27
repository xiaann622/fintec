from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case, extract
from sqlalchemy.orm import Session

from app.database import get_db
from app.models_db import Transaction, User
from app.security import get_current_user

router = APIRouter(prefix="/api/trends", tags=["trends"])


def _date_filtered(db: Session, date_from: Optional[str], date_to: Optional[str]):
    q = db.query(Transaction)
    if date_from:
        q = q.filter(Transaction.completion_time >= date_from)
    if date_to:
        q = q.filter(Transaction.completion_time <= date_to)
    return q


@router.get("/time-of-day")
def time_of_day(date_from: Optional[str] = None, date_to: Optional[str] = None,
                 db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Transaction volume & value by hour of day (0-23)."""
    q = _date_filtered(db, date_from, date_to)
    rows = (
        q.with_entities(
            extract("hour", Transaction.completion_time).label("hour"),
            func.count(Transaction.id).label("count"),
            func.sum(func.abs(Transaction.amount)).label("total_value"),
        )
        .group_by("hour").order_by("hour").all()
    )
    buckets = {h: {"hour": h, "count": 0, "total_value": 0.0} for h in range(24)}
    for r in rows:
        h = int(r.hour)
        buckets[h] = {"hour": h, "count": r.count, "total_value": float(r.total_value or 0)}
    return list(buckets.values())


@router.get("/weekday-vs-weekend")
def weekday_vs_weekend(date_from: Optional[str] = None, date_to: Optional[str] = None,
                        db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = _date_filtered(db, date_from, date_to)
    is_weekend = case(
        (extract("dow", Transaction.completion_time).in_([0, 6]), "Weekend"),
        else_="Weekday",
    )
    rows = (
        q.with_entities(
            is_weekend.label("bucket"),
            func.count(Transaction.id).label("count"),
            func.avg(func.abs(Transaction.amount)).label("avg_amount"),
            func.sum(func.abs(Transaction.amount)).label("total_value"),
        )
        .group_by("bucket").all()
    )
    return [
        {"bucket": r.bucket, "count": r.count,
         "avg_amount": float(r.avg_amount or 0), "total_value": float(r.total_value or 0)}
        for r in rows
    ]


@router.get("/weekly-pattern")
def weekly_pattern(date_from: Optional[str] = None, date_to: Optional[str] = None,
                    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Volume & value by day of week (Mon..Sun)."""
    q = _date_filtered(db, date_from, date_to)
    rows = (
        q.with_entities(
            extract("dow", Transaction.completion_time).label("dow"),
            func.count(Transaction.id).label("count"),
            func.sum(func.abs(Transaction.amount)).label("total_value"),
        )
        .group_by("dow").order_by("dow").all()
    )
    names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    buckets = {i: {"day": names[i], "count": 0, "total_value": 0.0} for i in range(7)}
    for r in rows:
        i = int(r.dow)
        buckets[i] = {"day": names[i], "count": r.count, "total_value": float(r.total_value or 0)}
    return [buckets[i] for i in [1, 2, 3, 4, 5, 6, 0]]  # Mon -> Sun order


@router.get("/monthly-week-progression")
def monthly_week_progression(
    year: Optional[int] = None, month: Optional[int] = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """
    Groups the selected month's transactions into calendar weeks
    (week 1 = days 1-7, week 2 = 8-14, ... last partial week included),
    showing how activity progresses from the first to the last week of the month.
    """
    import datetime
    today = datetime.date.today()
    year = year or today.year
    month = month or today.month

    q = db.query(Transaction).filter(
        extract("year", Transaction.completion_time) == year,
        extract("month", Transaction.completion_time) == month,
    )
    rows = q.with_entities(
        Transaction.completion_time, Transaction.amount
    ).all()

    week_buckets = {}
    for completion_time, amount in rows:
        if completion_time is None:
            continue
        day = completion_time.day
        week_no = min((day - 1) // 7 + 1, 5)
        b = week_buckets.setdefault(week_no, {"week": week_no, "count": 0, "total_value": 0.0})
        b["count"] += 1
        b["total_value"] += abs(amount or 0)

    result = [week_buckets.get(w, {"week": w, "count": 0, "total_value": 0.0}) for w in range(1, 6)]
    return {"year": year, "month": month, "weeks": result}


@router.get("/monthly-overview")
def monthly_overview(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Volume & net value per calendar month, across all loaded history."""
    rows = (
        db.query(
            extract("year", Transaction.completion_time).label("year"),
            extract("month", Transaction.completion_time).label("month"),
            func.count(Transaction.id).label("count"),
            func.sum(Transaction.paid_in).label("total_in"),
            func.sum(Transaction.withdrawn).label("total_out"),
        )
        .group_by("year", "month").order_by("year", "month").all()
    )
    return [
        {
            "year": int(r.year), "month": int(r.month), "count": r.count,
            "total_in": float(r.total_in or 0), "total_out": float(r.total_out or 0),
        }
        for r in rows
    ]
