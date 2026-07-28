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

Second gap considered -- an overly broad 'Pochi la Biashara' rule:

  get_transaction_label() also has:
      if d.startswith('customer transfer to'): return 'Pochi la Biashara'
  This matches ANY "Customer Transfer to..." text, including sends to a
  person's masked phone number (e.g. "Customer Transfer to - 2547******376
  JOSEPH KURIA"), not just real business-till payments. An earlier version
  of this file tried to narrow this with a masked-phone-number pattern
  check -- per explicit product clarification, that was WRONG: "Customer
  Transfer to..." is intentionally always Pochi la Biashara regardless of
  whether the destination looks like a phone number or a till. That rule
  has been removed; only an explicit "send money" in the text relabels a
  transaction, per the two rules below.

Third rule -- C2B / B2B structural resolution:

  Safaricom's C2B (Customer to Business) and B2B (Business to Business)
  are API-level umbrella terms, not the notebook's own product taxonomy --
  structurally each is always either a Buy Goods (till only) or Paybill
  (till + account reference) payment underneath. Rather than inventing new
  label classes the trained model was never built to output, C2B/B2B text
  is resolved into the existing Buy Goods/Paybill labels by structure. See
  channel_resolution.py. (B2C is different -- money going TO a customer's
  phone/wallet, not a till -- and already has a home via the notebook's
  existing 'offnet b2c transfer by' -> Receive Money rule, so it's not
  handled here.)

Set ENABLE_LABEL_OVERRIDES=false in .env to get raw model output only.
"""

from app.ml.channel_resolution import resolve_c2b_b2b


def post_process_label(predicted_label: str, details: str) -> tuple:
    """
    Returns (final_label, override_applied: bool). Never raises.

    Business rule (explicit product clarification):
      - "Customer Transfer to..." -> always Pochi la Biashara (no override
        here; this is the raw model/notebook rule's own behavior).
      - Literal "send money" in details (not a reversal) -> Label becomes
        Send Money, regardless of what the raw model predicted -- including
        'Receive Money'. An earlier version of this function exempted
        'Receive Money' as "already specific enough, don't touch it," which
        was wrong: the raw model can (and does) genuinely misclassify a
        Fuliza-funded Send Money as Receive Money at low confidence
        (observed: 29% confidence in production), and that low-confidence
        guess should not block the explicit textual evidence from
        correcting it. The only true no-op case is when the raw label is
        already 'Send Money' itself.
      - If "fuliza" ALSO appears alongside "send money" (e.g. "Fuliza Send
        Money"), the LABEL is still Send Money (label = what happened);
        it's transaction_classification that becomes 'Fuliza' instead of
        'Send Money' (see classification_overrides.py) -- classification
        captures the behavior/funding source on top of the same label.
      - "C2B"/"B2B" text resolves structurally to Buy Goods or Paybill
        (see channel_resolution.py).
    """
    try:
        if not isinstance(details, str) or not details:
            return predicted_label, False

        d = details.replace("\n", " ").strip().lower()

        if "send money" in d and "reversal" not in d:
            if predicted_label == "Send Money":
                return predicted_label, False
            return "Send Money", True

        resolved = resolve_c2b_b2b(details)
        if resolved is not None and resolved != predicted_label:
            return resolved, True

        return predicted_label, False
    except Exception:
        # Never let a malformed detail string break the pipeline.
        return predicted_label, False