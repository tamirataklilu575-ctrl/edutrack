"""EduTrack - Student Management System (Phase 6: Authentication)."""

import os
import re
import sqlite3
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
# Read the secret key from the environment in production.
# The fallback value is for local development only.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

DATABASE = Path(__file__).parent / "edutrack.db"

VALID_STATUSES = ("Active", "Inactive")
MIN_LENGTH = 2
MAX_LENGTH = 100

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,30}$")
MIN_PASSWORD_LENGTH = 6

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
    """Create tables and add sample students on first run."""
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO students (name, course, status) VALUES (?, ?, ?)",
                SEED_STUDENTS,
            )


def login_required(view):
    """Redirect to the login page if the user is not signed in."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


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


def validate_registration(username, password, confirm):
    """Return a dict of field errors for the registration form."""
    errors = {}

    if not username:
        errors["username"] = "Username is required."
    elif not USERNAME_PATTERN.match(username):
        errors["username"] = (
            "Username must be 3-30 characters: letters, numbers, or underscore."
        )

    if not password:
        errors["password"] = "Password is required."
    elif len(password) < MIN_PASSWORD_LENGTH:
        errors["password"] = (
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )

    if password and confirm != password:
        errors["confirm"] = "Passwords do not match."

    return errors


@app.errorhandler(404)
def page_not_found(error):
    """Render a friendly page when a URL or student does not exist."""
    return render_template("404.html"), 404


# ---------------------------------------------------------------- Auth routes


@app.route("/register", methods=["GET", "POST"])
def register():
    """Show the registration form (GET) and create a new user (POST)."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    errors = {}
    form = {"username": ""}

    if request.method == "POST":
        form["username"] = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        errors = validate_registration(form["username"], password, confirm)

        if not errors:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                        (form["username"], generate_password_hash(password)),
                    )
            except sqlite3.IntegrityError:
                errors["username"] = "This username is already taken."
            finally:
                conn.close()

            if not errors:
                flash("Account created! You can now log in.", "success")
                return redirect(url_for("login"))

    return render_template("register.html", form=form, errors=errors)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Show the login form (GET) and sign the user in (POST)."""
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    form = {"username": ""}

    if request.method == "POST":
        form["username"] = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        try:
            user = conn.execute(
                "SELECT * FROM users WHERE username = ?", (form["username"],)
            ).fetchone()
        finally:
            conn.close()

        if user is not None and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("dashboard"))

        # Same message for unknown user and wrong password (security best practice).
        flash("Invalid username or password.", "error")

    return render_template("login.html", form=form)


@app.route("/logout", methods=["POST"])
def logout():
    """Sign the user out."""
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ------------------------------------------------------------- Student routes


@app.route("/")
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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
    # Debug mode is only enabled when FLASK_DEBUG=1 is set (local development).
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")