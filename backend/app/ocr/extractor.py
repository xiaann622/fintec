"""
Multi-format ingestion for M-Pesa statements:
  - .csv / .xlsx / .xls           -> pandas, direct column mapping
  - .pdf (text-based)              -> pdfplumber text/table extraction
  - .pdf (scanned) / .jpg / .png   -> OCR via pytesseract (with pdf2image
                                       rasterising scanned PDF pages first)

Output: a normalised DataFrame with columns
  receipt_no, completion_time, details, paid_in, withdrawn, balance,
  amount, amount_raw, paid_in_raw, withdrawn_raw
ready to feed into app.ml.pipeline.predict_batch (after adding 'Details').
"""
import io
import logging
import re
from typing import List, Optional, Tuple

import pandas as pd

logger = logging.getLogger("mpesa.ocr")

# ---------------------------------------------------------------------------
# Row parsing
# ---------------------------------------------------------------------------
# A row STARTS with a receipt code + date + time, e.g.:
#   UANHF4RKFY 2026-01-23 12:04:33 Pay Bill Online Fuliza M-Pesa to Completed -95.00 0.00
# Everything else on that line -- and on any following line that does NOT
# itself look like a new row -- belongs to THIS row. That matters because
# the Details column regularly wraps onto a second (or third) line, e.g. the
# continuation "333222 - M-KOPA Kenya Ltd Acc. 13242477" for the row above.
ROW_START_RE = re.compile(
    r"^(?P<receipt>[A-Z][A-Z0-9]{7,11})\s+"
    r"(?P<date>\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s+"
    r"(?P<rest>.*)$"
)

_STATUS_RE = re.compile(r"\b(Completed|Pending|Failed|Reversed|Cancelled)\b", re.IGNORECASE)

# Only matches genuine decimal amounts (e.g. -95.00, 1,234.56) -- deliberately
# requires exactly 2 decimal digits so it never mistakes an account/till
# number like "333222" or "13242477" (no decimal point) for a Paid In /
# Withdrawn / Balance value.
_AMOUNT_RE = re.compile(r"-?[\d,]+\.\d{2}\b")

# Lines that are page furniture, not transaction data, and must never be
# folded into a details continuation. Deliberately does NOT treat "no
# letters at all" as noise -- a continuation line can legitimately be a bare
# account/reference/phone number (e.g. "13242477" or "0722541873") that
# wrapped onto its own line, and dropping those loses real data. Only a
# short 1-3 digit standalone number is treated as noise (a page number);
# anything longer is kept as a genuine continuation.
_NOISE_LINE_PATTERNS = [
    re.compile(r"receipt\s*no\.?\s*.*completion\s*time", re.IGNORECASE),
    re.compile(r"m-?pesa\s+statement", re.IGNORECASE),
    re.compile(r"^\s*page\s+\d+", re.IGNORECASE),
    re.compile(r"disclaimer", re.IGNORECASE),
    re.compile(r"^\s*[-_=]{3,}\s*$"),        # table border / separator lines
    re.compile(r"^\s*\d{1,3}\s*$"),          # bare page number (short only)
    re.compile(r"summary|opening\s+balance|closing\s+balance", re.IGNORECASE),
    # SMS-confirmation / statement-page footer boilerplate. Real statements
    # (and the SMS text some OCR sources are built from) repeat this on
    # every single page, and without these patterns it was silently getting
    # appended to whatever transaction happened to be "current" at that
    # point in the text stream -- polluting that row's `details` field with
    # unrelated marketing/help text (e.g. "...For self-help dial *234# |
    # Web: www.safaricom.co.ke | Twitter: @SafaricomPLC | Facebook:
    # Safaricom PLC | Terms and conditions apply").
    re.compile(r"for\s+self-help\s+dial", re.IGNORECASE),
    re.compile(r"terms\s+and\s+conditions\s+apply", re.IGNORECASE),
    re.compile(r"\bweb:\s*www\.", re.IGNORECASE),
    re.compile(r"twitter:\s*@\w+", re.IGNORECASE),
    re.compile(r"facebook:\s*safaricom", re.IGNORECASE),
    re.compile(r"safaricom\s*plc", re.IGNORECASE),
    re.compile(r"prompts?\s+to\s+enter\s+the\s+code", re.IGNORECASE),
]

NUMERIC_COLS = ["paid_in", "withdrawn", "balance"]


def _is_noise_line(line: str) -> bool:
    return any(p.search(line) for p in _NOISE_LINE_PATTERNS)


def _split_amounts_and_leftover(text: str) -> Tuple[List[float], str]:
    """
    Pulls decimal-amount tokens out of `text`, returning (amounts, leftover).
    `leftover` is whatever non-numeric wording remains once those tokens are
    removed -- i.e. genuine Details text that happened to land in the
    numeric tail of the row because of PDF line-wrapping, not an actual
    Paid In / Withdrawn / Balance value.
    """
    amounts = [float(a.replace(",", "")) for a in _AMOUNT_RE.findall(text)]
    leftover = _AMOUNT_RE.sub(" ", text)
    leftover = re.sub(r"\s+", " ", leftover).strip(" -\u2013\u2014")
    return amounts, leftover


