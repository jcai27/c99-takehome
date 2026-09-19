"""
Extracts Chapter 99's two structural relationships out of prose --
"references" into the base schedule, "excludes" between Chapter 99
provisions -- plus resolving citations to U.S./statistical notes, and
deriving a heading's subchapter.

Reference/exclusion extraction runs against a row's `context_text` (the
ancestor-chain text plus its own, from lib/hierarchy.py), not `description`
alone: an exclusion clause is often stated once on a headerless ancestor row
and applies, in legal effect, to every descendant heading beneath it.
Confirmed against real data (see db/schema.sql's comment on `rule`).

Code lists in the source prose mix comma/and/or separators with dash-joined
ranges ("9903.01.28-9903.01.33"), sometimes an en dash, sometimes a plain
hyphen. Rather than model that separator grammar precisely, each extractor
grabs a bounded text window after its trigger phrase and pulls every
HTS-code-or-range-shaped token out of it -- simpler, and robust to whichever
separator the prose happens to use.
"""

import re

_HTS10 = r"\d{4}\.\d{2}\.\d{2}"
# HTS codes appear at every granularity in prose: 4-digit heading ("2710"),
# 6-digit subheading ("2207.20"), 8/10-digit tariff line/statistical suffix
# ("9903.01.02"). One pattern covers all of them, used everywhere a code
# list is pulled out of a text window.
_HTSCODE = r"\d{4}(?:\.\d{2}){0,3}"
_DASH = r"[–—-]"
_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
          "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
          "XXI", "XXII", "XXIII", "XXIV", "XXV"]

_CODE_OR_RANGE_RE = re.compile(rf"({_HTSCODE})(?:\s*{_DASH}\s*({_HTSCODE}))?")

_WINDOW = 220
_STOP_WORDS_RE = re.compile(r"\b(articles|products)\s+the\s+product\b", re.IGNORECASE)

_REFERENCES_TRIGGER_RE = re.compile(r"provided for in subheadings?\s+", re.IGNORECASE)
_REFERENCES_HEADING_TRIGGER_RE = re.compile(r"provided for in headings?\s+", re.IGNORECASE)
# Both phrasings are real and both are common in the source prose -- confirmed
# against real data: "except for products described in headings X" (191
# occurrences) and "except as provided for in headings X" (123 occurrences),
# the latter previously unhandled entirely.
_EXCLUDES_TRIGGER_RE = re.compile(
    r"Except (?:for (?:products|articles)?\s*described in|as provided for in)\s+"
    r"(?:headings?|subheadings?)?\s*",
    re.IGNORECASE,
)

_NOTE_PATTERNS = [
    # (regex, note_type, subchapter_group_or_None) -- subchapter_group=0 means
    # "use the row's own subchapter", a real group index means "read it from
    # the match" (an explicit, possibly different, subchapter).
    (re.compile(r"See chapter \d+ statistical note\.?", re.I), "statistical", "chapter", None),
    (re.compile(r"See chapter \d+ statistical note (\d+)", re.I), "statistical", "chapter", 1),
    (re.compile(r"See subchapter ([IVXLCDM]+),?\s*U\.S\.\s*note (\d+)", re.I), "us", "explicit", (1, 2)),
    (re.compile(r"U\.S\.\s*note (\d+)(?:\([a-z]\))? to this sub-?\s?chapter", re.I), "us", "own", 1),
    (re.compile(r"U\.S\.\s*note (\d+)(?:\([a-z]\))? to this chapter", re.I), "us", "chapter", 1),
    (re.compile(r"\bnote (\d+)(?:\([a-z]\))? to this sub-?\s?chapter", re.I), "us", "own", 1),
    (re.compile(r"\bnote (\d+)(?:\([a-z]\))? to this chapter", re.I), "us", "chapter", 1),
    (re.compile(r"See U\.?S\.?\s*note (\d+)", re.I), "us", "own", 1),
]


def subchapter_of(htsno: str) -> str:
    """'9903.01.01' -> 'III'. Verified against the real notes PDF's own
    SUBCHAPTER page headers: heading 99XX is always subchapter roman-numeral
    XX, across every prefix present in a live revision (I, II, III, IV,
    VIII, XII, XIII, XV-XXII)."""
    n = int(htsno[2:4])
    return _ROMAN[n - 1]


def _expand_codes(window: str) -> list[str]:
    codes: list[str] = []
    for m in _CODE_OR_RANGE_RE.finditer(window):
        start, end = m.group(1), m.group(2)
        if not end or "." not in start or "." not in end:
            codes.append(start)
            if end:
                codes.append(end)
            continue
        start_prefix, start_suffix = start.rsplit(".", 1)
        end_prefix, end_suffix = end.rsplit(".", 1)
        if start_prefix == end_prefix:
            lo, hi = int(start_suffix), int(end_suffix)
            if 0 <= hi - lo <= 200:
                codes.extend(f"{start_prefix}.{n:02d}" for n in range(lo, hi + 1))
                continue
        codes.append(start)
        codes.append(end)
    return codes


def _windows_after(text: str, trigger_re: re.Pattern) -> list[str]:
    windows = []
    for m in trigger_re.finditer(text):
        window = text[m.end() : m.end() + _WINDOW]
        stop = _STOP_WORDS_RE.search(window)
        windows.append(window[: stop.start()] if stop else window)
    return windows


def extract_references(context_text: str) -> list[str]:
    codes: list[str] = []
    for trigger_re in (_REFERENCES_TRIGGER_RE, _REFERENCES_HEADING_TRIGGER_RE):
        for m in trigger_re.finditer(context_text):
            window = context_text[m.end() : m.end() + _WINDOW]
            close = window.find(")")
            if close != -1:
                window = window[:close]
            codes.extend(_expand_codes(window))
    # "references" means base codes (chapters 1-97) a provision modifies --
    # never Chapter 99 itself. Confirmed against real data: "provided for in
    # heading(s)" also appears in Chapter-99-internal cross-references like
    # "...except as provided for in headings 9903.01.34 and 9903.02.01...",
    # which isn't a base-schedule reference at all (and is now separately
    # caught by extract_exclusions's "except as provided for in" pattern).
    codes = [c for c in codes if not c.startswith("99")]
    return sorted(set(codes))


def extract_exclusions(context_text: str) -> list[str]:
    codes: list[str] = []
    for window in _windows_after(context_text, _EXCLUDES_TRIGGER_RE):
        codes.extend(_expand_codes(window))
    return sorted(set(codes))


def extract_note_refs(text: str, *, own_subchapter: str) -> list[tuple[str, str | None, int]]:
    """Returns (note_type, subchapter, number) triples -- subchapter is None
    for a chapter-scoped citation. `own_subchapter` is used when the prose
    doesn't name a scope explicitly ("See U.S. note 3", with no "to this
    subchapter"/"to this chapter" qualifier -- the common case)."""
    refs: list[tuple[str, str | None, int]] = []
    for regex, note_type, scope, group in _NOTE_PATTERNS:
        for m in regex.finditer(text):
            if group is None:
                continue  # "See chapter N statistical note." with no number -- nothing to resolve
            if scope == "explicit":
                sub_group, num_group = group
                refs.append((note_type, m.group(sub_group).upper(), int(m.group(num_group))))
            elif scope == "chapter":
                refs.append((note_type, None, int(m.group(group))))
            else:  # scope == "own"
                refs.append((note_type, own_subchapter, int(m.group(group))))
    return sorted(set(refs), key=lambda t: (t[0], t[1] or "", t[2]))
