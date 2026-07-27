"""
Text preprocessing — ported 1:1 from Fintech_Final_v5 (Cell 31).
Must stay identical to training-time preprocessing or the TF-IDF
vectorizers will produce a different vocabulary alignment at inference.
"""
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

for pkg in ["stopwords", "wordnet", "omw-1.4"]:
    try:
        nltk.data.find(f"corpora/{pkg}")
    except LookupError:
        nltk.download(pkg, quiet=True)

_lemmatizer = WordNetLemmatizer()
MPESA_STOPWORDS = set(stopwords.words("english"))

MPESA_KEYWORDS = {
    "paybill", "till", "merchant", "customer", "transfer",
    "withdraw", "deposit", "reversal", "refund", "loan",
}


def preprocess_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"\d+\*+\d*", " ", text)
    text = re.sub(r"[^a-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = [
        _lemmatizer.lemmatize(tok)
        for tok in text.split()
        if tok not in MPESA_STOPWORDS and len(tok) > 2
    ]
    return " ".join(tokens)
