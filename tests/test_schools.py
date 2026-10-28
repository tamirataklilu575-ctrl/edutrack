"""Tests for creating schools, adding teachers, passwords, and migration."""

import sqlite3

import app as app_module
from helpers import add_teacher, login, register


def count(db_path, table):
    check = sqlite3.connect(db_path)
    try:
        return check.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        check.close()


# ------------------------------------------------------------- Registration


def test_registering_creates_a_school_and_an_admin(client, db_path):
    register(client, "boss@example.com", school="Green Valley High")

    assert count(db_path, "schools") == 1
    check = sqlite3.connect(db_path)
    row = check.execute("SELECT role, school_id FROM users").fetchone()
    check.close()
    assert row == ("admin", 1)


def test_second_registration_creates_a_second_school(client, db_path):
    register(client, "one@example.com", school="One")
    register(client, "two@example.com", school="Two")

    assert count(db_path, "schools") == 2
    check = sqlite3.connect(db_path)
    roles = [r[0] for r in check.execute("SELECT role FROM users ORDER BY id")]
    check.close()
    assert roles == ["admin", "admin"]


def test_duplicate_email_does_not_leave_an_empty_school(client, db_path):
    register(client, "boss@example.com", school="First")
    register(client, "boss@example.com", school="Second")

    assert count(db_path, "schools") == 1


def test_school_name_is_required(client):
    response = client.post(
        "/register",
        data={
            "school_name": "",
            "email": "boss@example.com",
            "password": "secret123",
            "confirm": "secret123",
        },
    )
    assert b"School name is required." in response.data


def test_school_name_too_short(client):
    response = client.post(
        "/register",
        data={
            "school_name": "A",
            "email": "boss@example.com",
            "password": "secret123",
            "confirm": "secret123",
        },
    )
    assert b"at least 2 characters" in response.data


def test_new_school_starts_empty(client):
    register(client, "boss@example.com")
    login(client, "boss@example.com")

    response = client.get("/students")
    assert b"No students found." in response.data


def test_empty_school_dashboard_offers_sample_data(client):
    register(client, "boss@example.com")
    login(client, "boss@example.com")

    response = client.get("/")
    assert b"Your school is empty" in response.data
    assert b"Load Sample Students" in response.data


def test_loading_sample_data_fills_the_school(client):
    register(client, "boss@example.com")
    login(client, "boss@example.com")

    response = client.post("/sample-data", follow_redirects=True)

    assert b"Sample students added." in response.data
    assert b"Abebe Kebede" in client.get("/students").data
    assert b"Your school is empty" not in client.get("/").data


def test_sample_data_cannot_be_loaded_twice(auth_client):
    response = auth_client.post("/sample-data", follow_redirects=True)
    assert b"only be added to an empty school" in response.data
    assert auth_client.get("/students").data.count(b"Abebe Kebede") == 1


def test_teacher_cannot_load_sample_data(teacher_client):
    response = teacher_client.post("/sample-data", follow_redirects=True)
    assert b"do not have permission" in response.data


# ----------------------------------------------------------- Adding teachers


def test_admin_adds_a_teacher_who_can_log_in(auth_client):
    response = add_teacher(auth_client, "new@example.com")
    assert response.status_code == 302

    teacher = app_module.app.test_client()
    result = login(teacher, "new@example.com")
    assert result.status_code == 302
    assert b"Abebe Kebede" in teacher.get("/students").data


def test_added_teacher_is_a_teacher(auth_client):
    add_teacher(auth_client, "new@example.com")

    page = auth_client.get("/users").data
    assert b"new@example.com" in page
    assert b"Make Admin" in page