def _assign_amounts(amounts: List[float]) -> Tuple[float, float, Optional[float]]:
    """
    Maps a variable-length list of decimal amounts on a row to
    (paid_in, withdrawn, balance) -- WITHOUT assuming all three are present.

    Real M-Pesa statements leave a column's cell genuinely BLANK (no text at
    all, not even "0.00") when it doesn't apply -- a Withdraw/Pay Bill
    transaction populates Withdrawn only, a Deposit populates Paid In only.
    So we never require exactly 2 or 3 numbers:

      - The LAST amount is always Balance (rightmost column, always shown).
      - Of whatever remains: a NEGATIVE value is Withdrawn (M-Pesa renders
        money-out as negative), a non-negative value is Paid In.
      - If nothing remains, both are 0 -- we don't guess a value that was
        never actually present in the text.
    """
    if not amounts:
        return 0.0, 0.0, None

    balance = amounts[-1]
    remainder = amounts[:-1]

    if not remainder:
        return 0.0, 0.0, balance

    if len(remainder) == 1:
        val = remainder[0]
        return (0.0, abs(val), balance) if val < 0 else (val, 0.0, balance)

    negatives = [v for v in remainder if v < 0]
    positives = [v for v in remainder if v >= 0]
    if negatives and positives:
        return positives[0], abs(negatives[0]), balance

    # Same-sign fallback (shouldn't normally happen): trust standard column
    # order, Paid In before Withdrawn.
    return remainder[0], abs(remainder[1]), balance


def _clean_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "").str.replace("KES", "", case=False).str.strip(),
        errors="coerce",
    )


def normalise_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df.columns = (
        df.columns.astype(str).str.strip().str.lower()
            .str.replace(" ", "_").str.replace(".", "", regex=False)
    )
    rename_map = {
        "receipt_no": "receipt_no", "receipt": "receipt_no",
        "completion_time": "completion_time", "date": "completion_time",
        "details": "details", "detail": "details", "narrative": "details",
        "paid_in": "paid_in", "amount_in": "paid_in", "credit": "paid_in",
        "withdrawn": "withdrawn", "amount_out": "withdrawn", "debit": "withdrawn",
        "balance": "balance",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "details" not in df.columns:
        raise ValueError("Could not find a transaction details/narrative column.")

    
        # Parsed per-element (not vectorized) on purpose: pd.to_datetime on a
        # whole Series infers ONE format from the first value and silently
        # turns every row that doesn't match it into NaT. Real statements can
        # mix formats -- e.g. an ISO "2026-01-23 12:04:33" row from a PDF's
        # text layer alongside "01/06/2026 08:15:22" rows from a CSV export --
        # so each value is parsed independently instead.
    if "completion_time" in df.columns:
        df["completion_time"] = df["completion_time"].apply(
            lambda x: pd.to_datetime(
                x,
                format="mixed",
                errors="coerce",
                dayfirst=True,
        )
    )
    else:
        df["completion_time"] = pd.NaT

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = _clean_numeric(df[col])
        else:
            df[col] = 0.0

    df["details"] = df["details"].astype(str).str.strip()
    df = df[~df["details"].isin(["nan", "", "None"])].reset_index(drop=True)

    # Paid In / Withdrawn are frequently blank (NaN) for any given
    # transaction by design -- a withdrawal has no Paid In, a deposit has no
    # Withdrawn. That's expected, not an extraction failure; fillna(0) here
    # simply turns "not applicable" into 0 for arithmetic, it does not mean
    # we assumed both columns had a value while parsing.
    df["paid_in"] = df["paid_in"].fillna(0)
    df["withdrawn"] = df["withdrawn"].fillna(0).abs()
    df["amount"] = df["paid_in"] - df["withdrawn"]
    df["paid_in_raw"] = df["paid_in"]
    df["withdrawn_raw"] = df["withdrawn"]
    df["amount_raw"] = df["amount"]
    if "receipt_no" not in df.columns:
        df["receipt_no"] = None
    return df


def from_csv_or_excel(file_bytes: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes))
    else:
        df = pd.read_excel(io.BytesIO(file_bytes))
    return normalise_dataframe(df)


