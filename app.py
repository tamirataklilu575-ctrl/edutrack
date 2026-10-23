"""EduTrack - Student Management System (Phase 4B: Flash messages and 404)."""

import sqlite3
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

app = Flask(__name__)
# Required for flash messages. Replace with a secret environment variable in production.
app.secret_key = "dev-only-change-me"

DATABASE = Path(__file__).parent / "edutrack.db"

VALID_STATUSES = ("Active", "Inactive")
MIN_LENGTH = 2
MAX_LENGTH = 100

SEED_STUDENTS = [
    ("Abebe Kebede", "Computer Science", "Active"),
    ("Selam Tadesse", "Information Systems", "Active"),
    ("Dawit Alemu", "Software Engineering", "Inactive"),
    ("Hana Girma", "Computer Science", "Active"),
]


def get_db():
    """Open a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the students table and add sample data on first run."""
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                course TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active'
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO students (name, course, status) VALUES (?, ?, ?)",
                SEED_STUDENTS,
            )


def validate_student(name, course, status):
    """Return a dict of field errors. An empty dict means the data is valid."""
    errors = {}

    if not name:
        errors["name"] = "Full name is required."
    elif len(name) < MIN_LENGTH:
        errors["name"] = f"Full name must be at least {MIN_LENGTH} characters."
    elif len(name) > MAX_LENGTH:
        errors["name"] = f"Full name must be at most {MAX_LENGTH} characters."

    if not course:
        errors["course"] = "Course is required."
    elif len(course) < MIN_LENGTH:
        errors["course"] = f"Course must be at least {MIN_LENGTH} characters."
    elif len(course) > MAX_LENGTH:
        errors["course"] = f"Course must be at most {MAX_LENGTH} characters."

    if status not in VALID_STATUSES:
        errors["status"] = "Please choose a valid status."

    return errors


@app.errorhandler(404)
def page_not_found(error):
    """Render a friendly page when a URL or student does not exist."""
    return render_template("404.html"), 404


@app.route("/")
def dashboard():
    """Render the main dashboard with summary statistics."""
    conn = get_db()
    try:
        all_students = conn.execute(
            "SELECT * FROM students ORDER BY id DESC"
        ).fetchall()
    finally:
        conn.close()

    total = len(all_students)
    active = sum(1 for s in all_students if s["status"] == "Active")
    courses = len({s["course"] for s in all_students})

    stats = {
        "total": total,
        "active": active,
        "inactive": total - active,
        "courses": courses,
    }
    return render_template(
        "dashboard.html", stats=stats, recent_students=all_students[:5]
    )


@app.route("/students")
def student_list():
    """Render the list of students, optionally filtered by a search query."""
    query = request.args.get("q", "").strip()

    conn = get_db()
    try:
        if query:
            pattern = f"%{query}%"
            results = conn.execute(
                "SELECT * FROM students WHERE name LIKE ? OR course LIKE ? ORDER BY id",
                (pattern, pattern),
            ).fetchall()
        else:
            results = conn.execute("SELECT * FROM students ORDER BY id").fetchall()
    finally:
        conn.close()

    return render_template("students.html", students=results, query=query)


@app.route("/students/add", methods=["GET", "POST"])
def add_student():
    """Show the add-student form (GET) and save a new student (POST)."""
    errors = {}
    form = {"name": "", "course": "", "status": "Active"}

    if request.method == "POST":
        form = {
            "name": request.form.get("name", "").strip(),
            "course": request.form.get("course", "").strip(),
            "status": request.form.get("status", ""),
        }
        errors = validate_student(form["name"], form["course"], form["status"])

        if not errors:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO students (name, course, status) VALUES (?, ?, ?)",
                        (form["name"], form["course"], form["status"]),
                    )
            finally:
                conn.close()
            flash("Student added successfully!", "success")
            return redirect(url_for("student_list"))

    return render_template("add_student.html", student=None, form=form, errors=errors)


@app.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
def edit_student(student_id):
    """Show the edit form (GET) and update the student (POST)."""
    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        if student is None:
            abort(404)

        errors = {}
        form = {
            "name": student["name"],
            "course": student["course"],
            "status": student["status"],
        }

        if request.method == "POST":
            form = {
                "name": request.form.get("name", "").strip(),
                "course": request.form.get("course", "").strip(),
                "status": request.form.get("status", ""),
            }
            errors = validate_student(form["name"], form["course"], form["status"])

            if not errors:
                with conn:
                    conn.execute(
                        "UPDATE students SET name = ?, course = ?, status = ? WHERE id = ?",
                        (form["name"], form["course"], form["status"], student_id),
                    )
                flash("Student updated successfully!", "success")
                return redirect(url_for("student_list"))
    finally:
        conn.close()

    return render_template("add_student.html", student=student, form=form, errors=errors)


@app.route("/students/<int:student_id>/delete", methods=["POST"])
def delete_student(student_id):
    """Delete the student with the given ID."""
    conn = get_db()
    try:
        with conn:
            cursor = conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
        if cursor.rowcount == 0:
            abort(404)
    finally:
        conn.close()

    flash("Student deleted.", "success")
    return redirect(url_for("student_list"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)