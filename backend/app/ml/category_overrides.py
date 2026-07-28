"""
Deterministic post-processing overrides for `transaction_category` — ported
1:1 from Fintech_Final_v5.ipynb (business-name keyword logic first defined in
Cell 20's `layer1_assign`/`_route_anonymous_buy_goods`, then packaged as
`post_process_predictions()` in Cells 42/44 and applied after every
model.predict() call in the evaluation loops at Cells 45 and 83).

IMPORTANT — a documented inconsistency in the source notebook:
Every balanced-accuracy score reported while comparing models (Cells 45, 83)
was computed AFTER this override was applied to the model's raw predictions.
However, the notebook's own single-transaction demo cell (142) predicts
transaction_category directly from the model and does NOT call this function.
In other words: the notebook's *measured* accuracy includes these overrides,
but its *demoed* inference path doesn't use them.

This backend applies the override by default (to match the accuracy numbers
the models were actually selected/reported on). Set
ENABLE_CATEGORY_OVERRIDES=false in backend/.env to get raw model output only,
matching Cell 142's behaviour instead.
"""
import re

# ---- Ported verbatim from Cell 20 (_BUSINESS_SUFFIXES, _ANON_TRAVEL_KEYWORDS) ----
BUSINESS_SUFFIXES = [
    "limited", " ltd", "ltd.", "enterprises", "company",
    "hardware", "supplies", "supply", "cosmetics",
    "technologies", "technology", "systems", "solutions", "services",
    "products", "traders", "trading", "shop", "stores", "supermarket",
    "mart", "market", "kopo kopo", "kopokopo", "wholesale", "distributors",
    "industries", "farmers", "farm", "farms", "agri", "agriculture",
    "water company", "water refill", "gas supply", "lpg",
]

ANON_TRAVEL_KEYWORDS = [
    "petrol", "petroleum", "diesel", "fuel", "energy",
    "gas station", "filling station", "service station", "fuel station",
    "petrol station", "shell", "total energ", "rubis", "kobil",
    "ola energy", "vivo energy", "hashi energy", "gulf energy",
    "national oil", "astrol",
    "sacco", "matatu", "shuttle", "coach", "taxi", "cab", "boda",
    "transport", "logistics", "movers", "courier",
    "railway", "sgr", "airline", "airways", "airport",
    "hotel", "lodge", "resort", "inn", "guest house",
]

# ---- Ported verbatim from Cells 42/44 (HARD_RETAIL_OVERRIDE, HARD_TRAVEL_OVERRIDE) ----
HARD_RETAIL_OVERRIDE = [
    "naivas", "quick mart", "quickmart", "clean shelf", "gravity supermarket",
    "carrefour", "chandarana", "eastmatt", "magunas", "maathai",
    "tumaini", "kassmatt", "woolmatt", "saimo", "focus groceries", "jifa shopping",
    "99 mart limited", "khetia drapers", "eastleigh mattresses limited",
    "eastleigh mattress limited", "nila pharmaceuticals ltd", "krispine beauty shop",
    "enterprise", "tedmart", "jaza", "butchery", "freshener butchery",
    "manda butchery", "lizzie butchery", "bites and flavour butchery",
    "dean village enterprises", "best farmers", "upwork", "upwork freelance writers",
]

HARD_TRAVEL_OVERRIDE = [
    "buruburu sacco", "tavern", "munchies", "gatwe bar",
    "pick chick", "side java", "pizza inn", "shell", "petroleum station",
    "resort", "petrol station", "diesel",
]


import re

