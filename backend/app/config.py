"""
Central configuration for the M-Pesa Intelligence System backend.
All values are read from environment variables (see .env.example).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


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
    MODELS_DIR: str = os.getenv("MODELS_DIR", str(BASE_DIR / "models_store"))

    # Applies the notebook's post_process_predictions() keyword-override layer
    # to transaction_category predictions (Cells 42/44, applied before every
    # accuracy score in Cells 45/83). Set to "false" to get raw model output
    # only, matching the notebook's Cell 142 single-transaction demo instead.
    # See app/ml/category_overrides.py for the full explanation.
    ENABLE_CATEGORY_OVERRIDES: bool = os.getenv("ENABLE_CATEGORY_OVERRIDES", "true").lower() == "true"
    ENABLE_LABEL_OVERRIDES: bool = os.getenv("ENABLE_LABEL_OVERRIDES", "true").lower() == "true"

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