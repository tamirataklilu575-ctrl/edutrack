"""Automated tests for EduTrack (high school edition)."""

import pytest

import app as app_module

VALID_STUDENT = {
    "name": "Test Student",
    "grade": "9",
    "section": "A",
    "gender": "Male",
    "parent_phone": "",
    "status": "Active",
}


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


def student_data(**overrides):
    """Return valid student form data with optional overrides."""
    return {**VALID_STUDENT, **overrides}


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


def test_dashboard_shows_grade_chart(auth_client):
    response = auth_client.get("/")
    assert b"Students by Grade" in response.data
    assert b"Grade 12" in response.data


def test_student_list_shows_seed_data(auth_client):
    response = auth_client.get("/students")
    assert response.status_code == 200
    assert b"Abebe Kebede" in response.data


def test_add_student_success(auth_client):
    response = auth_client.post(
        "/students/add", data=student_data(), follow_redirects=True
    )
    assert b"Student added successfully!" in response.data
    assert b"Test Student" in response.data


def test_add_student_empty_name_shows_error(auth_client):
    response = auth_client.post("/students/add", data=student_data(name=""))
    assert response.status_code == 200
    assert b"Full name is required." in response.data


def test_add_student_short_name_shows_error(auth_client):
    response = auth_client.post("/students/add", data=student_data(name="A"))
    assert b"at least 2 characters" in response.data


def test_add_student_invalid_grade_shows_error(auth_client):
    response = auth_client.post("/students/add", data=student_data(grade="5"))
    assert b"Please choose a grade between 9 and 12." in response.data


def test_add_student_invalid_phone_shows_error(auth_client):
    response = auth_client.post(
        "/students/add", data=student_data(parent_phone="abc")
    )
    assert b"Enter a valid phone number" in response.data


def test_add_student_invalid_status_shows_error(auth_client):
    response = auth_client.post("/students/add", data=student_data(status="Hacked"))
    assert b"Please choose a valid status." in response.data


def test_edit_student(auth_client):
    response = auth_client.post(
        "/students/1/edit",
        data=student_data(name="Abebe Updated", grade="10", status="Inactive"),
        follow_redirects=True,
    )
    assert b"Student updated successfully!" in response.data
    assert b"Abebe Updated" in response.data


def test_delete_student(auth_client):
    response = auth_client.post("/students/1/delete", follow_redirects=True)
    assert b"Student deleted." in response.data
    assert b"Abebe Kebede" not in response.data


def test_search_filters_by_name(auth_client):
    response = auth_client.get("/students?q=selam")
    assert b"Selam Tadesse" in response.data
    assert b"Abebe Kebede" not in response.data


def test_grade_filter(auth_client):
    response = auth_client.get("/students?grade=10")
    assert b"Selam Tadesse" in response.data
    assert b"Abebe Kebede" not in response.data


def test_unknown_student_returns_404(auth_client):
    response = auth_client.get("/students/999/edit")
    assert response.status_code == 404


def test_unknown_page_returns_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404

    

# ---------------------------------------------------------------- Attendance


def test_attendance_requires_login(client):
    response = client.get("/attendance")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_attendance_page_lists_class_students(auth_client):
    response = auth_client.get("/attendance?grade=9&section=A&date=2026-10-20")
    assert response.status_code == 200
    assert b"Abebe Kebede" in response.data
    assert b"Meron Bekele" not in response.data


def test_attendance_save_and_summary(auth_client):
    response = auth_client.post(
        "/attendance",
        data={
            "grade": "9",
            "section": "A",
            "date": "2026-10-20",
            "status_1": "Absent",
        },
        follow_redirects=True,
    )
    assert b"Attendance saved." in response.data
    assert b"Absent: 1" in response.data


def test_attendance_invalid_date_falls_back_to_today(auth_client):
    response = auth_client.get("/attendance?date=not-a-date")
    assert response.status_code == 200


def test_delete_student_with_attendance(auth_client):
    auth_client.post(
        "/attendance",
        data={"grade": "9", "section": "A", "date": "2026-10-20", "status_1": "Late"},
    )
    response = auth_client.post("/students/1/delete", follow_redirects=True)
    assert b"Student deleted." in response.data

    

# --------------------------------------------------------------------- Marks


MARKS_QUERY = "grade=9&section=A&subject=Mathematics&term=Semester+1"


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


