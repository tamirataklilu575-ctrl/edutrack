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


@pytest.fixture
def auth_client(client):
    """A test client that is already registered and logged in."""
    client.post(
        "/register",
        data={"username": "tester", "password": "secret123", "confirm": "secret123"},
    )
    client.post("/login", data={"username": "tester", "password": "secret123"})
    return client


# ------------------------------------------------------------ Authentication


def test_dashboard_requires_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_students_requires_login(client):
    response = client.get("/students")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_register_success(client):
    response = client.post(
        "/register",
        data={"username": "newuser", "password": "secret123", "confirm": "secret123"},
        follow_redirects=True,
    )
    assert b"Account created!" in response.data


def test_register_password_mismatch(client):
    response = client.post(
        "/register",
        data={"username": "newuser", "password": "secret123", "confirm": "different"},
    )
    assert b"Passwords do not match." in response.data


def test_register_short_password(client):
    response = client.post(
        "/register",
        data={"username": "newuser", "password": "123", "confirm": "123"},
    )
    assert b"at least 6 characters" in response.data


def test_register_duplicate_username(client):
    data = {"username": "dup_user", "password": "secret123", "confirm": "secret123"}
    client.post("/register", data=data)
    response = client.post("/register", data=data)
    assert b"already taken" in response.data


def test_login_success(client):
    client.post(
        "/register",
        data={"username": "tester", "password": "secret123", "confirm": "secret123"},
    )
    response = client.post(
        "/login",
        data={"username": "tester", "password": "secret123"},
        follow_redirects=True,
    )
    assert b"Welcome back, tester!" in response.data


def test_login_wrong_password(client):
    client.post(
        "/register",
        data={"username": "tester", "password": "secret123", "confirm": "secret123"},
    )
    response = client.post(
        "/login", data={"username": "tester", "password": "wrongpass"}
    )
    assert b"Invalid username or password." in response.data


def test_logout(auth_client):
    response = auth_client.post("/logout", follow_redirects=True)
    assert b"You have been logged out." in response.data
    assert auth_client.get("/").status_code == 302


# ------------------------------------------------------------------ Students


def test_dashboard_loads(auth_client):
    response = auth_client.get("/")
    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_student_list_shows_seed_data(auth_client):
    response = auth_client.get("/students")
    assert response.status_code == 200
    assert b"Abebe Kebede" in response.data


def test_add_student_success(auth_client):
    response = auth_client.post(
        "/students/add",
        data={"name": "Test Student", "course": "Biology", "status": "Active"},
        follow_redirects=True,
    )
    assert b"Student added successfully!" in response.data
    assert b"Test Student" in response.data


def test_add_student_empty_name_shows_error(auth_client):
    response = auth_client.post(
        "/students/add",
        data={"name": "", "course": "Biology", "status": "Active"},
    )
    assert response.status_code == 200
    assert b"Full name is required." in response.data


def test_add_student_short_name_shows_error(auth_client):
    response = auth_client.post(
        "/students/add",
        data={"name": "A", "course": "Biology", "status": "Active"},
    )
    assert b"at least 2 characters" in response.data


def test_add_student_invalid_status_shows_error(auth_client):
    response = auth_client.post(
        "/students/add",
        data={"name": "Test Student", "course": "Biology", "status": "Hacked"},
    )
    assert b"Please choose a valid status." in response.data


def test_edit_student(auth_client):
    response = auth_client.post(
        "/students/1/edit",
        data={"name": "Abebe Updated", "course": "Math", "status": "Inactive"},
        follow_redirects=True,
    )
    assert b"Student updated successfully!" in response.data
    assert b"Abebe Updated" in response.data


def test_delete_student(auth_client):
    response = auth_client.post("/students/1/delete", follow_redirects=True)
    assert b"Student deleted." in response.data
    assert b"Abebe Kebede" not in response.data


def test_search_filters_results(auth_client):
    response = auth_client.get("/students?q=selam")
    assert b"Selam Tadesse" in response.data
    assert b"Abebe Kebede" not in response.data


def test_unknown_student_returns_404(auth_client):
    response = auth_client.get("/students/999/edit")
    assert response.status_code == 404


def test_unknown_page_returns_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404