# M-Pesa Intelligence System

A full-stack transaction intelligence platform for M-Pesa statements: OCR-powered
ingestion (CSV, Excel, PDF, scanned documents, photos), a 3-stage ML
classification pipeline (label → classification → category), behavioural
trend analytics, and a model-monitoring dashboard — built for finance teams
who need to understand transaction behaviour fast.

```
mpesa-system/
├── backend/            FastAPI API — auth, OCR ingestion, ML pipeline, Postgres
├── frontend/            HTML/CSS/JS multi-page app (login, dashboard, uploads, trends…)
├── streamlit_app/        Companion analytics app (direct DB access, ad-hoc exploration)
├── database/schema.sql   Postgres schema (users, transactions, uploads, feedback, logs)
└── docker-compose.yml    One-command full-stack deployment
```

## 1. Architecture at a glance

- **Backend (FastAPI + Postgres 14)** — REST API under `/api/*`. Handles auth
  (JWT), file ingestion + OCR, runs your trained models, and serves all
  analytics queries the frontend/Streamlit need.
- **Frontend (plain HTML/CSS/JS)** — no build step. Talks to the backend via
  `fetch`, renders charts with Chart.js. Pages: Login, Home, Upload,
  Transactions, Labels, Classification, Categories, Predict, Trends,
  Monitoring, Feedback, About.
- **Streamlit app** — a read-only analytics companion that queries Postgres
  directly (via SQLAlchemy/pandas) for fast ad-hoc filtering/exporting,
  independent of the main app.
- **ML pipeline** — ported 1:1 from `Fintech_Final_v5.ipynb`. Three models run
  in sequence, each with a different feature width:

  | Stage | Text features | Extra features | Total |
  |---|---|---|---|
  | `transaction_label` | TF-IDF | hour, day-of-week, is_weekend (3) + amount block (9) = **12** | TFIDF + 12 |
  | `transaction_classification` | TF-IDF | label (1) + time (3) + amount (9) = **13** | TFIDF + 13 |
  | `transaction_category` | TF-IDF | label (1) + classification (1) + time (3) + amount (9) = **14** | TFIDF + 14 |

  This matches what you described (e.g. TF-IDF 1502 → model input 1516 for
  the category model = 1502 + 14). The exact feature order is implemented in
  `backend/app/ml/feature_engineering.py` — **do not reorder these columns**
  or predictions will silently be wrong (sklearn doesn't validate column
  semantics, only column count).

- **Category keyword-override layer.** Your notebook also applies a
  deterministic, business-name keyword override (`post_process_predictions`
  in your notebook) to `transaction_category` — hard-coded rules like
  "Naivas/Shell/any `*_LIMITED`/`*_SHOP` name → Retail & Shopping or Travel &
  Leisure" that run *after* the category model's raw prediction. This is
  ported exactly in `backend/app/ml/category_overrides.py`.

  **Worth knowing:** every balanced-accuracy score in your notebook (model
  comparison cells) was computed *with* this override applied — but your
  notebook's own single-transaction demo cell predicts directly from the
  model *without* it. Those two cells disagree with each other, so I
  couldn't infer a single "correct" answer from the notebook alone. The
  backend applies the override **by default** (to match the accuracy your
  models were actually selected on). Set `ENABLE_CATEGORY_OVERRIDES=false`
  in `backend/.env` if you'd rather get raw model output only. The Predict
  page shows a banner whenever an override actually fires, so you can see
  it happening on real transactions.

## 2. Prerequisites

- Python 3.11
- Postgres 14 (you already have this — see §5)
- Tesseract OCR + Poppler (for PDF/image ingestion):
  - **Ubuntu/Debian:** `sudo apt-get install tesseract-ocr poppler-utils`
  - **macOS:** `brew install tesseract poppler`
  - **Windows:** install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
    and [poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases),
    then set `TESSERACT_CMD` in `backend/.env` to the full path of `tesseract.exe`.
- Node is **not** required — the frontend is plain HTML/CSS/JS.

## 3. Backend setup (local, no Docker)

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set POSTGRES_* (or DATABASE_URL) to your existing DB 14,
# and a real SECRET_KEY

python -c "import nltk; nltk.download('stopwords'); nltk.download('wordnet'); nltk.download('omw-1.4')"

uvicorn app.main:app --reload --port 8000
```

On startup the backend will:
- Create `users`, `upload_batches`, `feedback`, `prediction_logs` tables if
  they don't exist yet (**never touches your existing `transactions` table
  structure** — `Base.metadata.create_all` is a no-op for tables that
  already exist).
- Attempt to load your ML models from `backend/models_store/`.

Check `GET http://localhost:8000/api/health` → `{"status":"ok","models_ready":true}`.

## 4. Load your trained models

Read **`backend/models_store/README.md`** — it lists the exact filenames the
loader looks for (with a fallback list so your original notebook filenames
work without renaming), plus a copy-paste snippet to export them from Colab.
Drop the `.joblib` files into `backend/models_store/` and restart the backend.

