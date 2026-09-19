"""
Unit tests for lib/rates.py -- the duty-rate categorization cascade.

Every case here is a real string pulled from the live scrape (see
data/runs/*/chapter99.json and base_schedule.json), not an invented example.
"""

import pytest

from lib.rates import BASE_RATE_KINDS, categorize, categorize_base


def test_free():
    r = categorize("Free")
    assert r.kind == "free"
    assert r.value is None


def test_no_change():
    assert categorize("No change").kind == "no_change"
    assert categorize("No change.").kind == "no_change"


def test_bare_ad_valorem_percent():
    r = categorize("2.5%")
    assert r.kind == "ad_valorem"
    assert r.value == 2.5


def test_additive_prose():
    r = categorize("The duty provided in the applicable subheading + 25%")
    assert r.kind == "additive"
    assert r.value == 25.0


def test_specific_compound_rate_is_not_misread_as_ad_valorem():
    r = categorize("14.27¢/ liter")
    assert r.kind == "specific"
    assert r.value is None
    assert r.text == "14.27¢/ liter"


def test_dollar_specific_rate():
    r = categorize("$0.44/kg + 6.4%")
    assert r.kind == "specific"


def test_unrecognized_text_falls_back_to_other_without_losing_it():
    r = categorize("Some future rate format nobody has seen yet")
    assert r.kind == "other"
    assert r.text == "Some future rate format nobody has seen yet"


def test_empty_is_none_not_a_fabricated_rate():
    assert categorize("") is None
    assert categorize(None) is None
    assert categorize("   ") is None


def test_whitespace_is_stripped():
    r = categorize("  Free  ")
    assert r.kind == "free"
    assert r.text == "Free"


@pytest.mark.parametrize("text", ["No change", "The duty provided in the applicable subheading + 10%"])
def test_base_coerces_rule_only_kinds_to_other(text):
    r = categorize_base(text)
    assert r.kind in BASE_RATE_KINDS
    assert r.kind == "other"
    assert r.text == categorize(text).text  # raw text is preserved even when coerced


def test_base_ad_valorem_and_free_pass_through_unchanged():
    assert categorize_base("Free").kind == "free"
    assert categorize_base("2.5%").kind == "ad_valorem"
