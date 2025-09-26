from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture()
def srs(tmp_path, monkeypatch):
    db_path = tmp_path / "spanish-vibes-test.db"
    monkeypatch.setenv("SPANISH_VIBES_DB_PATH", str(db_path))

    import spanish_vibes.srs as srs_module

    srs_module = importlib.reload(srs_module)
    srs_module.SRS_FAST = True
    srs_module.init_db()
    return srs_module


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def test_insert_card_trims_and_sets_defaults(srs):
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    card = srs.insert_card("hola", "hello", example="ejemplo", now=now)

    assert card.front == "hola"
    assert card.back == "hello"
    assert card.example == "ejemplo"
    assert card.ease == srs.DEFAULT_EASE
    assert card.interval == 0
    assert card.reps == 0
    assert card.due_at == _iso(now)
    assert card.created_at == _iso(now)


def test_fetch_card_returns_matching_card_by_id(srs):
    now = datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)
    card = srs.insert_card("hola", "hello", now=now)

    fetched = srs.fetch_card(card.id)

    assert fetched == card


def test_list_cards_orders_newest_first_and_limits(srs):
    start = datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)
    first = srs.insert_card("uno", "one", now=start)
    second = srs.insert_card("dos", "two", now=start + timedelta(minutes=1))
    third = srs.insert_card("tres", "three", now=start + timedelta(minutes=2))

    ids_all = [card.id for card in srs.list_cards()]
    ids_limited = [card.id for card in srs.list_cards(limit=2)]

    assert ids_all == [third.id, second.id, first.id]
    assert ids_limited == [third.id, second.id]


def test_count_due_counts_only_cards_due_at_or_before_now(srs):
    now = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    due = srs.insert_card("ahora", "now", now=now)
    future = srs.insert_card("despues", "later", now=now + timedelta(minutes=5))

    assert srs.count_due(now) == 1
    assert due.id in {card.id for card in srs.list_cards()}
    assert srs.count_due(now + timedelta(minutes=5, seconds=1)) == 2
    assert srs.count_due(now - timedelta(minutes=1)) == 0


def test_next_due_card_none_when_no_cards_due(srs):
    now = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)

    assert srs.next_due_card(now) is None


def test_next_due_card_returns_earliest_due_card(srs):
    base = datetime(2024, 1, 1, 7, 0, tzinfo=timezone.utc)
    early = srs.insert_card("temprano", "early", now=base)
    later = srs.insert_card("tarde", "late", now=base + timedelta(minutes=10))

    result = srs.next_due_card(base + timedelta(minutes=1))

    assert result is not None
    assert result.id == early.id

    srs.schedule(result, "good", base + timedelta(minutes=11))

    result_after_first_due = srs.next_due_card(base + timedelta(minutes=11))
    assert result_after_first_due is not None
    assert result_after_first_due.id == later.id


def test_schedule_good_increases_reps_interval_and_ease(srs):
    created = datetime(2024, 1, 1, 6, 0, tzinfo=timezone.utc)
    card = srs.insert_card("hola", "hello", now=created)
    review_time = created + timedelta(minutes=5)

    updated = srs.schedule(card, "good", review_time)

    assert updated.reps == card.reps + 1
    assert updated.interval >= 1
    assert updated.ease > card.ease
    assert datetime.fromisoformat(updated.due_at) > review_time


def test_schedule_again_resets_progress_and_enforces_minimum_ease(srs):
    created = datetime(2024, 1, 1, 5, 0, tzinfo=timezone.utc)
    card = srs.insert_card("hola", "hello", now=created)

    first_review_time = created + timedelta(minutes=1)
    progressed = srs.schedule(card, "good", first_review_time)

    again_time = first_review_time + timedelta(minutes=5)
    reset = srs.schedule(progressed, "again", again_time)

    assert reset.reps == 0
    assert reset.interval == 1
    assert reset.ease <= progressed.ease
    assert reset.ease >= srs.MIN_EASE
    due_dt = datetime.fromisoformat(reset.due_at)
    assert due_dt - again_time == timedelta(minutes=reset.interval)


def test_round_trip_schedule_fetch_and_due_tracking(srs):
    created = datetime(2024, 1, 1, 4, 0, tzinfo=timezone.utc)
    card = srs.insert_card("hola", "hello", now=created)
    review_time = created + timedelta(minutes=2)

    scheduled = srs.schedule(card, "good", review_time)

    fetched = srs.fetch_card(card.id)
    assert fetched == scheduled

    assert srs.count_due(review_time) == 0

    due_dt = datetime.fromisoformat(scheduled.due_at)
    assert srs.count_due(due_dt + timedelta(seconds=1)) == 1
