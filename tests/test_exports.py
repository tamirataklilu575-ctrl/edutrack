"""Tests for the CSV export feature."""

from datetime import date

import pytest

import app as app_module
from csv_tools import build_csv, safe_cell

TODAY = date(2026, 10, 20)


# ------------------------------------------------------------------- Helpers


def register(client, email, password="secret123"):
    return client.post(
        "/register",
        data={"email": email, "password": password, "confirm": password},
    )


def login(client, email, password="secret123"):
    return client.post("/login", data={"email": email, "password": password})


def csv_text(response):
    """Decode a CSV response (dropping the byte order mark)."""
    return response.data.decode("utf-8-sig")


@pytest.fixture
def export_client(tmp_path, monkeypatch):
    """A fresh app client where 'today' is fixed to TODAY."""
    monkeypatch.setattr(app_module, "DATABASE", tmp_path / "exports.db")
    monkeypatch.setattr(app_module, "today_local", lambda: TODAY)
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client


@pytest.fixture
def admin_client(export_client):
    register(export_client, "boss@example.com")
    login(export_client, "boss@example.com")
    return export_client


@pytest.fixture
def teacher_client(export_client):
    register(export_client, "boss@example.com")
    register(export_client, "teacher@example.com")
    login(export_client, "teacher@example.com")
    return export_client


def save_mark(client):
    return client.post(
        "/marks",
        data={
            "grade": "9",
            "section": "A",
            "subject": "Mathematics",
            "term": "Semester 1",
            "score_1": "85",
        },
    )


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


def test_students_export_requires_login(export_client):
    response = export_client.get("/students/export.csv")
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


def test_teacher_cannot_export_students(teacher_client):
    response = teacher_client.get("/students/export.csv", follow_redirects=True)
    assert b"do not have permission" in response.data


# ------------------------------------------------------- Class report export


def test_class_report_export_requires_login(export_client):
    response = export_client.get("/class-report/export.csv")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_class_report_export_contents(admin_client):
    save_mark(admin_client)

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


def test_teacher_can_export_class_report(teacher_client):
    response = teacher_client.get("/class-report/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.content_type


# ---------------------------------------------------------- Backup exports


def test_marks_export(admin_client):
    save_mark(admin_client)

    text = csv_text(admin_client.get("/export/marks.csv"))
    assert "Student ID,Name,Grade,Section,Term,Subject,Score" in text
    assert "1,Abebe Kebede,9,A,Semester 1,Mathematics,85" in text


def test_attendance_export(admin_client):
    admin_client.post(
        "/attendance",
        data={
            "grade": "9",
            "section": "A",
            "date": "2026-10-20",
            "status_1": "Present",
        },
    )

    text = csv_text(admin_client.get("/export/attendance.csv"))
    assert "Student ID,Name,Grade,Section,Date,Status" in text
    assert "1,Abebe Kebede,9,A,2026-10-20,Present" in text


def test_teacher_cannot_export_marks_or_attendance(teacher_client):
    for url in ("/export/marks.csv", "/export/attendance.csv"):
        response = teacher_client.get(url, follow_redirects=True)
        assert b"do not have permission" in response.data


# --------------------------------------------------------------- Export page


def test_export_page_for_admin(admin_client):
    response = admin_client.get("/export")
    assert response.status_code == 200
    assert b"Export Data" in response.data
    assert b"/export/marks.csv" in response.data


def test_export_page_blocked_for_teacher(teacher_client):
    response = teacher_client.get("/export", follow_redirects=True)
    assert b"do not have permission" in response.data