def test_marks_requires_login(client):
    response = client.get("/marks")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_marks_page_lists_class_students(auth_client):
    response = auth_client.get(f"/marks?{MARKS_QUERY}")
    assert response.status_code == 200
    assert b"Abebe Kebede" in response.data
    assert b"Meron Bekele" not in response.data


def test_marks_save_and_summary(auth_client):
    response = auth_client.post("/marks", data=marks_data(), follow_redirects=True)
    assert b"Marks saved." in response.data
    assert b"Average: 85.0" in response.data


def test_marks_update_overwrites_previous_score(auth_client):
    auth_client.post("/marks", data=marks_data(score_1="70"))
    response = auth_client.post(
        "/marks", data=marks_data(score_1="90"), follow_redirects=True
    )
    assert b"Average: 90.0" in response.data
    assert b"Marked: 1" in response.data


def test_marks_rejects_score_above_100(auth_client):
    response = auth_client.post("/marks", data=marks_data(score_1="150"))
    assert response.status_code == 200
    assert b"Score must be between 0 and 100." in response.data


def test_marks_rejects_non_numeric_score(auth_client):
    response = auth_client.post("/marks", data=marks_data(score_1="abc"))
    assert b"Enter a number." in response.data


def test_delete_student_with_marks(auth_client):
    auth_client.post("/marks", data=marks_data())
    response = auth_client.post("/students/1/delete", follow_redirects=True)
    assert b"Student deleted." in response.data

    

# --------------------------------------------------------------------- Roles


def register(client, username, password="secret123"):
    """Register an account through the form."""
    return client.post(
        "/register",
        data={"username": username, "password": password, "confirm": password},
    )


def login(client, username, password="secret123"):
    """Log in through the form."""
    return client.post("/login", data={"username": username, "password": password})


@pytest.fixture
def teacher_client(client):
    """A client logged in as a teacher (the first account, 'boss', is the admin)."""
    register(client, "boss")
    register(client, "teacher1")
    login(client, "teacher1")
    return client


def test_first_user_is_admin(auth_client):
    response = auth_client.get("/users")
    assert response.status_code == 200
    assert b"Admin" in response.data


def test_teacher_cannot_open_users_page(teacher_client):
    response = teacher_client.get("/users", follow_redirects=True)
    assert b"do not have permission" in response.data


def test_teacher_cannot_add_student(teacher_client):
    response = teacher_client.post(
        "/students/add", data=student_data(), follow_redirects=True
    )
    assert b"do not have permission" in response.data
    assert b"Test Student" not in teacher_client.get("/students").data


def test_teacher_cannot_delete_student(teacher_client):
    response = teacher_client.post("/students/1/delete", follow_redirects=True)
    assert b"do not have permission" in response.data
    assert b"Abebe Kebede" in teacher_client.get("/students").data


def test_teacher_sees_students_without_admin_buttons(teacher_client):
    response = teacher_client.get("/students")
    assert response.status_code == 200
    assert b"Abebe Kebede" in response.data
    assert b"+ Add Student" not in response.data
    assert b"Delete" not in response.data


def test_teacher_can_take_attendance(teacher_client):
    response = teacher_client.post(
        "/attendance",
        data={
            "grade": "9",
            "section": "A",
            "date": "2026-10-20",
            "status_1": "Present",
        },
        follow_redirects=True,
    )
    assert b"Attendance saved." in response.data


def test_teacher_can_enter_marks(teacher_client):
    response = teacher_client.post("/marks", data=marks_data(), follow_redirects=True)
    assert b"Marks saved." in response.data


def test_admin_can_change_role(client):
    register(client, "boss")
    register(client, "second")
    login(client, "boss")
    response = client.post(
        "/users/2/role", data={"role": "admin"}, follow_redirects=True
    )
    assert b"Role updated." in response.data


def test_admin_cannot_change_own_role(auth_client):
    response = auth_client.post(
        "/users/1/role", data={"role": "teacher"}, follow_redirects=True
    )
    assert b"cannot change your own role" in response.data


def test_invalid_role_is_rejected(client):
    register(client, "boss")
    register(client, "second")
    login(client, "boss")
    response = client.post(
        "/users/2/role", data={"role": "superuser"}, follow_redirects=True
    )
    assert b"Invalid role." in response.data


def test_teacher_cannot_change_roles(teacher_client):
    response = teacher_client.post(
        "/users/1/role", data={"role": "teacher"}, follow_redirects=True
    )
    assert b"do not have permission" in response.data