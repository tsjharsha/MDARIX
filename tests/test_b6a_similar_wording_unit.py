"""B6a P1 (D8): the word-overlap score and its bounds, with no database (scenario row B6-41's maths)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from backend.app.intake import rules, service

pytestmark = pytest.mark.unit
PRODUCT, OTHER = uuid.uuid4(), uuid.uuid4()


def _side(text: str, product=PRODUCT, day=date(2026, 11, 1)) -> dict:
    return {"product_id": product, "event_on": day, "words": rules.words(text)}


def test_words_are_normalized_without_stop_words_or_punctuation():
    assert rules.words("The pump's ALARM, during the night-shift.") == {"pump", "s", "alarm", "night", "shift"}
    assert rules.words(None) == frozenset()


def test_the_score_is_shared_words_over_all_words():
    left, right = rules.words("pump alarm night"), rules.words("pump alarm day")
    assert rules.word_overlap(left, right) == pytest.approx(2 / 4)
    assert rules.word_overlap(left, frozenset()) == 0.0
    assert rules.word_overlap(left, left) == 1.0


def test_at_half_the_words_or_more_the_pair_is_suggested_with_the_percentage():
    # 2 shared of 4: exactly the threshold (B6a-D8: 0.5 or above).
    assert rules.wording_reason(_side("pump alarm night"), _side("pump alarm day")) == (
        "similar description (50 % words in common)"
    )
    # 5 shared of 8 words: 62 %.
    left = _side("infusion pump occlusion alarm sounded repeatedly saline")
    right = _side("pump occlusion alarm sounded repeatedly bolus")
    assert rules.wording_reason(left, right) == "similar description (62 % words in common)"
    # Below the threshold: 1 shared of 3.
    assert rules.wording_reason(_side("pump alarm"), _side("pump cracked")) is None


def test_the_bounds_product_and_ninety_days():
    same = "pump occlusion alarm sounded"
    assert rules.wording_reason(_side(same), _side(same, product=OTHER)) is None
    assert rules.wording_reason(_side(same), _side(same, product=None)) is not None  # one without a product
    assert rules.wording_reason(_side(same), _side(same, day=date(2026, 8, 3))) is not None  # 90 days
    assert rules.wording_reason(_side(same), _side(same, day=date(2026, 8, 2))) is None  # 91 days
    assert rules.wording_reason(_side(same), _side(same, day=None)) is not None  # no event date on one


def test_switched_off_only_todays_rule(monkeypatch):
    same = "pump occlusion alarm sounded"
    fields = [_side(same), _side(same)]
    assert service.similar_pairs(fields) == [(0, 1)]
    monkeypatch.setenv("MDARIX_B6_SIMILAR_WORDING", "off")
    assert rules.wording_reason(*fields) is None and service.similar_pairs(fields) == []


def test_the_pairs_compared_are_bounded():
    fields = [_side(f"pump alarm {n}", product=PRODUCT if n % 2 else OTHER) for n in range(rules.SIMILAR_SCAN + 50)]
    fields.append(_side("no product here", product=None))
    pairs = service.similar_pairs(fields)
    compared = {index for pair in pairs for index in pair}
    assert len(compared) <= rules.SIMILAR_SCAN
    # Never two records of different products.
    assert all(
        not fields[a]["product_id"] or not fields[b]["product_id"] or fields[a]["product_id"] == fields[b]["product_id"]
        for a, b in pairs
    )
