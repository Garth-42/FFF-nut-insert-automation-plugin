"""Name matching cases from docs/SPEC.md."""

import pytest

from nutcore.naming import looks_like_nut, match_key


@pytest.mark.parametrize("name", ["NUT_M3SQ", "NUT_M3SQ:1", "NUT_M3SQ v2:1", "NUT_M3SQ (2)",
                                  "nut_m3sq-3", "Bracket/NUT_M3SQ", "NUT_M3SQ.step"])
def test_names_that_match(name):
    assert match_key(name, ["M3SQ"]) == "M3SQ"
    assert looks_like_nut(name)


@pytest.mark.parametrize("name", ["DONUT_M3SQ", "NUT_M3SQX", "NUTM3SQ"])
def test_names_that_do_not_match(name):
    assert match_key(name, ["M3SQ"]) is None


def test_only_real_nut_markers_count_as_nuts():
    assert not looks_like_nut("DONUT_M3SQ")
    assert not looks_like_nut("NUTM3SQ")
    assert looks_like_nut("NUT_M3SQX")      # a nut name with no library entry: an error


def test_longest_key_wins():
    assert match_key("NUT_M3SQ_THIN:1", ["M3SQ", "M3SQ_THIN"]) == "M3SQ_THIN"
    assert match_key("NUT_M3SQ_THIN:1", ["M3SQ_THIN", "M3SQ"]) == "M3SQ_THIN"
