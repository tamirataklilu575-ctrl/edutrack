"""Tests for the demo data script."""

import importlib.util
import sqlite3
from datetime import date
from pathlib import Path

import app as app_module
from helpers import login

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "seed_demo.py"
TODAY = date(2026, 10, 21)


def load_script():
    """Import scripts/seed_demo.py (the scripts folder is not a package)."""
    spec = importlib.util.spec_from_file_location("seed_demo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def table_count(db_path, table):
    check = sqlite3.connect(db_path)
    try:
        return check.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        check.close()


def test_seed_creates_a_demo_school(db_path):
    seed = load_script()

    result = seed.seed_demo_data(today=TODAY)

    assert result["students"] == 29
    assert result["marks"] > 0
    assert result["attendance"] > 0
    assert table_count(db_path, "schools") == 1
    assert table_count(db_path, "students") == 29


def test_seed_admin_can_log_in_and_sees_the_demo_school(db_path):
    seed = load_script()
    seed.seed_demo_data(today=TODAY)

    client = app_module.app.test_client()
    response = login(client, seed.DEMO_EMAIL, seed.DEMO_PASSWORD)

    assert response.status_code == 302
    assert b"Demo School" in client.get("/").data
    assert b"29" in client.get("/").data


def test_seed_is_safe_to_run_twice(db_path):
    seed = load_script()

    first = seed.seed_demo_data(today=TODAY)
    second = seed.seed_demo_data(today=TODAY)

    assert first is not None
    assert second is None
    assert table_count(db_path, "students") == 29
    assert table_count(db_path, "schools") == 1


def test_seed_refuses_postgres_without_flag(monkeypatch, capsys):
    monkeypatch.setattr(
        app_module, "DATABASE_URL", "postgresql://user:pass@host/db"
    )
    seed = load_script()

    assert seed.main([]) == 1
    assert "allow-postgres" in capsys.readouterr().out