def extract_business_name(text: str) -> str:
    """
    Extracts the merchant/business name while removing Safaricom footer text.
    """
    if not isinstance(text, str):
        return ""

    # Normalize whitespace
    t = re.sub(r"\s+", " ", text).strip()

    # Remove common Safaricom footer/help text
    t = re.split(
        r"(?:For self-help dial|\| Web:|Web:|Twitter:|Facebook:|Terms and conditions apply)",
        t,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    # Merchant Payment
    m = re.search(
        r"Merchant Payment.*?\d+\s*-\s*(.*?)(?:\s+for which it was provided|$)",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # Business Payment
    m = re.search(
        r"Business Payment.*?\d+\s*-\s*(.*?)(?:\s+for which it was provided|$)",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # Pay Bill
    m = re.search(
        r"Pay Bill.*?\d+\s*-\s*(.*?)(?:\s+Acc\..*|$)",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    return ""


def post_process_category(predicted_category: str, details: str) -> tuple:
    """
    Ported from `post_process_predictions()` (Cells 42/44). Operates on a
    single transaction rather than a batch array, but applies the identical
    rule order. Never raises.

    Returns (final_category, override_applied: bool).
    """
    try:
        biz = extract_business_name(details).lower()
        if not biz:
            return predicted_category, False

        # 1. BUSINESS_#/PERSON_# alias handling (highest priority)
        if re.match(r"(business|person)_\d+", biz):
            if any(sfx in biz for sfx in BUSINESS_SUFFIXES):
                return "Retail & Shopping", True
            if any(kw in biz for kw in ANON_TRAVEL_KEYWORDS):
                return "Travel & Leisure", True
            return predicted_category, False

        # 2. Hard keyword overrides
        if any(h in biz for h in HARD_RETAIL_OVERRIDE):
            return "Retail & Shopping", True
        if any(h in biz for h in HARD_TRAVEL_OVERRIDE):
            return "Travel & Leisure", True

        # 3. Pizza enterprise/ltd special case
        if "pizza" in biz:
            if any(x in biz for x in ["enterprise", "ltd", "limited"]):
                return "Retail & Shopping", True
            return "Travel & Leisure", True

        return predicted_category, False
    except Exception:
        # Never let a malformed detail string break the pipeline.
        return predicted_category, False


# ---------------------------------------------------------------------------
# Deterministic label -> category rule, ported 1:1 from `assign_category_fixed`
# (notebook cell 29). Unlike the business-name overrides above (which refine
# ambiguous cases), category for THESE labels is a 100% deterministic
# function of label in the training ground truth -- there's no keyword
# judgment call involved, so the category model shouldn't be trusted over
# this rule, especially for a label that post_process_label just corrected
# (the category model never saw the corrected label/text combination during
# training). 'Buy Goods' is deliberately excluded here: assign_category_fixed
# only *defaults* it to Retail & Shopping, and the business-name overrides
# above already provide a more specific Retail vs Travel & Leisure signal for
# it -- forcing it here would bypass that finer-grained logic.
# Category is a deterministic function of CLASSIFICATION (not label), per
# architecture clarification: label and classification are independent,
# each derived only from details; category depends on (details,
# classification). This covers the full set of classification values --
# mirroring assign_category_fixed()'s original label-keyed mapping, but
# keyed on classification instead. 'Buy Goods' is deliberately excluded:
# assign_category_fixed only *defaults* it to Retail & Shopping, and the
# business-name overrides above already provide a more specific Retail vs
# Travel & Leisure signal for it -- forcing it here would bypass that
# finer-grained logic.
_DETERMINISTIC_CLASSIFICATION_CATEGORY = {
    "Airtime": "Utilities & Bills",
    "Bundles": "Utilities & Bills",
    "Transaction Fees": "Extra Charges",
    "Mshwari": "Finance & Insurance",
    "Interest": "Finance & Insurance",
    "Withdraw": "Finance & Insurance",
    "Fuliza": "Finance & Insurance",
    "Send Money": "Peer to Peer",
    "Receive Money": "Peer to Peer",
    "Paybill": "Utilities & Bills",
    "Pochi la Biashara": "Retail & Shopping",
}


def apply_classification_category_rule(predicted_category: str, transaction_classification: str) -> tuple:
    """
    Returns (final_category, override_applied: bool). Never raises.
    Call this BEFORE post_process_category so the business-name refinement
    (which only meaningfully applies to Buy Goods) still gets a chance to run.
    """
    try:
        forced = _DETERMINISTIC_CLASSIFICATION_CATEGORY.get(transaction_classification)
        if forced is not None and forced != predicted_category:
            return forced, True
        return predicted_category, False
    except Exception:
        return predicted_category, False