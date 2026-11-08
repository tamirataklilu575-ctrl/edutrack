"""Tests for managing accounts: adding, resetting, disabling, and passwords."""

import sqlite3

import app as app_module
from helpers import add_teacher, login, marks_data


def new_client():
    return app_module.app.test_client()


def user_id(db_path, login_name):
    check = sqlite3.connect(db_path)
    try:
        return check.execute(
            "SELECT id FROM users WHERE login = ?", (login_name,)
        ).fetchone()[0]
    finally:
        check.close()


# ----------------------------------------------------------- Adding teachers


def test_admin_adds_a_teacher_with_an_email(auth_client):
    add_teacher(auth_client, "new@example.com")

    teacher = new_client()
    assert login(teacher, "new@example.com").status_code == 302
    assert b"Abebe Kebede" in teacher.get("/students").data


def test_admin_adds_a_teacher_with_a_username(auth_client):
    add_teacher(auth_client, "abebe.k")

    teacher = new_client()
    assert login(teacher, "abebe.k").status_code == 302
    assert b"Abebe Kebede" in teacher.get("/students").data


def test_new_logins_are_stored_in_lowercase(auth_client, db_path):
    add_teacher(auth_client, "  Teacher.One ")

    assert user_id(db_path, "teacher.one") > 0


def test_added_account_is_a_teacher(auth_client):
    add_teacher(auth_client, "new@example.com")

    page = auth_client.get("/users").data
    assert b"new@example.com" in page
    assert b"Make Admin" in page


