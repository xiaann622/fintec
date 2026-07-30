"""
Central configuration for the M-Pesa Intelligence System backend.
All values are read from environment variables (see .env.example).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_models_dir() -> str:
    """
    A relative MODELS_DIR value (backend/.env.example ships
    `MODELS_DIR=./models_store`) resolves relative to the process's current
    working directory at import time -- which varies by how/where the
    server is launched (uvicorn from the repo root vs. backend/, a process
    manager with its own cwd, a Windows service, etc.) and is NOT
    necessarily BASE_DIR.

    If that directory doesn't exist, `os.makedirs(settings.MODELS_DIR,
    exist_ok=True)` below silently creates an *empty* one, `_try_load()` in
    app/ml/pipeline.py finds nothing there, and `artifacts_ready()` returns
    False -- with only a server-log warning, nothing visible in the UI.
    Every transaction then gets saved with null label/classification/
    category, which the frontend renders as "Unclassified" / "--" for every
    row (a *different* trigger for the same visible symptom as the
    n_jobs/Windows-multiprocessing issue fixed elsewhere in this file).

    Anchoring any relative MODELS_DIR to BASE_DIR (backend/) instead of CWD
    makes `MODELS_DIR=./models_store` mean the same thing -- backend's own
    models_store/ -- no matter where the process was started from.
    """
    raw = os.getenv("MODELS_DIR")
    if not raw:
        return str(BASE_DIR / "models_store")
    p = Path(raw)
    return str(p) if p.is_absolute() else str(BASE_DIR / p)


class Settings:
    # --- Postgres (your existing DB 14, table `transactions`) ---
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5435")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "mpesa")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "Anngatz3112#")

    @property
    def DATABASE_URL(self) -> str:
        override = os.getenv("DATABASE_URL")
        if override:
            return override
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # --- Auth ---
    SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE_ME_IN_PRODUCTION_" + os.urandom(8).hex())
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

    # --- ML model artifacts ---
    MODELS_DIR: str = _resolve_models_dir()

    # Applies the notebook's post_process_predictions() keyword-override layer
    # to transaction_category predictions (Cells 42/44, applied before every
    # accuracy score in Cells 45/83). Set to "false" to get raw model output
    # only, matching the notebook's Cell 142 single-transaction demo instead.
    # See app/ml/category_overrides.py for the full explanation.
    ENABLE_CATEGORY_OVERRIDES: bool = os.getenv("ENABLE_CATEGORY_OVERRIDES", "true").lower() == "true"
    ENABLE_LABEL_OVERRIDES: bool = os.getenv("ENABLE_LABEL_OVERRIDES", "true").lower() == "true"
    ENABLE_CLASSIFICATION_OVERRIDES: bool = os.getenv("ENABLE_CLASSIFICATION_OVERRIDES", "true").lower() == "true"

    # --- OCR ---
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "tesseract")

    # --- CORS ---
    ALLOWED_ORIGINS: list = os.getenv("ALLOWED_ORIGINS", "*").split(",")

    # --- Uploads ---
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads"))
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "25000"))


settings = Settings()
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.MODELS_DIR, exist_ok=True)