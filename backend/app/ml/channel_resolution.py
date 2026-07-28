"""
Structural resolver for C2B / B2B transaction text.

Background (Safaricom Daraja API terminology, not in the notebook):
    C2B (Customer to Business) -- a customer paying a business's Paybill or
    Till. It's an umbrella API term, not a distinct product: structurally
    it's always EITHER a Buy Goods (till only) or a Paybill (till +
    account reference) payment underneath.
    B2B (Business to Business) -- one business paying another's Paybill.
    Same structural resolution applies: till only -> Buy Goods pattern,
    till + account -> Paybill pattern.
    B2C (Business to Customer) -- money going the OTHER way, to a
    customer's phone/wallet (refunds, payouts). This is structurally
    different (destination is a phone number, not a till) and is NOT
    handled here -- it already has a home via the notebook's existing
    'offnet b2c transfer by' -> Receive Money keyword rule.

Rather than inventing brand-new 'C2B'/'B2B' label/classification classes
(which the trained models were never built to output, and which
_safe_encode would silently fall back to class-0 for), C2B/B2B text is
resolved into the EXISTING Buy Goods / Paybill taxonomy by structure:
does the text contain just a till/shortcode number, or a till number PLUS
an account reference? Category then follows whichever it resolves to,
using the existing business-name/keyword refinement (post_process_category)
rather than a fixed value -- so it isn't artificially limited to one
category.

NOTE: this pattern was designed from a description of the structural rule,
not a real sample of C2B/B2B statement text -- verify against real
examples and adjust the regexes below if the actual wording differs.
"""
import re

_ACCOUNT_REF_RE = re.compile(r"\bacc(?:ount)?\.?\s*(?:no\.?|number)?\s*[:\-]?\s*\w+", re.IGNORECASE)
_TILL_RE = re.compile(r"\b\d{5,7}\b")


def resolve_c2b_b2b(details: str):
    """
    Returns 'Buy Goods', 'Paybill', or None (not a C2B/B2B text, or
    couldn't determine structure). Never raises.
    """
    try:
        if not isinstance(details, str) or not details:
            return None
        d = details.replace("\n", " ").strip().lower()

        if "c2b" not in d and "b2b" not in d:
            return None

        has_till = bool(_TILL_RE.search(d))
        has_account = bool(_ACCOUNT_REF_RE.search(d))

        if has_till and has_account:
            return "Paybill"
        if has_till:
            return "Buy Goods"
        return None
    except Exception:
        return None