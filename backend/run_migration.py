"""
One-off migration: adds the `upload_batch_id` column to the `transactions`
table (needed for the delete-upload-batch feature).

Run this ONCE from your `backend/` folder, with your venv active:

    cd backend
    venv\\Scripts\\activate
    python run_migration.py

It uses your project's own DATABASE_URL (same config the app already uses),
so there's nothing new to configure. Safe to run more than once -- it
checks whether the column already exists first and skips it if so.
"""
import sys
from sqlalchemy import text

sys.path.insert(0, ".")
from app.database import engine  # noqa: E402

CHECK_SQL = """
SELECT column_name FROM information_schema.columns
WHERE table_name = 'transactions' AND column_name = 'upload_batch_id';
"""

ALTER_SQL = """
ALTER TABLE transactions ADD COLUMN upload_batch_id INTEGER REFERENCES upload_batches(id);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_transactions_upload_batch_id ON transactions (upload_batch_id);
"""

with engine.begin() as conn:
    exists = conn.execute(text(CHECK_SQL)).first()
    if exists:
        print("Column 'upload_batch_id' already exists on transactions -- nothing to do.")
    else:
        print("Adding 'upload_batch_id' column to transactions...")
        conn.execute(text(ALTER_SQL))
        print("Creating index...")
        conn.execute(text(INDEX_SQL))
        print("Done. Restart uvicorn now.")