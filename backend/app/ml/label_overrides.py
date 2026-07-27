"""
Deterministic post-processing overrides for `transaction_label`.

Background — a gap between the notebook's label and classification rules:

  get_transaction_label() (defines transaction_label ground truth) only
  recognizes Send Money via one narrow phrase:
      'customer send money to micro', 'offnet c2b transfer to'
  Anything else falls through to 'Other'.

  get_transaction_classification() (defines transaction_classification
  ground truth) is broader and checks the substring directly:
      if 'fuliza' in d: return 'Fuliza'
      if 'send money' in d and 'reversal' not in d: return 'Send Money'

  So a detail containing both "Fuliza" and "Send Money" legitimately gets
  Label='Other' / Classification='Fuliza' under the ORIGINAL notebook rules
  -- the label model was trained to replicate that gap faithfully.

Per product intent: label should describe WHAT HAPPENED (the transaction
type/action), classification should describe the BEHAVIOR on top of it.
Under that principle, a Fuliza-funded Send Money should be:
    Label:          Send Money   (what happened)
    Classification: Fuliza       (the behavior / funding source)

This override closes that gap at inference time -- without retraining --
by re-checking the raw text for 'send money' whenever the model's raw
predicted label doesn't already capture it. It deliberately mirrors the
classification rule's own 'reversal' guard so a "Send Money Reversal" still
routes to Receive Money (as get_transaction_label's broader keyword list
already handles), not Send Money.

Set ENABLE_LABEL_OVERRIDES=false in .env to get raw model output only.
"""

# Labels that already correctly represent a Send Money action; the override
# should not stomp on them or anything more specific the model got right.
_ALREADY_SPECIFIC = {"Send Money", "Receive Money"}


def post_process_label(predicted_label: str, details: str) -> tuple:
    """
    Returns (final_label, override_applied: bool). Never raises.
    """
    try:
        if not isinstance(details, str) or not details:
            return predicted_label, False

        d = details.replace("\n", " ").strip().lower()

        if predicted_label in _ALREADY_SPECIFIC:
            return predicted_label, False

        if "send money" in d and "reversal" not in d:
            return "Send Money", True

        return predicted_label, False
    except Exception:
        # Never let a malformed detail string break the pipeline.
        return predicted_label, False