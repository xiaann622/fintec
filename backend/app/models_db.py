from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, DateTime, Text, Boolean, ForeignKey
)
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    company = Column(String(150), nullable=True)
    role = Column(String(30), default="analyst")  # analyst | admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    """
    Maps to the existing Postgres `transactions` table.
    Column set mirrors the fields produced by the M-Pesa ML pipeline
    (Fintech_Final_v5 notebook) so predictions can be written straight back.
    If your existing table uses different column names, adjust here to match
    (SQLAlchemy will simply read/write these attribute<->column pairs).
    """
    __tablename__ = "transactions"

    id = Column(BigInteger, primary_key=True, index=True)
    receipt_no = Column(String(50), index=True, nullable=True)
    completion_time = Column(DateTime, index=True, nullable=False)
    details = Column(Text, nullable=False)
    details_nlp = Column(Text, nullable=True)

    paid_in = Column(Float, default=0.0)
    withdrawn = Column(Float, default=0.0)
    balance = Column(Float, nullable=True)
    amount = Column(Float, default=0.0)          # paid_in - withdrawn
    amount_raw = Column(Float, default=0.0)

    transaction_label = Column(String(60), index=True, nullable=True)
    transaction_classification = Column(String(60), index=True, nullable=True)
    transaction_category = Column(String(60), index=True, nullable=True)

    label_confidence = Column(Float, nullable=True)
    classification_confidence = Column(Float, nullable=True)
    category_confidence = Column(Float, nullable=True)

    counterparty_alias = Column(String(80), nullable=True)   # PERSON_n / BUSINESS_n
    channel = Column(String(40), nullable=True)               # paybill/till/send money etc

    source_file = Column(String(255), nullable=True)
    source_type = Column(String(20), nullable=True)  # csv | excel | pdf | image | manual
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)
    rows_ingested = Column(Integer, default=0)
    rows_failed = Column(Integer, default=0)
    status = Column(String(20), default="processing")  # processing|completed|failed
    error_message = Column(Text, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    subject = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    rating = Column(Integer, nullable=True)  # 1-5
    category = Column(String(40), nullable=True)  # bug | feature | prediction-quality | other
    transaction_id = Column(BigInteger, nullable=True)  # optional: feedback on a specific prediction
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PredictionLog(Base):
    """Every model call is logged here for the Monitoring page (drift, volume, latency)."""
    __tablename__ = "prediction_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    transaction_id = Column(BigInteger, nullable=True)
    model_stage = Column(String(30), nullable=False)  # label | classification | category
    predicted_value = Column(String(60), nullable=False)
    confidence = Column(Float, nullable=True)
    latency_ms = Column(Float, nullable=True)
    model_version = Column(String(60), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
