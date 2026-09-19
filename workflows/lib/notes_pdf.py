"""
Segments the Chapter 99 notes PDF into per-scope U.S. Notes / Statistical
Notes text, then splits each into individual numbered notes.

The PDF is a mixed document: short note prose per chapter and per subchapter,
followed by the tariff table re-rendered as jumbled multi-column text (the
column order isn't even consistent across subchapters -- confirmed against
the real PDF: subchapter II's table has an extra "Effective Period" column,
III's doesn't). The table is never a data source here -- the JSON already
has it, reliably -- so it's detected and skipped by its own header
vocabulary ("Rates of Duty", "Article Description", "Heading/", "Subheading"
clustered together), not by a content pattern like a heading-number regex.
That was the first approach here, and it broke on real data: Subchapter
III's U.S. Notes legitimately contain a 400+ line embedded list of excluded
base HTS codes that is indistinguishable from a table row by content alone.
"""

import re
from dataclasses import dataclass

_SUBCHAPTER_HDR_RE = re.compile(r"^SUBCHAPTER\s+([IVXLCDM]+)\s*$", re.MULTILINE)
_US_NOTES_RE = re.compile(r"^U\.S\. Notes(?:\s*\(con\.\))?\s*$", re.MULTILINE)
_STAT_NOTES_RE = re.compile(r"^Statistical Notes(?:\s*\(con\.\))?\s*$", re.MULTILINE)
_NOTE_ITEM_RE = re.compile(r"^(\d+)\.\s+", re.MULTILINE)
# "...in lieu of the rate provided in chapters 1 through\n97." -- a range
# endpoint that happens to line-wrap onto its own line, indistinguishable
# from a note boundary by the regex above alone. Confirmed against real
# data: this is exactly why subchapter XX's real notes 2 and 3 went missing
# (swallowed into a bogus "note 97"). "chapters 1 through 97/98" is common
# boilerplate throughout these notes, so this guard checks the text
# immediately before a candidate match for the standard range-connector.
_RANGE_CONNECTOR_RE = re.compile(r"\bthrough\s*$", re.IGNORECASE)

_TABLE_HEADER_TOKENS = ("Rates of Duty", "Article Description", "Heading/", "Subheading")

_BOILERPLATE_LINE_RES = [
    re.compile(r"^[IVXLCDM]+$"),                          # bare running roman numeral
    re.compile(r"^\d+\s*-\s*[IVXLCDM]+\s*-\s*\d+$"),        # "99 - III - 434"
    re.compile(r"^\d+-\d+$"),                               # "99-1"
    re.compile(r"^Harmonized Tariff Schedule of the United States"),
    re.compile(r"^Annotated for Statistical Reporting Purposes$"),
]


@dataclass
class ScopedNote:
    scope_type: str  # 'chapter' | 'subchapter'
    subchapter: str | None  # roman numeral, or None for scope_type='chapter'
    note_type: str  # 'us' | 'statistical'
    number: int
    text: str


def extract_pages_text(reader) -> list[str]:
    return [page.extract_text() or "" for page in reader.pages]


def _is_boilerplate(line: str) -> bool:
    line = line.strip()
    if not line:
        return True
    return any(r.match(line) for r in _BOILERPLATE_LINE_RES)


def _clean(text: str) -> str:
    lines = [ln for ln in text.split("\n") if not _is_boilerplate(ln)]
    return "\n".join(lines).strip()


def _find_table_start(chunk: str) -> int | None:
    """First offset where the table's column-header vocabulary appears
    clustered together. The real header cluster (e.g. "Rates of DutyUnit\\nof
    \\nQuantity\\nArticle Description\\nStat.\\nSuf-\\nfix\\nHeading/\\n
    Subheading...") is only ~150 chars wide -- the window has to be close to
    that, not generously large, or a short subchapter whose notes and table
    both land in one big window produces a false match at the chunk's start
    (confirmed against real data: Subchapter XXI, whose single-page notes
    section was being reported as containing no notes at all because of
    this)."""
    window, step = 250, 50
    idx = 0
    while idx < len(chunk):
        piece = chunk[idx : idx + window]
        if all(tok in piece for tok in _TABLE_HEADER_TOKENS):
            return idx
        idx += step
    return None


