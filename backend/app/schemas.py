from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# ---------- Auth ----------
class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(min_length=6)
    company: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    company: Optional[str]
    role: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut



# ---------- Transactions ----------
class TransactionOut(BaseModel):
    id: int
    receipt_no: Optional[str]
    completion_time: datetime
    details: str
    paid_in: Optional[float]
    withdrawn: Optional[float]
    balance: Optional[float]
    amount: Optional[float]
    transaction_label: Optional[str]
    transaction_classification: Optional[str]
    transaction_category: Optional[str]
    label_confidence: Optional[float]
    classification_confidence: Optional[float]
    category_confidence: Optional[float]
    counterparty_alias: Optional[str]
    source_type: Optional[str]

    class Config:
        from_attributes = True


class TransactionManualIn(BaseModel):
    completion_time: datetime
    details: str
    paid_in: float = 0.0
    withdrawn: float = 0.0
    balance: Optional[float] = None


class PredictTextIn(BaseModel):
    details: str
    completion_time: Optional[datetime] = None
    paid_in: float = 0.0
    withdrawn: float = 0.0


class PredictionResult(BaseModel):
    details: str
    details_nlp: str
    transaction_label: str
    transaction_classification: str
    transaction_category: str
    transaction_category_raw_model: Optional[str] = None
    category_override_applied: bool = False
    counterparty_alias: Optional[str] = None
    label_confidence: Optional[float] = None
    classification_confidence: Optional[float] = None
    category_confidence: Optional[float] = None


# ---------- Feedback ----------
class FeedbackIn(BaseModel):
    subject: str
    message: str
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    category: Optional[str] = "other"
    transaction_id: Optional[int] = None


class FeedbackOut(FeedbackIn):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Paginated list wrapper ----------
class Paginated(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[dict]