"""Unit-тесты бизнес-правил бронирования (без базы данных)."""

from datetime import datetime, timedelta

import pytest

from app.models import BookingStatus
from app.services.booking_service import (
    ALLOWED_TRANSITIONS,
    compute_free_slots,
    intervals_overlap,
    validate_time_window,
)
from app.services.errors import BookingValidationError

NOW = datetime(2026, 11, 2, 7, 0)
DAY = datetime(2026, 11, 3)


def at(hour: int, minute: int = 0, day: datetime = DAY) -> datetime:
    return day.replace(hour=hour, minute=minute)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((10, 12), (11, 13), True),  # частичное пересечение
        ((10, 12), (10, 12), True),  # полное совпадение
        ((10, 14), (11, 12), True),  # вложенный интервал
        ((10, 11), (11, 12), False),  # соседние интервалы не конфликтуют
        ((8, 9), (15, 16), False),  # далеко друг от друга
    ],
)
def test_intervals_overlap(a, b, expected):
    assert intervals_overlap(at(a[0]), at(a[1]), at(b[0]), at(b[1])) is expected


def test_valid_window_passes():
    validate_time_window(at(10), at(12), NOW)


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        (at(12), at(10), "позже"),
        (at(10), at(10), "позже"),
        (NOW - timedelta(hours=1), NOW + timedelta(hours=1), "прошлом"),
        (at(7), at(9), "работают"),
        (at(19), at(21), "работают"),
        (at(10), at(10, 15), "Минимальная"),
        (at(9), at(15), "Максимальная"),
        (at(10, day=NOW + timedelta(days=45)), at(11, day=NOW + timedelta(days=45)), "вперёд"),
    ],
)
def test_invalid_windows_raise(start, end, message):
    with pytest.raises(BookingValidationError, match=message):
        validate_time_window(start, end, NOW)


def test_booking_across_midnight_is_rejected():
    with pytest.raises(BookingValidationError, match="один день"):
        validate_time_window(at(19), at(9, day=DAY + timedelta(days=1)), NOW)


def test_compute_free_slots_between_bookings():
    free = compute_free_slots(at(8), at(20), [(at(13), at(15)), (at(10), at(11))])
    assert free == [(at(8), at(10)), (at(11), at(13)), (at(15), at(20))]


def test_compute_free_slots_with_overlapping_and_edge_bookings():
    free = compute_free_slots(at(8), at(20), [(at(8), at(10)), (at(9), at(12)), (at(18), at(20))])
    assert free == [(at(12), at(18))]


def test_compute_free_slots_empty_day():
    assert compute_free_slots(at(8), at(20), []) == [(at(8), at(20))]


def test_final_statuses_have_no_transitions():
    assert ALLOWED_TRANSITIONS[BookingStatus.REJECTED] == set()
    assert ALLOWED_TRANSITIONS[BookingStatus.CANCELLED] == set()
    assert BookingStatus.APPROVED not in ALLOWED_TRANSITIONS[BookingStatus.APPROVED]
