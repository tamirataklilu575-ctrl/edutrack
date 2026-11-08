"""Tests for the platform owner: creating schools without public registration."""

import sqlite3

import app as app_module
from helpers import add_teacher, login, register

OWNER_LOGIN = "owner"
OWNER_PASSWORD = "ownerpass1"


def new_client():
    return app_module.app.test_client()


def rows(db_path, sql):
    check = sqlite3.connect(db_path)
    try:
        return check.execute(sql).fetchall()
    finally:
        check.close()


def create_school(owner, name="Green Valley High", login_name="green.admin", password="secret123"):
    return owner.post(
        "/owner",
        data={"school_name": name, "login": login_name, "password": password},
        follow_redirects=True,
    )


# ------------------------------------------------------- Owner bootstrap


def test_owner_is_created_from_the_environment(owner_client, db_path):
    owner = rows(db_path, "SELECT login, role, school_id FROM users")
    assert owner == [(OWNER_LOGIN, "owner", None)]


def test_no_owner_without_environment_settings(db_path):
    assert rows(db_path, "SELECT COUNT(*) FROM users") == [(0,)]


def test_owner_password_follows_the_environment(db_path, monkeypatch):
    monkeypatch.setattr(app_module, "OWNER_LOGIN", OWNER_LOGIN)
    monkeypatch.setattr(app_module, "OWNER_PASSWORD", OWNER_PASSWORD)
    app_module.init_db()

    monkeypatch.setattr(app_module, "OWNER_PASSWORD", "brandnewpass9")
    app_module.init_db()

    assert b"Invalid login or password." in login(new_client(), OWNER_LOGIN, OWNER_PASSWORD).data
    assert login(new_client(), OWNER_LOGIN, "brandnewpass9").status_code == 302
    assert rows(db_path, "SELECT COUNT(*) FROM users") == [(1,)]


def test_owner_creation_is_safe_to_repeat(db_path, monkeypatch):
    monkeypatch.setattr(app_module, "OWNER_LOGIN", OWNER_LOGIN)
    monkeypatch.setattr(app_module, "OWNER_PASSWORD", OWNER_PASSWORD)

    app_module.init_db()
    app_module.init_db()

    assert rows(db_path, "SELECT COUNT(*) FROM users") == [(1,)]


def test_owner_with_a_short_password_is_not_created(db_path, monkeypatch, capsys):
    monkeypatch.setattr(app_module, "OWNER_LOGIN", OWNER_LOGIN)
    monkeypatch.setattr(app_module, "OWNER_PASSWORD", "short")

    app_module.init_db()

    assert rows(db_path, "SELECT COUNT(*) FROM users") == [(0,)]
    assert "at least 8 characters" in capsys.readouterr().out


def test_owner_login_never_takes_over_a_school_account(db_path, monkeypatch, capsys):
    register(None, "boss@example.com")
    monkeypatch.setattr(app_module, "OWNER_LOGIN", "boss@example.com")
    monkeypatch.setattr(app_module, "OWNER_PASSWORD", OWNER_PASSWORD)

    app_module.init_db()

    assert rows(db_path, "SELECT role FROM users") == [("admin",)]
    assert "belongs to a school account" in capsys.readouterr().out
    assert b"Invalid login or password." in login(
        new_client(), "boss@example.com", OWNER_PASSWORD
    ).data


def test_owner_is_not_adopted_into_a_school_by_migration(db_path, monkeypatch):
    monkeypatch.setattr(app_module, "OWNER_LOGIN", OWNER_LOGIN)
    monkeypatch.setattr(app_module, "OWNER_PASSWORD", OWNER_PASSWORD)

    app_module.init_db()
    app_module.init_db()

    assert rows(db_path, "SELECT COUNT(*) FROM schools") == [(0,)]
    assert rows(db_path, "SELECT school_id FROM users") == [(None,)]


# ------------------------------------------------------------ Owner access


def test_owner_login_goes_to_the_schools_page(owner_client, db_path):
    owner = new_client()
    response = login(owner, OWNER_LOGIN, OWNER_PASSWORD)

    assert response.status_code == 302
    assert "/owner" in response.headers["Location"]
    assert b"Create a School" in owner.get("/owner").data


def test_owner_page_requires_login(client):
    response = client.get("/owner")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_and_teacher_cannot_open_the_owner_page(admin_and_teacher):
    admin, teacher = admin_and_teacher

    for who in (admin, teacher):
        response = who.get("/owner", follow_redirects=True)
        assert b"do not have permission" in response.data
        posted = who.post(
            "/owner",
            data={"school_name": "Sneaky", "login": "sneaky", "password": "secret123"},
            follow_redirects=True,
        )
        assert b"do not have permission" in posted.data


def test_owner_cannot_open_any_school_page(owner_client):
    for url in ("/", "/students", "/attendance", "/marks", "/class-report", "/users",
                "/export", "/students/export.csv", "/export/marks.csv",
                "/account", "/students/1/report"):
        response = owner_client.get(url)
        assert response.status_code == 302, url
        assert "/owner" in response.headers["Location"], url


def test_owner_cannot_change_school_data(owner_client):
    for url in ("/sample-data", "/students/1/delete"):
        response = owner_client.post(url)
        assert response.status_code == 302, url
        assert "/owner" in response.headers["Location"], url