def _parse_ocr_text(text: str) -> pd.DataFrame:
    """
    Parse extracted M-Pesa statement text into transaction rows.

    Features
    --------
    - Handles multiline transaction descriptions.
    - Detects new transactions using receipt numbers.
    - Preserves account numbers, phone numbers and wrapped text.
    - Ignores page headers and statement furniture.
    - Supports variable amount layouts.
    """

    rows: List[dict] = []
    current: Optional[dict] = None

    def _finalize(row):
        if row is None:
            return

        amounts, leftover = _split_amounts_and_leftover(row["_tail"])

        if leftover:
            row["_details_parts"].append(leftover)

        paid_in, withdrawn, balance = _assign_amounts(amounts)

        # Build one clean description
        details = " ".join(row["_details_parts"])
        details = re.sub(r"\s+", " ", details)
        details = re.sub(r"\s*-\s*-\s*", " - ", details)
        details = details.strip()

        if not details:
            return

        rows.append(
            {
                "receipt_no": row["receipt"],
                "completion_time": f"{row['date']} {row['time']}",
                "details": details,
                "paid_in": paid_in,
                "withdrawn": withdrawn,
                "balance": balance,
            }
        )

    for raw_line in text.splitlines():

        line = raw_line.strip()

        if not line:
            continue

        # ----------------------------------------------------
        # Ignore page furniture
        # ----------------------------------------------------
        if _is_noise_line(line):
            continue

        # ----------------------------------------------------
        # New transaction starts here
        # ----------------------------------------------------
        m = ROW_START_RE.match(line)

        if m:

            _finalize(current)

            rest = m.group("rest")

            status_match = _STATUS_RE.search(rest)

            if status_match:
                details_first = rest[: status_match.start()].strip()
                tail = rest[status_match.end():].strip()
            else:
                details_first = rest.strip()
                tail = ""

            current = {
                "receipt": m.group("receipt"),
                "date": m.group("date"),
                "time": m.group("time"),
                "_details_parts": [details_first] if details_first else [],
                "_tail": tail,
            }

            continue

        # ----------------------------------------------------
        # Continuation line
        # ----------------------------------------------------
        if current is not None:

            # Ignore repeated table headers
            lower = line.lower()

            if (
                "receipt no" in lower
                or "completion time" in lower
                or "transaction status" in lower
                or "paid in" in lower
                or "withdrawn" in lower
                or "balance" in lower
            ):
                continue

            line = re.sub(r"\s+", " ", line).strip()

            # Ignore duplicated continuation
            if (
                current["_details_parts"]
                and current["_details_parts"][-1] == line
            ):
                continue

            current["_details_parts"].append(line)

    _finalize(current)

    df = pd.DataFrame(
        rows,
        columns=[
            "receipt_no",
            "completion_time",
            "details",
            "paid_in",
            "withdrawn",
            "balance",
        ],
    )

    logger.info("Parsed %d transactions", len(df))

    if not df.empty:
        logger.info("First transaction: %s", df.iloc[0].to_dict())
        logger.info("Last transaction: %s", df.iloc[-1].to_dict())

    return df


def from_pdf(file_bytes: bytes) -> pd.DataFrame:
    """
    Try text-layer extraction first (pdfplumber).

    If text exists but cannot be parsed, stop and report the real problem.
    Only fall back to OCR if the PDF truly contains no text.
    """
    import pdfplumber

    all_text = []

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            logger.info("PDF has %d pages", len(pdf.pages))

            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                logger.info(
                    "Page %d extracted %d characters",
                    page_num,
                    len(text),
                )
                all_text.append(text)

    except Exception as e:
        logger.exception("pdfplumber failed")
        raise ValueError(f"Unable to open PDF: {e}")

    combined = "\n".join(all_text).strip()

    logger.info("Total extracted characters: %d", len(combined))

    if combined:
        logger.info("First 1000 characters:\n%s", combined[:1000])

    # If there is text, try parsing it.
    if combined:
        df = _parse_ocr_text(combined)

        logger.info("Parsed transactions: %d", len(df))

        if not df.empty:
            return normalise_dataframe(df)

        raise ValueError(
            "PDF text was extracted successfully, but no M-Pesa "
            "transactions could be parsed."
        )

    # No text at all -> probably a scanned PDF.
    logger.info("No text layer found. Falling back to OCR.")
    return from_scanned_pdf(file_bytes)


def from_scanned_pdf(file_bytes: bytes) -> pd.DataFrame:
    import os
    from concurrent.futures import ThreadPoolExecutor
    from pdf2image import convert_from_bytes
    import pytesseract

    images = convert_from_bytes(file_bytes, dpi=300)

    # OCR is the one extraction stage that's inherently slow (tesseract runs
    # per page), so for large scanned statements it's the biggest risk to a
    # tight time budget. pytesseract.image_to_string shells out to the
    # tesseract binary and blocks on it -- CPython releases the GIL while
    # waiting on that subprocess, so a thread pool gives real parallelism
    # here (not fighting the GIL the way pure-Python CPU work would).
    max_workers = min(len(images), max(os.cpu_count() or 1, 1))
    logger.info("OCR: %d page(s), %d worker thread(s)", len(images), max_workers)

    if max_workers <= 1:
        page_texts = [pytesseract.image_to_string(img) for img in images]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            page_texts = list(pool.map(pytesseract.image_to_string, images))

    df = _parse_ocr_text("\n".join(page_texts))
    return normalise_dataframe(df)


def from_image(file_bytes: bytes) -> pd.DataFrame:
    from PIL import Image
    import pytesseract

    img = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(img)
    df = _parse_ocr_text(text)
    return normalise_dataframe(df)


def extract(file_bytes: bytes, filename: str) -> pd.DataFrame:
    fname = filename.lower()
    if fname.endswith((".csv", ".xlsx", ".xls")):
        return from_csv_or_excel(file_bytes, filename)
    if fname.endswith(".pdf"):
        return from_pdf(file_bytes)
    if fname.endswith((".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")):
        return from_image(file_bytes)
    raise ValueError(f"Unsupported file type: {filename}")