def _split_notes(
    text: str, *, scope_type: str, subchapter: str | None, note_type: str
) -> list[ScopedNote]:
    # A note's body can itself contain a nested numbered sub-list, whose
    # items also match "^N. " -- confirmed against real data (subchapter
    # III's note text produced a duplicate "note 1" from exactly this: a
    # long note containing its own "1., 2., 3., ..." sub-enumeration).
    # Top-level notes are monotonically increasing but real gaps do occur
    # (also confirmed against real data: subchapter III's real top-level
    # notes skip from 3 straight to 5 -- a repealed/renumbered provision,
    # not an extraction bug). Requiring strict +1 succession is too rigid
    # (one real gap would permanently reject every note after it); requiring
    # *some* increase over the last accepted number tolerates real gaps
    # while still rejecting a nested sub-list, which always restarts back
    # down at 1.
    all_matches = list(_NOTE_ITEM_RE.finditer(text))
    matches = []
    last_accepted = 0
    for m in all_matches:
        if _RANGE_CONNECTOR_RE.search(text[: m.start()]):
            continue  # "chapters 1 through 97." -- a range endpoint, not a note
        num = int(m.group(1))
        if num > last_accepted:
            matches.append(m)
            last_accepted = num

    notes = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        notes.append(
            ScopedNote(
                scope_type=scope_type,
                subchapter=subchapter,
                note_type=note_type,
                number=int(m.group(1)),
                text=body,
            )
        )
    return notes


def parse(pages_text: list[str]) -> list[ScopedNote]:
    full_text = "\n".join(pages_text)

    # Locate every SUBCHAPTER boundary in the *raw* text first, before any
    # cleaning -- cleaning could shift offsets out from under these matches.
    hdr_matches = list(_SUBCHAPTER_HDR_RE.finditer(full_text))
    chapter_end = hdr_matches[0].start() if hdr_matches else len(full_text)
    scopes: list[tuple[str, str | None, int, int]] = [("chapter", None, 0, chapter_end)]
    for i, hm in enumerate(hdr_matches):
        start = hm.end()
        end = hdr_matches[i + 1].start() if i + 1 < len(hdr_matches) else len(full_text)
        scopes.append(("subchapter", hm.group(1), start, end))

    all_notes: list[ScopedNote] = []
    for scope_type, subchapter, start, end in scopes:
        chunk = full_text[start:end]
        table_start = _find_table_start(chunk)
        notes_region = chunk[:table_start] if table_start is not None else chunk

        us_m = _US_NOTES_RE.search(notes_region)
        stat_m = _STAT_NOTES_RE.search(notes_region)

        if us_m:
            us_end = stat_m.start() if stat_m and stat_m.start() > us_m.end() else len(notes_region)
            us_text = _clean(notes_region[us_m.end() : us_end])
            all_notes.extend(
                _split_notes(us_text, scope_type=scope_type, subchapter=subchapter, note_type="us")
            )

        if stat_m:
            stat_text = _clean(notes_region[stat_m.end() :])
            all_notes.extend(
                _split_notes(
                    stat_text, scope_type=scope_type, subchapter=subchapter, note_type="statistical"
                )
            )

        if not us_m and not stat_m:
            # Some subchapters (observed: XXI, XXII -- both newer free-trade-
            # agreement additions) state their numbered notes directly under
            # the SUBCHAPTER title with no "U.S. Notes" label at all. If
            # there's numbered content before the table starts, it's U.S.
            # notes in substance even though the label is missing.
            fallback_text = _clean(notes_region)
            all_notes.extend(
                _split_notes(
                    fallback_text, scope_type=scope_type, subchapter=subchapter, note_type="us"
                )
            )

    return all_notes
