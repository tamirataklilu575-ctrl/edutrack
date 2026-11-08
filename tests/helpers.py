"""Small helper functions shared by the test files."""

from werkzeug.security import generate_password_hash

import app as app_module

VALID_STUDENT = {
    "name": "Test Student",
    "grade": "9",
    "section": "A",
    "gender": "Male",
    "parent_phone": "",
    "status": "Active",
}


def register(client, login_name, password="secret123", school="Test School"):
    """Create a school and its admin account directly in the database.

    There is no public registration page any more, so tests create schools the
    way the platform owner would. The ``client`` argument is kept only so older
    tests keep working; it is not used.
    """
    conn = app_module.get_db()
    try:
        with conn:
            new_school_id = app_module.create_school(conn, school)
            conn.execute(
                "INSERT INTO users (login, password_hash, role, school_id) "
                "VALUES (?, ?, 'admin', ?)",
                (login_name.strip().lower(), generate_password_hash(password), new_school_id),
            )
    finally:
        conn.close()


def login(client, login_name, password="secret123"):
    """Log in through the form."""
    return client.post("/login", data={"login": login_name, "password": password})


def load_sample(client):
    """Fill the signed-in admin's empty school with the sample students."""
    return client.post("/sample-data")


def add_teacher(admin_client, login_name, password="secret123"):
    """Create a teacher account from the signed-in admin's Users page."""
    return admin_client.post(
        "/users/add", data={"login": login_name, "password": password}
    )


def student_data(**overrides):
    """Return valid student form data with optional overrides."""
    return {**VALID_STUDENT, **overrides}


def marks_data(**overrides):
    """Return valid marks form data for Grade 9 Section A (student 1)."""
    data = {
        "grade": "9",
        "section": "A",
        "subject": "Mathematics",
        "term": "Semester 1",
        "score_1": "85",
    }
    data.update(overrides)
    return data


def attendance_data(status="Present", day="2026-10-20", student_id=1):
    """Return attendance form data for Grade 9 Section A."""
    return {
        "grade": "9",
        "section": "A",
        "date": day,
        f"status_{student_id}": status,
    }
