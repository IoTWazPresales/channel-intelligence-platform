"""Offline store-pin matcher (lane L5). Synthetic labels and a synthetic places table only.

No database and no network. Chain-like words and towns below are invented.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import pytest
from app.services.store_dc import place_name as pn

_ROWS = [
    # geonameid, name, ascii_name, lat, lon, feature_code
    ("1", "Brightvale", "Brightvale", -30.0, 25.0, "PPL"),
    ("2", "Mossgrove", "Mossgrove", -31.0, 26.0, "PPL"),
    ("3", "Kalmere", "Kalmere", -32.0, 27.0, "PPL"),
    ("4", "Tarnwick", "Tarnwick", -26.0, 28.0, "PPL"),
    ("5", "Tarnwick Falls", "Tarnwick Falls", -26.5, 28.5, "PPL"),
    ("6", "Oldham Reach", "Oldham Reach", -29.0, 30.0, "PPL"),
    # same name in two provinces, far apart; the admin seat comes first
    ("7", "Stonebridge", "Stonebridge", -24.0, 29.0, "PPL"),
    ("8", "Stonebridge", "Stonebridge", -33.5, 19.0, "PPLA"),
    # same name twice, but a few hundred metres apart: one place, not an ambiguity
    ("9", "Quillhaven", "Quillhaven", -28.0, 31.0, "PPL"),
    ("10", "Quillhaven", "Quillhaven", -28.001, 31.001, "PPLX"),
    ("11", "Verdant Ridge", "Verdant Ridge", -27.0, 32.0, "PPL"),
    ("12", "Zeebrugh", "Zeebrugh", -34.0, 22.0, "PPL"),
]


def _table() -> pn.PlaceTable:
    return pn.build_place_table(
        [
            {
                "geonameid": gid,
                "name": name,
                "ascii_name": ascii_name,
                "latitude": lat,
                "longitude": lon,
                "feature_code": code,
            }
            for gid, name, ascii_name, lat, lon, code in _ROWS
        ]
    )


def _propose(label, **kwargs):
    return pn.propose_store_pin(label, table=_table(), **kwargs)


# --- normalising ------------------------------------------------------------------------------


def test_normalise_folds_case_accents_punctuation_and_whitespace():
    assert pn.normalise_place("  BRÏGHT-vale,,  ") == "bright vale"
    assert pn.normalise_place("Ōldham   Reach") == "oldham reach"


def test_the_table_is_matched_on_accent_folded_names():
    table = pn.build_place_table(
        [{"geonameid": "1", "name": "Brïghtvale", "ascii_name": "", "latitude": 1, "longitude": 2, "feature_code": "PPL"}]
    )
    hit = pn.propose_store_pin("ZORBEX BRIGHTVALE MALL", table=table)
    assert hit is not None and hit["place"] == "Brïghtvale"


# --- own customer name and generic retail words -----------------------------------------------


def test_generic_retail_words_are_stripped():
    assert pn.significant_tokens("Brightvale Main Store") == ["brightvale"]
    assert pn.significant_tokens("ZORBEX Cellular Brightvale Mall Centre") == ["zorbex", "brightvale"]
    assert pn.significant_tokens("Brightvale Super Hyper Express Outlet Shop Branch Plaza Square Junction") == ["brightvale"]


def test_own_customer_name_tokens_are_stripped_but_other_words_stay():
    tokens = pn.significant_tokens("ZORBEX CORP BRIGHTVALE MALL 0412", customer_names=["Zorbex Corporation", "ZBX-01"])
    # "corp" is an abbreviation of the customer's own "corporation"; digits are store numbers
    assert tokens == ["brightvale"]


def test_a_customer_token_is_only_removed_for_that_customer():
    # The same label for a customer with another name keeps the chain-like word.
    assert pn.significant_tokens("ZORBEX BRIGHTVALE", customer_names=["Nimbo Retail"]) == ["zorbex", "brightvale"]


def test_customer_name_that_equals_a_town_is_not_used_as_the_town():
    # Customer "Mossgrove Stores": the store label's "Mossgrove" is the chain, "Kalmere" is the place.
    hit = _propose("Mossgrove Kalmere Store", customer_names=["Mossgrove Stores"])
    assert hit is not None
    assert hit["place"] == "Kalmere"


def test_no_hard_coded_brand_list_in_the_matcher_source():
    source = Path(pn.__file__).read_text(encoding="utf-8").casefold()
    for word in ("game", "makro", "hifi", "incredible", "takealot", "pick n pay", "checkers"):
        assert word not in source, word


# --- exact, contained, longest ----------------------------------------------------------------


def test_whole_label_equal_to_a_place_is_exact():
    hit = _propose("Brightvale")
    assert hit["method"] == "exact"
    assert hit["place"] == "Brightvale"
    assert (hit["latitude"], hit["longitude"]) == (-30.0, 25.0)
    assert hit["confidence"] >= 0.9
    assert hit["alternatives"] == []


def test_generic_words_around_the_town_leave_an_exact_match():
    hit = _propose("Brightvale Main Store")
    assert hit["method"] == "exact"
    assert hit["place"] == "Brightvale"


def test_town_inside_chain_words_is_contained():
    hit = _propose("ZORBEX BRIGHTVALE MALL", customer_names=["Zorbex Trading"])
    assert hit["place"] == "Brightvale"
    assert hit["method"] in {"exact", "contained"}
    hit = _propose("ZORBEX WHOLESALE BRIGHTVALE")
    assert hit["method"] == "contained"
    assert hit["place"] == "Brightvale"
    assert hit["matched_text"] == "brightvale"
    assert 0.6 <= hit["confidence"] < 0.9


def test_longest_multi_word_match_wins_over_a_shorter_one():
    hit = _propose("ZORBEX TARNWICK FALLS MALL", customer_names=["Zorbex"])
    assert hit["place"] == "Tarnwick Falls"
    assert hit["alternatives"] == []
    short = _propose("ZORBEX WHOLESALE TARNWICK")
    assert short["place"] == "Tarnwick"
    long = _propose("ZORBEX WHOLESALE TARNWICK FALLS")
    assert long["place"] == "Tarnwick Falls"
    assert long["confidence"] > short["confidence"]


def test_multi_word_place_inside_other_words():
    hit = _propose("Nimbo Cellular Oldham Reach Centre", customer_names=["Nimbo Retail"])
    assert hit["place"] == "Oldham Reach"
    assert hit["method"] == "exact"
    # without the customer's name the chain word stays, so it is only contained
    assert _propose("Nimbo Cellular Oldham Reach Centre")["method"] == "contained"


def test_the_matched_text_is_reported_for_the_steward():
    hit = _propose("ZORBEX VERDANT RIDGE MALL")
    assert hit["matched_text"] == "verdant ridge"


# --- fuzzy ------------------------------------------------------------------------------------


def test_one_letter_typo_is_a_fuzzy_match_with_lower_confidence():
    exact = _propose("ZORBEX WHOLESALE BRIGHTVALE")
    typo = _propose("ZORBEX WHOLESALE BRIGTVALE")
    assert typo["place"] == "Brightvale"
    assert typo["method"] == "fuzzy"
    assert typo["confidence"] < exact["confidence"]
    assert 0.4 <= typo["confidence"] <= 0.8


def test_fuzzy_match_of_a_two_word_place():
    hit = _propose("ZORBEX VERDENT RIDGE MALL")
    assert hit["place"] == "Verdant Ridge"
    assert hit["method"] == "fuzzy"


def test_a_short_token_never_matches_fuzzily():
    assert _propose("ZORBEX WHOLESALE BRIG") is None
    assert _propose("ZORBEX WHOLESALE KAL") is None


def test_an_unrelated_word_does_not_fuzzy_match():
    assert _propose("ZORBEX WHOLESALE HEADQUARTERS") is None


# --- ambiguity --------------------------------------------------------------------------------


def test_a_name_in_several_provinces_lowers_confidence_and_lists_alternatives():
    unique = _propose("ZORBEX WHOLESALE KALMERE")
    ambiguous = _propose("ZORBEX WHOLESALE STONEBRIDGE")
    assert ambiguous["place"] == "Stonebridge"
    assert ambiguous["ambiguous"] is True
    assert ambiguous["confidence"] < unique["confidence"]
    assert len(ambiguous["alternatives"]) == 1
    alt = ambiguous["alternatives"][0]
    # the admin-seat entry is the primary proposal, the other one is the alternative
    assert (ambiguous["latitude"], ambiguous["longitude"]) == (-33.5, 19.0)
    assert (alt["latitude"], alt["longitude"]) == (-24.0, 29.0)
    assert alt["place"] == "Stonebridge"


def test_two_entries_a_few_hundred_metres_apart_are_one_place():
    hit = _propose("ZORBEX WHOLESALE QUILLHAVEN")
    assert hit["ambiguous"] is False
    assert hit["alternatives"] == []


def test_two_different_towns_in_one_label_are_both_offered():
    hit = _propose("Kalmere Mossgrove")
    assert hit["ambiguous"] is True
    assert {hit["place"], hit["alternatives"][0]["place"]} == {"Kalmere", "Mossgrove"}
    assert hit["confidence"] < _propose("Kalmere")["confidence"]


# --- the file's own place name ----------------------------------------------------------------


def test_the_place_name_from_the_file_wins_over_the_label():
    hit = _propose("ZORBEX BRIGHTVALE MALL", place_name="Kalmere")
    assert hit["place"] == "Kalmere"


def test_the_label_is_used_when_the_place_name_matches_nothing():
    hit = _propose("ZORBEX BRIGHTVALE MALL", place_name="Head Office")
    assert hit["place"] == "Brightvale"


# --- no proposal ------------------------------------------------------------------------------


@pytest.mark.parametrize("label", [None, "", "   ", "ZORBEX HEAD OFFICE WHOLESALE", "Main Store", "0412"])
def test_no_match_gives_no_proposal(label):
    assert _propose(label) is None


def test_suggest_store_location_wraps_the_proposal_for_the_map():
    hit = pn.suggest_store_location("ZORBEX BRIGHTVALE MALL", customer_names=["Zorbex"], table=_table())
    assert hit["outcome"] == "suggest"
    assert hit["reason"] == "match"
    assert hit["place"] == "Brightvale"
    assert hit["method"] in {"exact", "contained"}
    assert hit["licence"] == pn.LICENCE_NAME
    assert isinstance(hit["alternatives"], list)
    miss = pn.suggest_store_location("ZORBEX HEAD OFFICE", table=_table())
    assert miss["outcome"] == "manual"
    assert miss["reason"] == "none"
    assert miss["latitude"] is None and miss["confidence"] is None
    assert pn.suggest_store_location(None, table=_table())["reason"] == "none"


def test_the_matcher_never_goes_online():
    source = Path(pn.__file__).read_text(encoding="utf-8")
    for word in ("urlopen", "requests", "httpx", "aiohttp", "socket"):
        assert word not in source


# --- the bundled list and speed ---------------------------------------------------------------

_BUNDLED = Path(pn.__file__).with_name("data") / "za_populated_places.csv"


def test_a_bundled_place_name_is_proposed_for_a_label_around_it():
    with _BUNDLED.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    counts: dict[str, int] = {}
    for row in rows:
        counts[pn.normalise_place(row["name"])] = counts.get(pn.normalise_place(row["name"]), 0) + 1
    row = next(
        r for r in rows
        if counts[pn.normalise_place(r["name"])] == 1 and len(pn.normalise_place(r["name"])) >= 8
        and not set(pn.normalise_place(r["name"]).split()) & pn.GENERIC_RETAIL_WORDS
    )
    hit = pn.propose_store_pin(f"QXZ WHOLESALE {row['name'].upper()} MALL")
    assert hit is not None
    assert pn.normalise_place(hit["place"]) == pn.normalise_place(row["name"])


def test_the_bundled_table_is_indexed_once():
    assert pn.default_place_table() is pn.default_place_table()


def test_hundreds_of_unmatched_labels_stay_fast():
    pn.default_place_table()
    labels = [f"QXZ {chr(97 + i % 26)}{chr(97 + (i // 26) % 26)}ploxarn WHOLESALE {i}" for i in range(300)]
    start = time.perf_counter()
    for label in labels:
        pn.propose_store_pin(label)
    assert time.perf_counter() - start < 5.0


def test_place_word_before_a_centre_word_is_a_weak_named_centre_hint() -> None:
    """BACKLOG-267 counterexample shape: "<chain> <place> Mall" names a mall, not the town."""
    table = _table()
    plain = pn.propose_store_pin("Brightvale", customer_names=["Acme"], table=table)
    mall = pn.propose_store_pin("Acme Brightvale Mall", customer_names=["Acme"], table=table)
    chain_left = pn.propose_store_pin("Globex Brightvale Mall", customer_names=["Acme"], table=table)
    assert plain["named_centre"] is None and plain["confidence"] >= 0.8
    assert mall["place"] == "Brightvale" and mall["named_centre"] == "brightvale mall"
    assert mall["confidence"] < 0.55  # Low band: never in the high-confidence bulk selection
    assert chain_left["named_centre"] == "brightvale mall" and chain_left["confidence"] < 0.55
    assert pn.suggest_store_location("Acme Brightvale Mall", customer_names=["Acme"], table=table)["reason"] == "match"
