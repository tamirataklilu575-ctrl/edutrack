"""Shared pytest settings and fixtures."""

import pytest

import app as app_module
from helpers import add_teacher, load_sample, login, register


@pytest.fixture(autouse=True)
def use_sqlite_for_tests(monkeypatch):
    """Always run tests on a temporary SQLite database, never on PostgreSQL."""
    monkeypatch.setattr(app_module, "DATABASE_URL", "")


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """A fresh, empty database file for one test."""
    path = tmp_path / "test.db"
    monkeypatch.setattr(app_module, "DATABASE", path)
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    return path


@pytest.fixture
def client(db_path):
    """A signed-out test client."""
    return app_module.app.test_client()


@pytest.fixture
def auth_client(client):
    """A client signed in as the admin of 'Test School', with sample students.

    The sample students get IDs 1 to 5 (Abebe is 1, Hana is 5).
    """
    register(client, "boss@example.com")
    login(client, "boss@example.com")
    load_sample(client)
    return client


@pytest.fixture
def teacher_client(db_path):
    """A client signed in as a teacher of the same school as the admin."""
    admin = app_module.app.test_client()
    teacher = app_module.app.test_client()

    register(admin, "boss@example.com")
    login(admin, "boss@example.com")
    load_sample(admin)
    add_teacher(admin, "teacher@example.com")
    login(teacher, "teacher@example.com")
    return teacher


@pytest.fixture
def two_schools(db_path):
    """Two signed-in admins from two different schools, each with sample data.

    Alice's students have IDs 1 to 5; Bob's have IDs 6 to 10. Both schools
    have students with the same names, which is exactly what makes mix-ups
    easy to spot.
    """
    alice = app_module.app.test_client()
    bob = app_module.app.test_client()

    register(alice, "alice@example.com", school="Alice School")
    login(alice, "alice@example.com")
    load_sample(alice)

    register(bob, "bob@example.com", school="Bob School")
    login(bob, "bob@example.com")
    load_sample(bob)

    return alice, bob
