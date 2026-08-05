"""
Directly queries the database for the real transaction count -- bypasses
the API, the frontend, and any browser caching entirely. Run this from
`backend/` with your venv active:
 
    python check_transaction_count.py
"""
import sys
from sqlalchemy import text
 
sys.path.insert(0, ".")
from app.database import engine  # noqa: E402
 
with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
    unclassified = conn.execute(text(
        "SELECT COUNT(*) FROM transactions WHERE transaction_label IS NULL"
    )).scalar()
    batches = conn.execute(text("SELECT COUNT(*) FROM upload_batches")).scalar()
 
print(f"Real transaction count in the database right now: {total}")
print(f"  (of which unclassified: {unclassified})")
print(f"Upload batches: {batches}")
 