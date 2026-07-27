-- M-Pesa Intelligence System — Postgres 14 schema
-- Run this only if your `transactions` table does not already exist.
-- If it already exists with data, DO NOT run the CREATE TABLE for
-- transactions — instead compare/alter columns to match, see notes below.

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(150) NOT NULL,
    email           VARCHAR(150) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    company         VARCHAR(150),
    role            VARCHAR(30) DEFAULT 'analyst',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Existing table in your DB. Columns below reflect what the ML pipeline
-- reads/writes. If your existing table uses different names, either:
--   (a) rename your columns to match, or
--   (b) edit backend/app/models_db.py Transaction class to match yours.
CREATE TABLE IF NOT EXISTS transactions (
    id                          BIGSERIAL PRIMARY KEY,
    receipt_no                  VARCHAR(50),
    completion_time             TIMESTAMP NOT NULL,
    details                     TEXT NOT NULL,
    details_nlp                 TEXT,
    paid_in                     DOUBLE PRECISION DEFAULT 0,
    withdrawn                   DOUBLE PRECISION DEFAULT 0,
    balance                     DOUBLE PRECISION,
    amount                      DOUBLE PRECISION DEFAULT 0,
    amount_raw                  DOUBLE PRECISION DEFAULT 0,
    transaction_label           VARCHAR(60),
    transaction_classification  VARCHAR(60),
    transaction_category        VARCHAR(60),
    label_confidence            DOUBLE PRECISION,
    classification_confidence   DOUBLE PRECISION,
    category_confidence         DOUBLE PRECISION,
    counterparty_alias          VARCHAR(80),
    channel                     VARCHAR(40),
    source_file                 VARCHAR(255),
    source_type                 VARCHAR(20),
    uploaded_by                 INTEGER REFERENCES users(id),
    created_at                  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_transactions_completion_time ON transactions (completion_time);
CREATE INDEX IF NOT EXISTS idx_transactions_label ON transactions (transaction_label);
CREATE INDEX IF NOT EXISTS idx_transactions_classification ON transactions (transaction_classification);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions (transaction_category);
CREATE INDEX IF NOT EXISTS idx_transactions_receipt ON transactions (receipt_no);

CREATE TABLE IF NOT EXISTS upload_batches (
    id             SERIAL PRIMARY KEY,
    filename       VARCHAR(255) NOT NULL,
    file_type      VARCHAR(20) NOT NULL,
    rows_ingested  INTEGER DEFAULT 0,
    rows_failed    INTEGER DEFAULT 0,
    status         VARCHAR(20) DEFAULT 'processing',
    error_message  TEXT,
    uploaded_by    INTEGER REFERENCES users(id),
    created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feedback (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id),
    subject         VARCHAR(150) NOT NULL,
    message         TEXT NOT NULL,
    rating          INTEGER CHECK (rating BETWEEN 1 AND 5),
    category        VARCHAR(40),
    transaction_id  BIGINT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prediction_logs (
    id              BIGSERIAL PRIMARY KEY,
    transaction_id  BIGINT,
    model_stage     VARCHAR(30) NOT NULL,
    predicted_value VARCHAR(60) NOT NULL,
    confidence      DOUBLE PRECISION,
    latency_ms      DOUBLE PRECISION,
    model_version   VARCHAR(60),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prediction_logs_created_at ON prediction_logs (created_at);
