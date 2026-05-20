"""Unit tests for the pure demurrage math. Edge cases per PROJECT_BRIEF §3.3."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from demurrage.calculations import (
    aging_bucket,
    days_overdue,
    demurrage,
    excess_days,
    trip_status,
    waiting_days,
)


# ---------- waiting_days ----------

def test_waiting_days_basic():
    assert waiting_days(date(2025, 12, 15), date(2025, 12, 20), date(2025, 12, 24)) == 4


def test_waiting_days_zero():
    """Truck offloads same day it arrives."""
    d = date(2026, 5, 10)
    assert waiting_days(date(2026, 5, 7), d, d) == 0


def test_waiting_days_accepts_datetimes():
    assert (
        waiting_days(
            datetime(2025, 12, 15),
            datetime(2025, 12, 20, 10, 0),
            datetime(2025, 12, 24, 15, 0),
        )
        == 4
    )


def test_waiting_days_missing_offload_returns_none():
    assert waiting_days(date(2026, 5, 7), date(2026, 5, 10), None) is None


def test_waiting_days_missing_arrival_returns_none():
    assert waiting_days(date(2026, 5, 7), None, date(2026, 5, 10)) is None


def test_waiting_days_rejects_offload_before_arrival():
    with pytest.raises(ValueError):
        waiting_days(date(2026, 5, 1), date(2026, 5, 10), date(2026, 5, 9))


def test_waiting_days_rejects_arrival_before_load():
    with pytest.raises(ValueError):
        waiting_days(date(2026, 5, 10), date(2026, 5, 5), date(2026, 5, 12))


# ---------- excess_days ----------

def test_excess_clipped_at_zero():
    assert excess_days(2, 2) == 0
    assert excess_days(1, 2) == 0


def test_excess_positive():
    assert excess_days(4, 2) == 2


def test_excess_passthrough_none():
    assert excess_days(None, 2) is None


def test_excess_requires_laytime_when_waiting_known():
    with pytest.raises(ValueError):
        excess_days(3, None)


def test_excess_rejects_negative():
    with pytest.raises(ValueError):
        excess_days(-1, 2)
    with pytest.raises(ValueError):
        excess_days(2, -1)


# ---------- demurrage ----------

def test_demurrage_basic():
    assert demurrage(2, 250) == 500.0


def test_demurrage_zero_excess():
    assert demurrage(0, 250) == 0.0


def test_demurrage_none_when_excess_unknown():
    assert demurrage(None, 250) is None


def test_demurrage_requires_rate_when_excess_known():
    with pytest.raises(ValueError):
        demurrage(2, None)


# ---------- trip_status ----------

def test_trip_status_pending_when_no_waiting():
    assert trip_status(None, None) == "PENDING"


def test_trip_status_demurrage_when_excess_positive():
    assert trip_status(4, 2) == "DEMURRAGE"


def test_trip_status_on_time_when_excess_zero():
    assert trip_status(2, 0) == "ON-TIME"


# ---------- aging_bucket ----------

@pytest.mark.parametrize(
    "days,expected",
    [
        (None, "Current"),
        (-5, "Current"),
        (0, "Current"),
        (1, "1-30"),
        (30, "1-30"),
        (31, "31-60"),
        (60, "31-60"),
        (61, "61-90"),
        (90, "61-90"),
        (91, "90+"),
        (365, "90+"),
    ],
)
def test_aging_bucket_boundaries(days, expected):
    assert aging_bucket(days) == expected


# ---------- days_overdue ----------

def test_days_overdue_paid_is_zero():
    assert days_overdue(date(2026, 1, 1), date(2026, 5, 20), status="Paid") == 0


def test_days_overdue_draft_returns_none():
    assert days_overdue(date(2026, 1, 1), date(2026, 5, 20), status="Draft") is None


def test_days_overdue_sent_past_due():
    assert days_overdue(date(2026, 5, 1), date(2026, 5, 20), status="Sent") == 19


def test_days_overdue_sent_future_due_clamped_to_zero():
    assert days_overdue(date(2026, 6, 1), date(2026, 5, 20), status="Sent") == 0


def test_days_overdue_no_due_date_returns_none():
    assert days_overdue(None, date(2026, 5, 20), status="Sent") is None
