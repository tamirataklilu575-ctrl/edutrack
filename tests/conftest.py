"""Shared pytest settings."""

import pytest

import app as app_module


@pytest.fixture(autouse=True)
def use_sqlite_for_tests(monkeypatch):
    """Always run tests on a temporary SQLite database, never on PostgreSQL."""
    monkeypatch.setattr(app_module, "DATABASE_URL", "")