def test_adding_teacher_rejects_duplicate_email(auth_client):
    add_teacher(auth_client, "new@example.com")
    response = auth_client.post(
        "/users/add",
        data={"email": "new@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    assert b"already registered" in response.data


def test_adding_teacher_rejects_bad_email_and_short_password(auth_client):
    first = auth_client.post(
        "/users/add",
        data={"email": "nope", "password": "secret123"},
        follow_redirects=True,
    )
    assert b"Enter a valid email address." in first.data

    second = auth_client.post(
        "/users/add",
        data={"email": "ok@example.com", "password": "123"},
        follow_redirects=True,
    )
    assert b"at least 6 characters" in second.data


def test_teacher_cannot_add_users(teacher_client):
    response = teacher_client.post(
        "/users/add",
        data={"email": "x@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    assert b"do not have permission" in response.data


# ----------------------------------------------------------------- Password


def test_account_page_requires_login(client):
    response = client.get("/account")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_change_password_success(auth_client):
    response = auth_client.post(
        "/account",
        data={
            "current_password": "secret123",
            "new_password": "newsecret456",
            "confirm": "newsecret456",
        },
        follow_redirects=True,
    )
    assert b"Password changed." in response.data

    fresh = app_module.app.test_client()
    assert b"Invalid email or password." in fresh.post(
        "/login",
        data={"email": "boss@example.com", "password": "secret123"},
    ).data
    assert fresh.post(
        "/login",
        data={"email": "boss@example.com", "password": "newsecret456"},
    ).status_code == 302


def test_change_password_needs_correct_current_password(auth_client):
    response = auth_client.post(
        "/account",
        data={
            "current_password": "wrong",
            "new_password": "newsecret456",
            "confirm": "newsecret456",
        },
    )
    assert b"Current password is incorrect." in response.data


def test_change_password_rejects_short_and_mismatched(auth_client):
    short = auth_client.post(
        "/account",
        data={"current_password": "secret123", "new_password": "123", "confirm": "123"},
    )
    assert b"at least 6 characters" in short.data

    mismatch = auth_client.post(
        "/account",
        data={
            "current_password": "secret123",
            "new_password": "newsecret456",
            "confirm": "different",
        },
    )
    assert b"Passwords do not match." in mismatch.data


# ----------------------------------------------------------------- Migration


def build_pre_school_database(path):
    """Create a database as it looked before schools existed."""
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'teacher'
        );
        CREATE TABLE students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grade INTEGER NOT NULL,
            section TEXT NOT NULL,
            gender TEXT NOT NULL,
            parent_phone TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Active'
        );
        INSERT INTO users (email, password_hash, role)
            VALUES ('old@example.com', 'x', 'admin'),
                   ('old2@example.com', 'x', 'teacher');
        INSERT INTO students (name, grade, section, gender)
            VALUES ('Old Student', 9, 'A', 'Male'),
                   ('Old Student Two', 10, 'B', 'Female');
        """
    )
    old.commit()
    old.close()


def test_old_database_moves_into_one_school(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    build_pre_school_database(path)
    monkeypatch.setattr(app_module, "DATABASE", path)

    app_module.init_db()

    check = sqlite3.connect(path)
    schools = check.execute("SELECT id, name FROM schools").fetchall()
    user_schools = {r[0] for r in check.execute("SELECT school_id FROM users")}
    student_schools = {r[0] for r in check.execute("SELECT school_id FROM students")}
    emails = [r[0] for r in check.execute("SELECT email FROM users ORDER BY id")]
    student_count = check.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    check.close()

    assert schools == [(1, app_module.LEGACY_SCHOOL_NAME)]
    assert user_schools == {1}
    assert student_schools == {1}
    assert emails == ["old@example.com", "old2@example.com"]  # nobody was lost
    assert student_count == 2


def test_migration_is_safe_to_run_twice(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    build_pre_school_database(path)
    monkeypatch.setattr(app_module, "DATABASE", path)

    app_module.init_db()
    app_module.init_db()

    assert count(path, "schools") == 1
    assert count(path, "students") == 2


def test_fresh_database_creates_no_school(db_path):
    assert count(db_path, "schools") == 0
    assert count(db_path, "students") == 0


def test_user_without_a_school_is_treated_as_signed_out(client, db_path):
    register(client, "boss@example.com")
    login(client, "boss@example.com")
    assert client.get("/").status_code == 200

    check = sqlite3.connect(db_path)
    check.execute("UPDATE users SET school_id = NULL")
    check.commit()
    check.close()

    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
