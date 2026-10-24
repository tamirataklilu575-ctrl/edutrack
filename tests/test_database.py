"""Tests for the database wrapper that supports SQLite and PostgreSQL."""

import pytest

import app as app_module


def test_placeholders_are_converted_for_postgres():
    db = app_module.Database(raw=None, postgres=True)
    sql = "SELECT * FROM students WHERE grade = ? AND section = ?"
    assert db.convert_sql(sql) == (
        "SELECT * FROM students WHERE grade = %s AND section = %s"
    )


def test_placeholders_are_unchanged_for_sqlite():
    db = app_module.Database(raw=None, postgres=False)
    sql = "SELECT * FROM students WHERE grade = ?"
    assert db.convert_sql(sql) == sql


def test_using_postgres_follows_database_url(monkeypatch):
    monkeypatch.setattr(
        app_module, "DATABASE_URL", "postgresql://user:pass@host/db"
    )
    assert app_module.using_postgres() is True

    monkeypatch.setattr(app_module, "DATABASE_URL", "")
    assert app_module.using_postgres() is False


def test_connection_commits_on_success_and_rolls_back_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "DATABASE", tmp_path / "wrapper.db")
    app_module.init_db()

    insert = "INSERT INTO users (email, password_hash, role) VALUES (?, ?, ?)"
    conn = app_module.get_db()

    with conn:
        conn.execute(insert, ("keep@example.com", "hash", "teacher"))

    with pytest.raises(RuntimeError):
        with conn:
            conn.execute(insert, ("lose@example.com", "hash", "teacher"))
            raise RuntimeError("something went wrong")

    emails = [row["email"] for row in conn.execute("SELECT email FROM users").fetchall()]
    conn.close()

    assert emails == ["keep@example.com"]