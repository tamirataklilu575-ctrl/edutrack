"""Tests for sample data and for migrating older databases."""

import sqlite3

import app as app_module
from helpers import login, register


def count(db_path, table):
    check = sqlite3.connect(db_path)
    try:
        return check.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        check.close()


# --------------------------------------------------------------- Sample data


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


# ----------------------------------------------------------------- Migration


def build_pre_school_database(path, user_column="email"):
    """Create a database as it looked before schools and logins existed."""
    old = sqlite3.connect(path)
    old.executescript(
        f"""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {user_column} TEXT NOT NULL UNIQUE,
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
        INSERT INTO users ({user_column}, password_hash, role)
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
    logins = [r[0] for r in check.execute("SELECT login FROM users ORDER BY id")]
    roles = [r[0] for r in check.execute("SELECT role FROM users ORDER BY id")]
    actives = {r[0] for r in check.execute("SELECT active FROM users")}
    student_count = check.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    columns = [r[1] for r in check.execute("PRAGMA table_info(users)")]
    check.close()

    assert schools == [(1, app_module.LEGACY_SCHOOL_NAME)]
    assert user_schools == {1}
    assert student_schools == {1}
    assert logins == ["old@example.com", "old2@example.com"]  # nobody was lost
    assert roles == ["admin", "teacher"]  # roles are kept
    assert actives == {1}  # everyone stays active
    assert student_count == 2
    assert "email" not in columns and "login" in columns


def test_migrated_account_can_still_log_in(tmp_path, monkeypatch):
    from werkzeug.security import generate_password_hash

    path = tmp_path / "old.db"
    build_pre_school_database(path)
    check = sqlite3.connect(path)
    check.execute(
        "UPDATE users SET password_hash = ? WHERE role = 'admin'",
        (generate_password_hash("oldpass123"),),
    )
    check.commit()
    check.close()

    monkeypatch.setattr(app_module, "DATABASE", path)
    app_module.init_db()
    app_module.app.config["TESTING"] = True

    client = app_module.app.test_client()
    response = login(client, "old@example.com", "oldpass123")

    assert response.status_code == 302
    page = client.get("/students").data
    assert b"Old Student" in page
    assert app_module.LEGACY_SCHOOL_NAME.encode() in client.get("/").data


def test_migration_is_safe_to_run_twice(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    build_pre_school_database(path)
    monkeypatch.setattr(app_module, "DATABASE", path)

    app_module.init_db()
    app_module.init_db()

    assert count(path, "schools") == 1
    assert count(path, "students") == 2
    assert count(path, "users") == 2


def test_fresh_database_creates_no_school(db_path):
    assert count(db_path, "schools") == 0
    assert count(db_path, "students") == 0
    assert count(db_path, "users") == 0


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