def test_owner_has_no_school_menu(owner_client):
    page = owner_client.get("/owner").data
    assert b"Schools" in page
    assert b"Platform owner" in page
    assert b"Students" not in page.split(b"<main")[0]


# --------------------------------------------------------- Creating schools


def test_owner_creates_a_school_and_its_admin_can_log_in(owner_client, db_path):
    response = create_school(owner_client)
    assert b"School &#39;Green Valley High&#39; created." in response.data

    admin = new_client()
    assert login(admin, "green.admin", "secret123").status_code == 302
    page = admin.get("/").data
    assert b"Green Valley High" in page
    assert b"Your school is empty" in page
    assert rows(db_path, "SELECT role FROM users WHERE login = 'green.admin'") == [("admin",)]


def test_owner_sees_counts_but_no_student_names(owner_client, admin_and_teacher):
    page = owner_client.get("/owner").data

    assert b"Test School" in page
    assert b"Abebe Kebede" not in page
    assert b"teacher@example.com" not in page
    assert b"boss@example.com" in page  # the school's admin is listed


def test_owner_form_validates(owner_client):
    empty = create_school(owner_client, name="", login_name="", password="")
    assert b"School name is required." in empty.data
    assert b"Login is required." in empty.data
    assert b"Password is required." in empty.data

    bad = create_school(owner_client, login_name="not an email@", password="123")
    assert b"Enter a valid email address." in bad.data
    assert b"at least 6 characters" in bad.data


def test_owner_cannot_reuse_a_login_and_no_empty_school_is_left(owner_client, db_path):
    create_school(owner_client, name="First", login_name="same.login")
    before = rows(db_path, "SELECT COUNT(*) FROM schools")

    response = create_school(owner_client, name="Second", login_name="SAME.login")

    assert b"already in use" in response.data
    assert rows(db_path, "SELECT COUNT(*) FROM schools") == before


def test_two_schools_created_by_the_owner_are_separate(owner_client):
    create_school(owner_client, name="One", login_name="one.admin")
    create_school(owner_client, name="Two", login_name="two.admin")

    one, two = new_client(), new_client()
    login(one, "one.admin")
    login(two, "two.admin")
    one.post("/sample-data")

    assert b"Abebe Kebede" in one.get("/students").data
    assert b"Abebe Kebede" not in two.get("/students").data


def test_owner_resets_a_school_admins_password(owner_client, db_path):
    create_school(owner_client)
    admin_id = rows(db_path, "SELECT id FROM users WHERE login = 'green.admin'")[0][0]

    response = owner_client.post(
        f"/owner/users/{admin_id}/password",
        data={"password": "reset-pass-1"},
        follow_redirects=True,
    )

    assert b"Admin password updated." in response.data
    assert b"Invalid login or password." in login(new_client(), "green.admin", "secret123").data
    assert login(new_client(), "green.admin", "reset-pass-1").status_code == 302


def test_owner_reset_needs_a_valid_password(owner_client, db_path):
    create_school(owner_client)
    admin_id = rows(db_path, "SELECT id FROM users WHERE login = 'green.admin'")[0][0]

    response = owner_client.post(
        f"/owner/users/{admin_id}/password", data={"password": "1"}, follow_redirects=True
    )

    assert b"at least 6 characters" in response.data
    assert login(new_client(), "green.admin", "secret123").status_code == 302


def test_owner_cannot_reset_a_teachers_or_their_own_password(owner_client, admin_and_teacher, db_path):
    teacher_id = rows(db_path, "SELECT id FROM users WHERE login = 'teacher@example.com'")[0][0]
    owner_id = rows(db_path, "SELECT id FROM users WHERE role = 'owner'")[0][0]

    for target in (teacher_id, owner_id):
        response = owner_client.post(
            f"/owner/users/{target}/password", data={"password": "hacked999"}
        )
        assert response.status_code == 404

    assert login(new_client(), "teacher@example.com", "secret123").status_code == 302


def test_school_admins_cannot_reset_passwords_through_the_owner_route(admin_and_teacher, db_path):
    admin, teacher = admin_and_teacher
    admin_id = rows(db_path, "SELECT id FROM users WHERE login = 'boss@example.com'")[0][0]

    for who in (admin, teacher):
        response = who.post(
            f"/owner/users/{admin_id}/password",
            data={"password": "hacked999"},
            follow_redirects=True,
        )
        assert b"do not have permission" in response.data

    assert login(new_client(), "boss@example.com", "secret123").status_code == 302


def test_a_disabled_school_admin_is_flagged_for_the_owner(owner_client, admin_and_teacher, db_path):
    admin, _teacher = admin_and_teacher
    # A second admin is disabled by the first one.
    add_teacher(admin, "second@example.com")
    second_id = rows(db_path, "SELECT id FROM users WHERE login = 'second@example.com'")[0][0]
    admin.post(f"/users/{second_id}/role", data={"role": "admin"})
    admin.post(f"/users/{second_id}/active", data={"active": "0"})

    page = owner_client.get("/owner").data
    assert b"second@example.com" in page
    assert b"Disabled" in page
