"""
Categorizes duty-rate prose into (kind, value, raw text).

Chapter 99 rates aren't always numbers -- "The duty provided in the
applicable subheading + 25%" is additive to a rate this table doesn't itself
hold, which a single numeric column can't express. This cascade turns the
prose in a 'general' column into a (rate_kind, rate_value) pair a query can
actually compute against, while always keeping the raw text so nothing
parsed imperfectly is silently lost -- an unrecognized pattern still lands as
'other' with its text intact, never dropped.
"""

import re
from dataclasses import dataclass

FULL_RATE_KINDS = frozenset({"free", "additive", "ad_valorem", "no_change", "specific", "other"})
BASE_RATE_KINDS = frozenset({"free", "ad_valorem", "specific", "other"})

_PCT = r"(\d+(?:\.\d+)?)\s*%"
_AD_VALOREM_RE = re.compile(rf"^{_PCT}$")
_ADDITIVE_RE = re.compile(rf"\+\s*{_PCT}")
_SPECIFIC_MARKERS = ("¢", "$", "/kg", "/liter", "/head", " each", "/doz", "/gal", "/m2")


@dataclass
class Rate:
    kind: str
    value: float | None
    text: str


def categorize(raw: str | None) -> Rate | None:
    """The general cascade -- returns None for a genuinely empty rate; the
    caller decides what that means (inherit from a parent, or leave null)."""
    text = (raw or "").strip()
    if not text:
        return None

    if text.rstrip(".") == "No change":
        return Rate(kind="no_change", value=None, text=text)

    if text == "Free":
        return Rate(kind="free", value=None, text=text)

    m = _AD_VALOREM_RE.match(text)
    if m:
        return Rate(kind="ad_valorem", value=float(m.group(1)), text=text)

    # Checked before the additive pattern: a compound rate like
    # "$0.44/kg + 6.4%" also matches "+ N%", but the presence of a specific
    # unit marker means it's a specific-plus-ad-valorem compound rate, not
    # "the applicable rate, plus N%" -- confirmed against real data (402
    # hts_base rows have exactly this shape; zero chapter99 rows do, so this
    # ordering is safe for both callers).
    if any(marker in text for marker in _SPECIFIC_MARKERS):
        return Rate(kind="specific", value=None, text=text)

    m = _ADDITIVE_RE.search(text)
    if m:
        return Rate(kind="additive", value=float(m.group(1)), text=text)

    return Rate(kind="other", value=None, text=text)


def categorize_base(raw: str | None) -> Rate | None:
    """Same cascade, coerced to hts_base's narrower rate_kind CHECK -- the
    base MFN column is never legitimately 'additive' or 'no_change' (those
    are Chapter 99 rate-*modification* concepts). If prose ever produced one
    here, that would be a surprise worth falling back safely on rather than
    failing the insert."""
    rate = categorize(raw)
    if rate is None:
        return None
    if rate.kind not in BASE_RATE_KINDS:
        return Rate(kind="other", value=None, text=rate.text)
    return rate
