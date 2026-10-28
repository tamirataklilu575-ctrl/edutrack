"""Tests that one school can never see or change another school's data.

Alice's students have IDs 1-5 and Bob's have IDs 6-10. Both schools have
students with the same names, so every check below looks at IDs and at the
one student added only to Alice's school ("Alpha Only").
"""

from helpers import attendance_data, marks_data, student_data

ALICE_ONLY = "Alpha Only"


def add_alpha(alice):
    """Add a student that exists only in Alice's school (ID 6 becomes Bob's 7)."""
    alice.post("/students/add", data=student_data(name=ALICE_ONLY))


def alpha_id(alice):
    """Find the ID of Alice's extra student by reading her CSV export."""
    text = alice.get("/students/export.csv").data.decode("utf-8-sig")
    for line in text.splitlines():
        if ALICE_ONLY in line:
            return int(line.split(",")[0])
    raise AssertionError("Alpha Only was not found in Alice's export")


# ------------------------------------------------------------- Seeing data


def test_each_school_has_its_own_students(two_schools):
    alice, bob = two_schools
    add_alpha(alice)

    assert ALICE_ONLY.encode() in alice.get("/students").data
    assert ALICE_ONLY.encode() not in bob.get("/students").data


def test_dashboard_counts_only_own_students(two_schools):
    alice, bob = two_schools
    add_alpha(alice)

    assert b"<span class=\"card-value\">6</span>" in alice.get("/").data
    assert b"<span class=\"card-value\">5</span>" in bob.get("/").data


def test_search_does_not_cross_schools(two_schools):
    alice, bob = two_schools
    add_alpha(alice)

    assert ALICE_ONLY.encode() not in bob.get("/students?q=alpha").data


def test_class_report_does_not_cross_schools(two_schools):
    alice, bob = two_schools
    add_alpha(alice)

    response = bob.get("/class-report?grade=9&section=A")
    assert ALICE_ONLY.encode() not in response.data
    assert b"Abebe Kebede" in response.data  # Bob's own copy of that name


def test_users_page_lists_only_own_school(two_schools):
    alice, bob = two_schools

    assert b"alice@example.com" in alice.get("/users").data
    assert b"alice@example.com" not in bob.get("/users").data
    assert b"bob@example.com" in bob.get("/users").data


def test_school_name_shown_is_your_own(two_schools):
    alice, bob = two_schools

    assert b"Alice School" in alice.get("/").data
    assert b"Alice School" not in bob.get("/").data


# ---------------------------------------------------- Reaching data by URL


def test_cannot_open_another_schools_student_edit_page(two_schools):
    alice, bob = two_schools

    assert bob.get("/students/1/edit").status_code == 404
    assert alice.get("/students/6/edit").status_code == 404


def test_cannot_change_another_schools_student(two_schools):
    alice, bob = two_schools

    response = bob.post(
        "/students/1/edit", data=student_data(name="Hacked Name")
    )

    assert response.status_code == 404
    assert b"Hacked Name" not in alice.get("/students").data
    assert b"Abebe Kebede" in alice.get("/students").data


def test_cannot_delete_another_schools_student(two_schools):
    alice, bob = two_schools

    response = bob.post("/students/1/delete")

    assert response.status_code == 404
    assert b"Abebe Kebede" in alice.get("/students").data


def test_cannot_view_another_schools_report_card(two_schools):
    alice, bob = two_schools
    add_alpha(alice)

    assert bob.get(f"/students/{alpha_id(alice)}/report").status_code == 404


# ------------------------------------------------- Writing into other data


def test_attendance_for_another_schools_student_is_ignored(two_schools):
    alice, bob = two_schools

    # Bob sends a status for Alice's student 1 while viewing his own class.
    bob.post("/attendance", data=attendance_data("Absent", student_id=1))

    text = alice.get("/export/attendance.csv").data.decode("utf-8-sig")
    assert "Abebe Kebede" not in text.split("\r\n", 1)[1]


def test_marks_for_another_schools_student_are_ignored(two_schools):
    alice, bob = two_schools

    bob.post("/marks", data=marks_data(score_1="99"))

    text = alice.get("/export/marks.csv").data.decode("utf-8-sig")
    assert "99" not in text


def test_attendance_and_marks_pages_show_only_own_scores(two_schools):
    alice, bob = two_schools
    # Alice enters a mark and attendance for her student 1.
    alice.post("/marks", data=marks_data(score_1="77"))
    alice.post("/attendance", data=attendance_data("Absent"))

    # Bob (whose Grade 9 A student is ID 6) sees none of it.
    marks_page = bob.get("/marks?grade=9&section=A&subject=Mathematics&term=Semester+1")
    assert b"Marked: 0" in marks_page.data
    attendance_page = bob.get("/attendance?grade=9&section=A&date=2026-10-20")
    assert b"Absent: 0" in attendance_page.data


def test_report_rank_ignores_other_schools(two_schools):
    alice, bob = two_schools
    # Bob's student 6 scores far higher than Alice's student 1.
    alice.post("/marks", data=marks_data(score_1="60"))
    bob.post("/marks", data=marks_data(score_6="99"))

    response = alice.get("/students/1/report?term=Semester+1")
    assert b"1 of 1" in response.data


# ------------------------------------------------------------- Exports


def test_csv_exports_contain_only_own_school(two_schools):
    alice, bob = two_schools
    add_alpha(alice)
    alice.post("/marks", data=marks_data(score_1="88"))
    alice.post("/attendance", data=attendance_data("Late"))

    for url in (
        "/students/export.csv",
        "/export/marks.csv",
        "/export/attendance.csv",
        "/class-report/export.csv?grade=9&section=A&term=Semester+1",
    ):
        text = bob.get(url).data.decode("utf-8-sig")
        assert ALICE_ONLY not in text
        assert "88" not in text.replace("88.0", "")  # no copy of Alice's mark


def test_students_export_has_only_own_rows(two_schools):
    alice, bob = two_schools

    alice_ids = {line.split(",")[0] for line in
                 alice.get("/students/export.csv").data.decode("utf-8-sig").splitlines()[1:]}
    bob_ids = {line.split(",")[0] for line in
               bob.get("/students/export.csv").data.decode("utf-8-sig").splitlines()[1:]}

    assert alice_ids == {"1", "2", "3", "4", "5"}
    assert bob_ids == {"6", "7", "8", "9", "10"}


# ----------------------------------------------------------- Users and roles


def test_cannot_change_a_role_in_another_school(two_schools):
    alice, bob = two_schools

    # Bob is user 2. Alice tries to make him a teacher, and he tries the same on her.
    assert alice.post("/users/2/role", data={"role": "teacher"}).status_code == 404
    assert bob.post("/users/1/role", data={"role": "teacher"}).status_code == 404


def test_teacher_added_by_one_school_belongs_to_that_school(two_schools):
    alice, bob = two_schools

    alice.post("/users/add", data={"email": "t@example.com", "password": "secret123"})

    assert b"t@example.com" in alice.get("/users").data
    assert b"t@example.com" not in bob.get("/users").data


def test_sample_data_only_goes_into_own_school(two_schools):
    alice, bob = two_schools
    alice.post("/students/1/delete")  # Alice still has 4 students, so no sample data.

    response = alice.post("/sample-data", follow_redirects=True)

    assert b"only be added to an empty school" in response.data
    assert b"<span class=\"card-value\">5</span>" in bob.get("/").data
