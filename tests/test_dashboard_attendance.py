"""Tests for the dashboard's "Attendance Today" section."""

from datetime import date

import pytest

import app as app_module
from helpers import attendance_data

TODAY = date(2026, 10, 20)
TODAY_ISO = TODAY.isoformat()


@pytest.fixture
def admin_client(auth_client, monkeypatch):
    """The signed-in admin client, with 'today' fixed to TODAY."""
    monkeypatch.setattr(app_module, "today_local", lambda: TODAY)
    return auth_client


def save_attendance(client, status, day=TODAY_ISO):
    """Record attendance for student 1 (Grade 9, Section A)."""
    return client.post("/attendance", data=attendance_data(status, day=day))


# ------------------------------------------------------------ Summary logic


def test_build_today_attendance_counts_and_rate():
    students = [
        {"id": 1, "grade": 9, "section": "A"},
        {"id": 2, "grade": 9, "section": "A"},
        {"id": 3, "grade": 10, "section": "B"},
        {"id": 4, "grade": 10, "section": "B"},
    ]
    rows = [
        {"student_id": 1, "status": "Present"},
        {"student_id": 2, "status": "Absent"},
        {"student_id": 3, "status": "Late"},
    ]

    summary = app_module.build_today_attendance(students, rows)

    assert summary["counts"] == {"Present": 1, "Absent": 1, "Late": 1, "Pending": 1}
    assert summary["total"] == 4
    assert summary["recorded"] == 3
    # Present and Late both count as attended: 2 of the 3 recorded students.
    assert summary["rate_text"] == "67%"
    assert summary["classes"][0]["grade"] == 9
    assert summary["classes"][0]["Absent"] == 1
    assert summary["classes"][1]["Pending"] == 1


def test_build_today_attendance_without_records():
    students = [{"id": 1, "grade": 9, "section": "A"}]

    summary = app_module.build_today_attendance(students, [])

    assert summary["counts"]["Pending"] == 1
    assert summary["recorded"] == 0
    assert summary["rate_text"] == "—"


def test_build_today_attendance_unknown_status_counts_as_pending():
    students = [{"id": 1, "grade": 9, "section": "A"}]
    rows = [{"student_id": 1, "status": "Weird"}]

    summary = app_module.build_today_attendance(students, rows)

    assert summary["counts"]["Pending"] == 1
    assert summary["counts"]["Present"] == 0


# ----------------------------------------------------------------- Dashboard


def test_dashboard_shows_message_when_nothing_recorded(admin_client):
    response = admin_client.get("/")
    assert response.status_code == 200
    assert b"Attendance Today" in response.data
    assert b"No attendance has been recorded today" in response.data


def test_dashboard_counts_attendance_recorded_today(admin_client):
    save_attendance(admin_client, "Absent")

    response = admin_client.get("/")

    assert b"No attendance has been recorded today" not in response.data
    assert b'data-testid="absent">1</span>' in response.data
    # Four active students, one recorded, so three are still pending.
    assert b'data-testid="pending">3</span>' in response.data
    assert b'data-testid="rate">0%</span>' in response.data


def test_dashboard_ignores_attendance_from_other_days(admin_client):
    save_attendance(admin_client, "Absent", day="2026-10-19")

    response = admin_client.get("/")

    assert b"No attendance has been recorded today" in response.data
    assert b'data-testid="absent">0</span>' in response.data


# ----------------------------------------------------------------- Time zone


def test_attendance_page_defaults_to_school_today(admin_client):
    response = admin_client.get("/attendance")
    assert f'value="{TODAY_ISO}"'.encode() in response.data


def test_today_local_returns_a_date():
    assert isinstance(app_module.today_local(), date)
