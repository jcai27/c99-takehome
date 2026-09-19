"""
Unit tests for lib/hierarchy.py -- resolving the indent-encoded parent/child
structure hidden in a flat USITC export.

Fixtures below are shaped exactly like the real data: a heading with its own
htsno and no rate, a headerless "superior" row with none at all, and a
10-digit statistical suffix -- the three row shapes that drove the schema's
parent_hts/context_text design (see db/schema.sql's comments on `hts_base`
and `rule`, and SUBMISSION.md).
"""

from lib.hierarchy import resolve


def _row(htsno, indent, description, superior=None, general=""):
    return {
        "htsno": htsno,
        "indent": str(indent),
        "description": description,
        "superior": superior,
        "general": general,
    }


def test_flat_rows_have_no_parent():
    rows = [_row("0101.21.00", 0, "Purebred breeding animals", general="Free")]
    nodes = resolve(rows)
    assert nodes[0].parent_htsno is None
    assert nodes[0].context_text == "Purebred breeding animals"


def test_stat_suffix_inherits_the_nearest_htsno_ancestor():
    rows = [
        _row("0101.21.00", 2, "Purebred breeding animals", general="Free"),
        _row("0101.21.00.10", 3, "Males"),
        _row("0101.21.00.20", 3, "Females"),
    ]
    nodes = resolve(rows)
    males = next(n for n in nodes if n.htsno == "0101.21.00.10")
    females = next(n for n in nodes if n.htsno == "0101.21.00.20")
    assert males.parent_htsno == "0101.21.00"
    assert females.parent_htsno == "0101.21.00"


def test_headerless_superior_row_is_never_a_parent_but_its_text_carries_forward():
    """Mirrors the real 9903.01.13 case: a headerless 'superior' row states
    an exclusion clause, and its child heading's legal scope depends on that
    text even though the row itself has no htsno to be a foreign key."""
    rows = [
        _row("9903.01.10", 0, "Except for products described in headings 9903.01.11..."),
        _row("9903.01.11", 0, "Articles the product of Canada that are donations..."),
        _row(
            "",
            0,
            "Except for products described in headings 9903.01.11, 9903.01.12, "
            "9903.01.14 and 9903.01.15 and articles the product of Canada:",
            superior="true",
        ),
        _row("9903.01.13", 1, "Crude oil, natural gas, lease condensates..."),
    ]
    nodes = resolve(rows)
    child = next(n for n in nodes if n.htsno == "9903.01.13")
    assert child.parent_htsno is None  # no ancestor has its own htsno at indent 0 here
    assert "Except for products described in headings 9903.01.11" in child.context_text
    assert "Crude oil, natural gas" in child.context_text


def test_context_text_concatenates_ancestor_chain_in_document_order():
    rows = [
        _row("0101", 0, "Live horses, asses, mules and hinnies:"),
        _row("0101.90", 1, "Other:"),
        _row("0101.90.10", 2, "Asses"),
    ]
    nodes = resolve(rows)
    leaf = next(n for n in nodes if n.htsno == "0101.90.10")
    assert leaf.parent_htsno == "0101.90"
    assert leaf.context_text == "Live horses, asses, mules and hinnies: Other: Asses"


def test_sibling_after_a_deeper_child_does_not_inherit_that_childs_ancestry():
    """A dedent back to indent 0 must pop the stack -- a following sibling
    shouldn't see the previous branch's deeper context."""
    rows = [
        _row("0101", 0, "Live horses, asses, mules and hinnies:"),
        _row("0101.90", 1, "Other:"),
        _row("0101.90.10", 2, "Asses"),
        _row("0102", 0, "Live bovine animals:"),
    ]
    nodes = resolve(rows)
    sibling = next(n for n in nodes if n.htsno == "0102")
    assert sibling.parent_htsno is None
    assert sibling.context_text == "Live bovine animals:"