If models aren't loaded yet, the Upload page will still ingest and store
rows (without predictions) — run **Monitoring → "Run backfill now"** once
the models are in place to classify anything that was stored earlier.

## 5. Connecting your existing Postgres 14 database

You mentioned your DB already has some data in a `transactions` table. Two
paths:

- **Column names already match** what's in `database/schema.sql` /
  `backend/app/models_db.py` (`receipt_no`, `completion_time`, `details`,
  `paid_in`, `withdrawn`, `balance`, `transaction_label`,
  `transaction_classification`, `transaction_category`, …) → just point
  `POSTGRES_*` at it. Nothing else to do.
- **Column names differ** → either rename your columns to match, or edit the
  `Transaction` class in `backend/app/models_db.py` so each SQLAlchemy
  attribute maps to your actual column name (e.g.
  `amount = Column("txn_amount", Float)`).

Run `database/schema.sql` once (`psql -f database/schema.sql`) if the
supporting tables (`users`, `upload_batches`, `feedback`, `prediction_logs`)
don't exist yet — it uses `CREATE TABLE IF NOT EXISTS` throughout, so it's
safe to run against a DB that already has your `transactions` table and data.

## 6. Frontend setup

No build step — it's static HTML/CSS/JS.

```bash
cd frontend
python -m http.server 8080
# open http://localhost:8080
```

Edit `frontend/js/config.js` if your backend isn't on `http://localhost:8000`:

```js
window.MPESA_API_BASE = "http://localhost:8000"; // or your deployed API URL
```

The first user to register (via the "Create an account" link on the login
page) is automatically made an `admin`.

## 7. Streamlit companion app

```bash
cd streamlit_app
pip install -r requirements.txt
cp ../backend/.env .env     # reuse the same DB connection settings
streamlit run app.py
```

Optional password gate: set `STREAMLIT_APP_PASSWORD` in `streamlit_app/.env`.
Without it, the app is open (fine for an internal/VPN-only deployment, not
for the public internet).

## 8. One-command deployment with Docker

```bash
docker compose up --build
```

This starts: `postgres` (only if you don't already have one — see the notes
inside `docker-compose.yml` about pointing at your existing DB instead),
`backend` on :8000, `streamlit` on :8501, and `frontend` (nginx) on :8080.

Before running, drop your `.joblib` models into `backend/models_store/` and
create `backend/.env` from `.env.example` — both are mounted/read by the
`backend` container.

## 9. Security notes

- Auth uses JWT bearer tokens (`python-jose`) with bcrypt-hashed passwords
  (`passlib`). Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 8h).
- Every `/api/*` route except `/api/auth/login` and `/api/auth/register`
  requires a valid `Authorization: Bearer <token>` header.
- Set a long, random `SECRET_KEY` in production — never use the auto-generated
  dev default outside local testing.
- Lock `ALLOWED_ORIGINS` down to your real frontend domain(s) before going to
  production (it defaults to `*` for local development convenience).
- Uploaded files are validated by extension and size (`MAX_UPLOAD_MB`) before
  processing.

## 10. Feature pages included

| Page | What it shows |
|---|---|
| **Home** | KPI cards, category mix, monthly inflow/outflow, hour-of-day and weekday/weekend snapshots, recent transactions |
| **Upload** | Drag-and-drop CSV/Excel/PDF/scanned/JPEG ingestion with OCR, live batch history |
| **Transactions** | Full filterable, paginated ledger |
| **Labels / Classification / Categories** | Distribution charts + click-to-drill-in transaction lists for each stage of the pipeline |
| **Predict** | Run the pipeline on one ad-hoc transaction line |
| **Trends** | Time-of-day histogram, weekday vs weekend, day-of-week pattern, monthly week-1→week-5 progression, full multi-month history |
| **Monitoring** | Model-ready status, classification coverage, confidence trend over time, category drift (last 30 vs prior 30 days), low-confidence review queue, upload batch health |
| **Feedback** | Submit + browse feedback, optionally tied to a specific transaction |
| **About** | System overview and architecture explanation |

## 11. Troubleshooting

- **"ML models are not loaded"** → confirm the six required `.joblib` files
  are in `backend/models_store/` and check the backend startup logs for the
  exact filenames it looked for.
- **Shape mismatch / sklearn errors** → almost always means a feature-order
  mismatch. Re-check `backend/app/ml/feature_engineering.py` against Cells
  119/138/140/142 of your notebook if you changed the training feature
  order.
- **OCR returns no rows** → scanned image quality matters a lot; try a
  higher-resolution scan, or export a CSV/XLSX statement instead when
  possible. You can also tune `MPESA_ROW_RE` in
  `backend/app/ocr/extractor.py` to match your statement's exact layout.
- **CORS errors in the browser console** → set `ALLOWED_ORIGINS` in
  `backend/.env` to include your frontend's exact origin.
