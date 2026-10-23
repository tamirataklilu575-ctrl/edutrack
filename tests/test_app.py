"""Automated tests for EduTrack."""

import pytest

import app as app_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client that uses a temporary database."""
    monkeypatch.setattr(app_module, "DATABASE", tmp_path / "test.db")
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client


def test_dashboard_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_student_list_shows_seed_data(client):
    response = client.get("/students")
    assert response.status_code == 200
    assert b"Abebe Kebede" in response.data


def test_add_student_success(client):
    response = client.post(
        "/students/add",
        data={"name": "Test Student", "course": "Biology", "status": "Active"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Student added successfully!" in response.data
    assert b"Test Student" in response.data


def test_add_student_empty_name_shows_error(client):
    response = client.post(
        "/students/add",
        data={"name": "", "course": "Biology", "status": "Active"},
    )
    assert response.status_code == 200
    assert b"Full name is required." in response.data


def test_add_student_short_name_shows_error(client):
    response = client.post(
        "/students/add",
        data={"name": "A", "course": "Biology", "status": "Active"},
    )
    assert b"at least 2 characters" in response.data


def test_add_student_invalid_status_shows_error(client):
    response = client.post(
        "/students/add",
        data={"name": "Test Student", "course": "Biology", "status": "Hacked"},
    )
    assert b"Please choose a valid status." in response.data


def test_edit_student(client):
    response = client.post(
        "/students/1/edit",
        data={"name": "Abebe Updated", "course": "Math", "status": "Inactive"},
        follow_redirects=True,
    )
    assert b"Student updated successfully!" in response.data
    assert b"Abebe Updated" in response.data


def test_delete_student(client):
    response = client.post("/students/1/delete", follow_redirects=True)
    assert b"Student deleted." in response.data
    assert b"Abebe Kebede" not in response.data


def test_search_filters_results(client):
    response = client.get("/students?q=selam")
    assert b"Selam Tadesse" in response.data
    assert b"Abebe Kebede" not in response.data


def test_unknown_student_returns_404(client):
    response = client.get("/students/999/edit")
    assert response.status_code == 404


def test_unknown_page_returns_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404