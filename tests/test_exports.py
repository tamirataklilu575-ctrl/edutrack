"""Tests for the CSV export feature."""

from datetime import date

import pytest

import app as app_module
from csv_tools import build_csv, safe_cell
from helpers import attendance_data, marks_data

TODAY = date(2026, 10, 20)


def csv_text(response):
    """Decode a CSV response (dropping the byte order mark)."""
    return response.data.decode("utf-8-sig")


@pytest.fixture
def admin_client(auth_client, monkeypatch):
    """The signed-in admin client, with 'today' fixed to TODAY."""
    monkeypatch.setattr(app_module, "today_local", lambda: TODAY)
    return auth_client


@pytest.fixture
def teacher(teacher_client, monkeypatch):
    monkeypatch.setattr(app_module, "today_local", lambda: TODAY)
    return teacher_client


# --------------------------------------------------------------- CSV helpers


def test_safe_cell_blocks_formulas():
    assert safe_cell("=1+1") == "'=1+1"
    assert safe_cell("@SUM(A1)") == "'@SUM(A1)"
    assert safe_cell("+cmd") == "'+cmd"
    assert safe_cell("-5x") == "'-5x"


def test_safe_cell_keeps_normal_values():
    assert safe_cell("Abebe Kebede") == "Abebe Kebede"
    assert safe_cell("+251911000001") == "+251911000001"
    assert safe_cell("85") == "85"
    assert safe_cell(None) == ""
    assert safe_cell(7) == 7


def test_build_csv_has_bom_and_quotes_commas():
    text = build_csv(["Name", "Note"], [["Abebe, K", "=1+1"]])
    assert text.startswith("\ufeff")
    assert '"Abebe, K"' in text
    assert "'=1+1" in text


# ---------------------------------------------------------- Students export


def test_students_export_requires_login(client):
    response = client.get("/students/export.csv")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_students_export_downloads_csv(admin_client):
    response = admin_client.get("/students/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.content_type
    assert "attachment" in response.headers["Content-Disposition"]

    text = csv_text(response)
    assert "ID,Name,Grade,Section,Gender,Parent Phone,Status" in text
    assert "1,Abebe Kebede,9,A,Male,+251911000001,Active" in text


def test_students_export_filename_uses_school_date(admin_client):
    response = admin_client.get("/students/export.csv")
    assert "students_2026-10-20.csv" in response.headers["Content-Disposition"]


def test_students_export_respects_grade_filter(admin_client):
    text = csv_text(admin_client.get("/students/export.csv?grade=10"))
    assert "Selam Tadesse" in text
    assert "Abebe Kebede" not in text


def test_students_export_neutralises_formula_names(admin_client):
    admin_client.post(
        "/students/add",
        data={
            "name": "=SUM(A1)",
            "grade": "9",
            "section": "A",
            "gender": "Male",
            "parent_phone": "",
            "status": "Active",
        },
    )
    text = csv_text(admin_client.get("/students/export.csv"))
    assert "'=SUM(A1)" in text
    assert ",=SUM(A1)" not in text


def test_teacher_cannot_export_students(teacher):
    response = teacher.get("/students/export.csv", follow_redirects=True)
    assert b"do not have permission" in response.data


# ------------------------------------------------------- Class report export


def test_class_report_export_requires_login(client):
    response = client.get("/class-report/export.csv")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_class_report_export_contents(admin_client):
    admin_client.post("/marks", data=marks_data())

    response = admin_client.get(
        "/class-report/export.csv?grade=9&section=A&term=Semester+1"
    )
    assert response.status_code == 200
    assert "class_report_grade9_A_Semester-1.csv" in (
        response.headers["Content-Disposition"]
    )

    text = csv_text(response)
    assert (
        "Rank,Name,Amharic,English,Mathematics,Physics,Chemistry,Biology,Civics,"
        "Total,Average,Remark,Result"
    ) in text
    assert "1,Abebe Kebede,,,85,,,,,85,85.0,Very Good,Pass" in text
    assert "Subject Average" in text


def test_teacher_can_export_class_report(teacher):
    response = teacher.get("/class-report/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.content_type


# ---------------------------------------------------------- Backup exports


def test_marks_export(admin_client):
    admin_client.post("/marks", data=marks_data())

    text = csv_text(admin_client.get("/export/marks.csv"))
    assert "Student ID,Name,Grade,Section,Term,Subject,Score" in text
    assert "1,Abebe Kebede,9,A,Semester 1,Mathematics,85" in text


def test_attendance_export(admin_client):
    admin_client.post("/attendance", data=attendance_data("Present"))

    text = csv_text(admin_client.get("/export/attendance.csv"))
    assert "Student ID,Name,Grade,Section,Date,Status" in text
    assert "1,Abebe Kebede,9,A,2026-10-20,Present" in text


def test_teacher_cannot_export_marks_or_attendance(teacher):
    for url in ("/export/marks.csv", "/export/attendance.csv"):
        response = teacher.get(url, follow_redirects=True)
        assert b"do not have permission" in response.data


# --------------------------------------------------------------- Export page


def test_export_page_for_admin(admin_client):
    response = admin_client.get("/export")
    assert response.status_code == 200
    assert b"Export Data" in response.data
    assert b"/export/marks.csv" in response.data


def test_export_page_blocked_for_teacher(teacher):
    response = teacher.get("/export", follow_redirects=True)
    assert b"do not have permission" in response.data
