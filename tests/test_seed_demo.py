"""Tests for the demo data script."""

import importlib.util
from datetime import date
from pathlib import Path

import app as app_module

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "seed_demo.py"
TODAY = date(2026, 10, 21)


def load_script():
    """Import scripts/seed_demo.py (the scripts folder is not a package)."""
    spec = importlib.util.spec_from_file_location("seed_demo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fresh_database(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "DATABASE", tmp_path / "seed.db")
    app_module.init_db()


def count_students():
    conn = app_module.get_db()
    try:
        return conn.execute("SELECT COUNT(*) AS total FROM students").fetchone()["total"]
    finally:
        conn.close()


def test_seed_adds_demo_data(tmp_path, monkeypatch):
    fresh_database(tmp_path, monkeypatch)
    seed = load_script()

    result = seed.seed_demo_data(today=TODAY)

    assert result["students"] == 29
    assert result["marks"] > 0
    assert result["attendance"] > 0
    # The 5 built-in sample students plus 29 demo students.
    assert count_students() == 34


def test_seed_is_safe_to_run_twice(tmp_path, monkeypatch):
    fresh_database(tmp_path, monkeypatch)
    seed = load_script()

    first = seed.seed_demo_data(today=TODAY)
    second = seed.seed_demo_data(today=TODAY)

    assert first is not None
    assert second is None
    assert count_students() == 34


def test_seed_refuses_postgres_without_flag(monkeypatch, capsys):
    monkeypatch.setattr(
        app_module, "DATABASE_URL", "postgresql://user:pass@host/db"
    )
    seed = load_script()

    assert seed.main([]) == 1
    assert "allow-postgres" in capsys.readouterr().out