def test_adding_rejects_a_duplicate_login_in_any_letter_case(auth_client):
    add_teacher(auth_client, "new@example.com")
    response = auth_client.post(
        "/users/add",
        data={"login": "NEW@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    assert b"already in use" in response.data


def test_adding_rejects_bad_logins_and_short_passwords(auth_client):
    bad_email = auth_client.post(
        "/users/add",
        data={"login": "no@dots", "password": "secret123"},
        follow_redirects=True,
    )
    assert b"Enter a valid email address." in bad_email.data

    bad_username = auth_client.post(
        "/users/add",
        data={"login": "ab", "password": "secret123"},
        follow_redirects=True,
    )
    assert b"A username must be 3-30 characters" in bad_username.data

    short = auth_client.post(
        "/users/add",
        data={"login": "ok.name", "password": "123"},
        follow_redirects=True,
    )
    assert b"at least 6 characters" in short.data


def test_teacher_cannot_add_users(teacher_client):
    response = teacher_client.post(
        "/users/add",
        data={"login": "x@example.com", "password": "secret123"},
        follow_redirects=True,
    )
    assert b"do not have permission" in response.data


# ------------------------------------------------------ Teachers and passwords


def test_teacher_account_page_has_no_password_form(teacher_client):
    response = teacher_client.get("/account")
    assert response.status_code == 200
    assert b"Change Password" not in response.data
    assert b"school administrator" in response.data


def test_teacher_cannot_change_their_password(teacher_client):
    response = teacher_client.post(
        "/account",
        data={
            "current_password": "secret123",
            "new_password": "hacked999",
            "confirm": "hacked999",
        },
        follow_redirects=True,
    )
    assert b"Passwords are changed by your school administrator" in response.data

    # The old password still works, the attempted one does not.
    assert login(new_client(), "teacher@example.com", "secret123").status_code == 302
    assert b"Invalid login or password." in login(
        new_client(), "teacher@example.com", "hacked999"
    ).data


def test_admin_can_change_their_own_password(auth_client):
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

    assert b"Invalid login or password." in login(
        new_client(), "boss@example.com", "secret123"
    ).data
    assert login(new_client(), "boss@example.com", "newsecret456").status_code == 302


def test_change_password_needs_the_current_password(auth_client):
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


def test_account_page_requires_login(client):
    response = client.get("/account")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# --------------------------------------------------- Admin resets a password


def test_admin_resets_a_teachers_password(admin_and_teacher, db_path):
    auth_client, teacher_client = admin_and_teacher
    teacher_id = user_id(db_path, "teacher@example.com")

    response = auth_client.post(
        f"/users/{teacher_id}/password",
        data={"password": "fresh12345"},
        follow_redirects=True,
    )
    assert b"Password updated for teacher@example.com." in response.data

    assert b"Invalid login or password." in login(
        new_client(), "teacher@example.com", "secret123"
    ).data
    assert login(new_client(), "teacher@example.com", "fresh12345").status_code == 302


def test_reset_rejects_a_short_password(admin_and_teacher, db_path):
    auth_client, teacher_client = admin_and_teacher
    teacher_id = user_id(db_path, "teacher@example.com")

    response = auth_client.post(
        f"/users/{teacher_id}/password",
        data={"password": "123"},
        follow_redirects=True,
    )
    assert b"at least 6 characters" in response.data
    assert login(new_client(), "teacher@example.com", "secret123").status_code == 302


def test_admin_cannot_reset_their_own_password_here(auth_client):
    response = auth_client.post(
        "/users/1/password", data={"password": "fresh12345"}, follow_redirects=True
    )
    assert b"Account page" in response.data


def test_teacher_cannot_reset_passwords(teacher_client, db_path):
    admin_id = user_id(db_path, "boss@example.com")

    response = teacher_client.post(
        f"/users/{admin_id}/password",
        data={"password": "hacked999"},
        follow_redirects=True,
    )
    assert b"do not have permission" in response.data
    assert login(new_client(), "boss@example.com", "secret123").status_code == 302


# --------------------------------------------------- Disabling and enabling


def test_disabled_teacher_cannot_log_in(admin_and_teacher, db_path):
    auth_client, teacher_client = admin_and_teacher
    teacher_id = user_id(db_path, "teacher@example.com")

    response = auth_client.post(
        f"/users/{teacher_id}/active", data={"active": "0"}, follow_redirects=True
    )
    assert b"Account disabled for teacher@example.com." in response.data

    attempt = login(new_client(), "teacher@example.com", "secret123")
    assert b"This account has been disabled" in attempt.data


def test_disabling_ends_an_open_session_immediately(admin_and_teacher, db_path):
    auth_client, teacher_client = admin_and_teacher
    assert teacher_client.get("/students").status_code == 200

    teacher_id = user_id(db_path, "teacher@example.com")
    auth_client.post(f"/users/{teacher_id}/active", data={"active": "0"})

    response = teacher_client.get("/students")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_disabled_message_is_hidden_from_wrong_passwords(admin_and_teacher, db_path):
    auth_client, teacher_client = admin_and_teacher
    teacher_id = user_id(db_path, "teacher@example.com")
    auth_client.post(f"/users/{teacher_id}/active", data={"active": "0"})

    attempt = login(new_client(), "teacher@example.com", "wrong-password")
    assert b"Invalid login or password." in attempt.data
    assert b"disabled" not in attempt.data


def test_enabling_restores_access(admin_and_teacher, db_path):
    auth_client, teacher_client = admin_and_teacher
    teacher_id = user_id(db_path, "teacher@example.com")
    auth_client.post(f"/users/{teacher_id}/active", data={"active": "0"})
    auth_client.post(f"/users/{teacher_id}/active", data={"active": "1"})

    assert login(new_client(), "teacher@example.com", "secret123").status_code == 302


def test_admin_cannot_disable_themselves(auth_client):
    response = auth_client.post(
        "/users/1/active", data={"active": "0"}, follow_redirects=True
    )
    assert b"cannot disable your own account" in response.data
    assert auth_client.get("/students").status_code == 200


def test_teacher_cannot_disable_anyone(teacher_client, db_path):
    admin_id = user_id(db_path, "boss@example.com")

    response = teacher_client.post(
        f"/users/{admin_id}/active", data={"active": "0"}, follow_redirects=True
    )
    assert b"do not have permission" in response.data
    assert login(new_client(), "boss@example.com", "secret123").status_code == 302


def test_users_page_shows_status(admin_and_teacher, db_path):
    auth_client, teacher_client = admin_and_teacher
    teacher_id = user_id(db_path, "teacher@example.com")
    auth_client.post(f"/users/{teacher_id}/active", data={"active": "0"})

    page = auth_client.get("/users").data
    assert b"Disabled" in page
    assert b"Enable" in page


# ------------------------------------------------------ Other schools' accounts


def test_cannot_manage_accounts_of_another_school(two_schools, db_path):
    alice, bob = two_schools
    bob_id = user_id(db_path, "bob@example.com")
    alice_id = user_id(db_path, "alice@example.com")

    for url, data in (
        (f"/users/{bob_id}/password", {"password": "hacked999"}),
        (f"/users/{bob_id}/active", {"active": "0"}),
        (f"/users/{bob_id}/role", {"role": "teacher"}),
    ):
        assert alice.post(url, data=data).status_code == 404

    # Bob can still log in with his own password and is still an admin.
    assert login(new_client(), "bob@example.com", "secret123").status_code == 302
    assert bob.get("/users").status_code == 200
    assert alice_id != bob_id


def test_teachers_work_still_belongs_to_their_school(admin_and_teacher):
    auth_client, teacher_client = admin_and_teacher
    auth_client.post("/marks", data=marks_data(score_1="70"))
    assert b"70" in teacher_client.get("/students/1/report?term=Semester+1").data
