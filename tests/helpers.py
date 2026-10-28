"""Small helper functions shared by the test files."""

VALID_STUDENT = {
    "name": "Test Student",
    "grade": "9",
    "section": "A",
    "gender": "Male",
    "parent_phone": "",
    "status": "Active",
}


def register(client, email, password="secret123", school="Test School"):
    """Register a new school and its admin account through the form."""
    return client.post(
        "/register",
        data={
            "school_name": school,
            "email": email,
            "password": password,
            "confirm": password,
        },
    )


def login(client, email, password="secret123"):
    """Log in through the form."""
    return client.post("/login", data={"email": email, "password": password})


def load_sample(client):
    """Fill the signed-in admin's empty school with the sample students."""
    return client.post("/sample-data")


def add_teacher(admin_client, email, password="secret123"):
    """Create a teacher account from the signed-in admin's Users page."""
    return admin_client.post("/users/add", data={"email": email, "password": password})


def student_data(**overrides):
    """Return valid student form data with optional overrides."""
    return {**VALID_STUDENT, **overrides}


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


def attendance_data(status="Present", day="2026-10-20", student_id=1):
    """Return attendance form data for Grade 9 Section A."""
    return {
        "grade": "9",
        "section": "A",
        "date": day,
        f"status_{student_id}": status,
    }
