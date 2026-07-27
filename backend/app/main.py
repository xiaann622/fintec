import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth, upload, transactions, predictions, trends, monitoring, feedback
from app.ml.pipeline import load_artifacts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mpesa.main")

app = FastAPI(
    title="M-Pesa Intelligence System API",
    description="OCR ingestion, ML classification and behavioural analytics for M-Pesa transaction statements.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(transactions.router)
app.include_router(predictions.router)
app.include_router(trends.router)
app.include_router(monitoring.router)
app.include_router(feedback.router)


@app.on_event("startup")
def on_startup():
    # Creates users/upload_batches/feedback/prediction_logs tables if missing.
    # Does NOT alter your existing `transactions` table structure —
    # run database/schema.sql once if that table doesn't exist yet.
    Base.metadata.create_all(bind=engine)
    load_artifacts()
    logger.info("M-Pesa Intelligence System API started.")


@app.get("/api/health")
def health():
    from app.ml.pipeline import artifacts_ready
    return {"status": "ok", "models_ready": artifacts_ready()}
