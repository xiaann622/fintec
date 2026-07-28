"""
Deterministic post-processing override for `transaction_classification`,
ported from `get_transaction_classification()` in Fintech_Final_v5.ipynb
(cell 3) -- with one intentional deviation from the notebook, per explicit
architecture clarification:

    Label and classification are INDEPENDENT -- each is derived only from
    `details`. Category is what depends on (details, classification), not
    on label. The notebook's own function violates this by falling back to
    `return label` when no keyword matches:

        def get_transaction_classification(row):
            detail = row['Details']
            label  = row['transaction_label']
            ...
            if label in ('Airtime', 'Bundles'):  return 'Airtime'
            return label

    That fallback makes classification structurally dependent on label,
    which is exactly the coupling we don't want. This override instead
    falls back to the classification MODEL's own independently-trained raw
    prediction (never to label) when none of the keyword rules below fire.
    In practice this still lands on the same value in the common case
    (the model was trained to replicate the notebook's rule, including its
    label-passthrough behavior), but it no longer *forces* that outcome --
    so a genuine independent signal from the classification model itself
    is respected rather than overwritten.

Keyword rules (pure `details` lookups, unchanged from the notebook):
    'm-shwari'/'mshwari' in d          -> 'Mshwari'
    'fuliza' in d                       -> 'Fuliza'
    'send money' in d, not 'reversal'   -> 'Send Money'
    'receive'/'received'/'funds received' in d -> 'Receive Money'

Also resolves "C2B"/"B2B" structurally to Buy Goods or Paybill (see
channel_resolution.py), independently of label -- same resolution label
uses, but computed separately from the same details text rather than
copied from label's result.

Example: "Fuliza Customer Transfer to..." -> label independently determines
'Pochi la Biashara' (what happened: the payment channel), while this
override independently determines 'Fuliza' from the same text (the
behavior: funded via an overdraft that must be repaid) -- category then
follows classification -> 'Finance & Insurance', not label's usual
Pochi la Biashara -> Retail & Shopping mapping.

Set ENABLE_CLASSIFICATION_OVERRIDES=false in .env to get raw model output.
"""

from app.ml.channel_resolution import resolve_c2b_b2b


def compute_rule_classification(details: str):
    """
    Pure keyword-only re-implementation of the notebook's classification
    rules. Returns None (not a label passthrough) if no keyword applies --
    caller should fall back to the raw model's own prediction in that case.
    Never raises.
    """
    try:
        if not isinstance(details, str) or not details:
            return None
        d = details.replace("\n", " ").strip().lower()

        if "m-shwari" in d or "mshwari" in d:
            return "Mshwari"
        if "fuliza" in d:
            return "Fuliza"
        if "send money" in d and "reversal" not in d:
            return "Send Money"
        if any(x in d for x in ["receive", "received", "funds received"]):
            return "Receive Money"

        resolved = resolve_c2b_b2b(details)
        if resolved is not None:
            return resolved

        return None
    except Exception:
        return None


def post_process_classification(predicted_classification: str, details: str) -> tuple:
    """
    Returns (final_classification, override_applied: bool). Never raises.
    Depends only on `details` -- deliberately does NOT take transaction_label.
    """
    try:
        rule_result = compute_rule_classification(details)
        if rule_result is not None and rule_result != predicted_classification:
            return rule_result, True
        return predicted_classification, False
    except Exception:
        return predicted_classification, False