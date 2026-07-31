"""
Finds and removes duplicate Transaction rows -- created by re-uploading the
same statement/file more than once during testing.

DRY RUN BY DEFAULT -- prints what would be deleted without touching your
database. Review the output, then re-run with --apply to actually delete.

Usage (from backend/, with venv active):
    python dedup_transactions.py            # dry run, just prints
    python dedup_transactions.py --apply     # actually deletes

Dedup key:
  - If a row has a non-empty receipt_no (M-Pesa receipt codes are unique
    per real transaction), duplicates are rows sharing the same receipt_no.
  - If receipt_no is missing/empty (can happen for some OCR-parsed rows),
    falls back to matching on (completion_time, details, paid_in,
    withdrawn, balance) together.
  - Within each duplicate group, the row with the LOWEST id (the original,
    first-inserted copy) is kept; every other row in that group is
    deleted, along with its associated PredictionLog rows.
"""
import sys
from collections import defaultdict

sys.path.insert(0, ".")
from app.database import SessionLocal  # noqa: E402
from app.models_db import Transaction, PredictionLog  # noqa: E402

APPLY = "--apply" in sys.argv

db = SessionLocal()

rows = db.query(
    Transaction.id, Transaction.receipt_no, Transaction.completion_time,
    Transaction.details, Transaction.paid_in, Transaction.withdrawn,
    Transaction.balance,
).order_by(Transaction.id.asc()).all()

groups = defaultdict(list)
for r in rows:
    if r.receipt_no and r.receipt_no.strip():
        key = ("receipt", r.receipt_no.strip())
    else:
        key = ("composite", r.completion_time, r.details, r.paid_in, r.withdrawn, r.balance)
    groups[key].append(r.id)

dup_groups = {k: ids for k, ids in groups.items() if len(ids) > 1}
ids_to_delete = []
for key, ids in dup_groups.items():
    keep = min(ids)
    ids_to_delete.extend(i for i in ids if i != keep)

print(f"Scanned {len(rows)} transactions.")
print(f"Found {len(dup_groups)} duplicate group(s), {len(ids_to_delete)} row(s) would be deleted.\n")

if dup_groups:
    print("Sample (first 5 groups):")
    for key, ids in list(dup_groups.items())[:5]:
        kind = key[0]
        ident = key[1] if kind == "receipt" else f"{key[2]!r} @ {key[1]}"
        print(f"  [{kind}] {ident} -> {len(ids)} copies (ids={ids}), keeping id={min(ids)}")
    print()

if not APPLY:
    print("Dry run only -- nothing deleted. Re-run with --apply to actually delete these rows.")
else:
    if not ids_to_delete:
        print("Nothing to delete.")
    else:
        logs_deleted = (
            db.query(PredictionLog)
            .filter(PredictionLog.transaction_id.in_(ids_to_delete))
            .delete(synchronize_session=False)
        )
        txns_deleted = (
            db.query(Transaction)
            .filter(Transaction.id.in_(ids_to_delete))
            .delete(synchronize_session=False)
        )
        db.commit()
        print(f"Deleted {txns_deleted} transaction(s) and {logs_deleted} prediction log(s).")

db.close()