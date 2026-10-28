"""EduTrack - High School Management System."""

import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from csv_tools import build_csv
from pagination import paginate

app = Flask(__name__)
# Read the secret key from the environment in production.
# The fallback value is for local development only.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

# Keep users signed in for 7 days, even after the browser is closed.
app.permanent_session_lifetime = timedelta(days=7)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Local development uses a SQLite file. When DATABASE_URL is set (for example
# on Render), the app uses that PostgreSQL database instead.
DATABASE = Path(__file__).parent / "edutrack.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Ethiopia is UTC+3 all year (no daylight saving time). Servers usually run on
# UTC, so "today" is calculated with this offset instead.
SCHOOL_UTC_OFFSET_HOURS = 3

# Allowed values for student fields.
GRADES = (9, 10, 11, 12)
SECTIONS = ("A", "B", "C", "D")
GENDERS = ("Male", "Female")
VALID_STATUSES = ("Active", "Inactive")
ATTENDANCE_STATUSES = ("Present", "Absent", "Late")
SUBJECTS = (
    "Amharic",
    "English",
    "Mathematics",
    "Physics",
    "Chemistry",
    "Biology",
    "Civics",
)
TERMS = ("Semester 1", "Semester 2")
ROLES = ("admin", "teacher")
PASS_MARK = 50

# How many students appear on one page of the student list.
STUDENTS_PER_PAGE = 20

MIN_LENGTH = 2
MAX_LENGTH = 100
PHONE_PATTERN = re.compile(r"^\+?[0-9 ]{9,15}$")

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EMAIL_LENGTH = 254
MIN_PASSWORD_LENGTH = 6

# Name given to the school that adopts data created before schools existed.
LEGACY_SCHOOL_NAME = "My School"

# (name, grade, section, gender, parent_phone, status)
SAMPLE_STUDENTS = [
    ("Abebe Kebede", 9, "A", "Male", "+251911000001", "Active"),
    ("Meron Bekele", 9, "B", "Female", "+251911000002", "Active"),
    ("Selam Tadesse", 10, "B", "Female", "+251911000003", "Active"),
    ("Dawit Alemu", 11, "A", "Male", "", "Inactive"),
    ("Hana Girma", 12, "C", "Female", "+251911000005", "Active"),
]


# ------------------------------------------------------------------ Database


def using_postgres():
    """Return True when a PostgreSQL connection string is configured."""
    return bool(DATABASE_URL)


class Database:
    """A thin wrapper so the same code works with SQLite and PostgreSQL.

    - Queries are written with ``?`` placeholders; they are converted for
      PostgreSQL automatically.
    - ``with db:`` commits on success and rolls back on error, but keeps the
      connection open. Call ``close()`` when you are finished.
    """

    def __init__(self, raw, postgres):
        self.raw = raw
        self.postgres = postgres

    def convert_sql(self, sql):
        """Convert ``?`` placeholders to ``%s`` when talking to PostgreSQL."""
        return sql.replace("?", "%s") if self.postgres else sql

    def execute(self, sql, params=()):
        cursor = self.raw.cursor()
        cursor.execute(self.convert_sql(sql), params)
        return cursor

    def executemany(self, sql, params_list):
        cursor = self.raw.cursor()
        cursor.executemany(self.convert_sql(sql), params_list)
        return cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.raw.commit()
        else:
            self.raw.rollback()
        return False

    def close(self):
        self.raw.close()


def get_db():
    """Open a connection to PostgreSQL (if configured) or to the SQLite file."""
    if using_postgres():
        # Imported here so local development does not need psycopg installed.
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            connect_timeout=15,
            prepare_threshold=None,
        )
        return Database(raw, postgres=True)

    raw = sqlite3.connect(DATABASE)
    raw.row_factory = sqlite3.Row
    # SQLite does not enforce foreign keys unless this is switched on.
    raw.execute("PRAGMA foreign_keys = ON")
    return Database(raw, postgres=False)


def integrity_errors():
    """Return the exception types raised when a UNIQUE rule is broken."""
    if using_postgres():
        import psycopg

        return (psycopg.IntegrityError,)
    return (sqlite3.IntegrityError,)


def column_names(conn, table):
    """Return the column names of a table (works on both databases)."""
    if conn.postgres:
        rows = conn.execute(
            "SELECT column_name AS name FROM information_schema.columns "
            "WHERE table_name = ? AND table_schema = current_schema()",
            (table,),
        ).fetchall()
    else:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [row["name"] for row in rows]


def create_school(conn, name):
    """Insert a school and return its new ID."""
    row = conn.execute(
        "INSERT INTO schools (name) VALUES (?) RETURNING id", (name,)
    ).fetchone()
    return row["id"]


def insert_sample_students(conn, school_id):
    """Add the sample students to one school."""
    conn.executemany(
        "INSERT INTO students "
        "(school_id, name, grade, section, gender, parent_phone, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(school_id, *student) for student in SAMPLE_STUDENTS],
    )


def init_db():
    """Create tables and migrate older databases to the school-based layout."""
    conn = get_db()
    try:
        with conn:
            if not conn.postgres:
                # Development-stage migration: replace the old university table.
                columns = column_names(conn, "students")
                if columns and "grade" not in columns:
                    conn.execute("DROP TABLE students")

                # Development-stage migration: accounts now sign in with an
                # email, so an older username-based table is replaced.
                user_columns = column_names(conn, "users")
                if user_columns and "email" not in user_columns:
                    conn.execute("DROP TABLE users")

            # Primary-key syntax differs between the two databases.
            pk = "SERIAL PRIMARY KEY" if conn.postgres else (
                "INTEGER PRIMARY KEY AUTOINCREMENT"
            )

            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS schools (
                    id {pk},
                    name TEXT NOT NULL
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS users (
                    id {pk},
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'teacher',
                    school_id INTEGER REFERENCES schools (id)
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS students (
                    id {pk},
                    school_id INTEGER REFERENCES schools (id),
                    name TEXT NOT NULL,
                    grade INTEGER NOT NULL,
                    section TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    parent_phone TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Active'
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS attendance (
                    id {pk},
                    student_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    UNIQUE (student_id, date),
                    FOREIGN KEY (student_id) REFERENCES students (id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS marks (
                    id {pk},
                    student_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    term TEXT NOT NULL,
                    score DOUBLE PRECISION NOT NULL,
                    UNIQUE (student_id, subject, term),
                    FOREIGN KEY (student_id) REFERENCES students (id)
                        ON DELETE CASCADE
                )
                """
            )

            # Migration: databases created before schools existed get a
            # school_id column on users and students.
            for table in ("users", "students"):
                if "school_id" not in column_names(conn, table):
                    conn.execute(
                        f"ALTER TABLE {table} "
                        "ADD COLUMN school_id INTEGER REFERENCES schools (id)"
                    )

            # Everything that already exists moves into one school, so no
            # account or student is lost. A fresh database creates nothing.
            orphans = conn.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM users WHERE school_id IS NULL) AS users, "
                "(SELECT COUNT(*) FROM students WHERE school_id IS NULL) AS students"
            ).fetchone()
            if orphans["users"] or orphans["students"]:
                legacy_id = create_school(conn, LEGACY_SCHOOL_NAME)
                conn.execute(
                    "UPDATE users SET school_id = ? WHERE school_id IS NULL",
                    (legacy_id,),
                )
                conn.execute(
                    "UPDATE students SET school_id = ? WHERE school_id IS NULL",
                    (legacy_id,),
                )
    finally:
        conn.close()


def today_local():
    """Return today's date in the school's time zone (Ethiopia, UTC+3)."""
    school_zone = timezone(timedelta(hours=SCHOOL_UTC_OFFSET_HOURS))
    return datetime.now(school_zone).date()


@app.before_request
def load_current_user():
    """Load the signed-in user, their role, and their school for this request."""
    g.user = None
    if request.endpoint == "static":
        return

    user_id = session.get("user_id")
    if user_id is None:
        return

    conn = get_db()
    try:
        g.user = conn.execute(
            "SELECT u.id, u.email, u.role, u.school_id, s.name AS school_name "
            "FROM users u LEFT JOIN schools s ON s.id = u.school_id "
            "WHERE u.id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    # No account, or an account without a school, is treated as signed out.
    if g.user is None or g.user["school_id"] is None:
        g.user = None
        session.clear()


@app.context_processor
def inject_options():
    """Make allowed field values and the current user available in templates."""
    return {
        "current_user": getattr(g, "user", None),
        "GRADES": GRADES,
        "SECTIONS": SECTIONS,
        "GENDERS": GENDERS,
        "STATUSES": VALID_STATUSES,
        "ATTENDANCE_STATUSES": ATTENDANCE_STATUSES,
        "SUBJECTS": SUBJECTS,
        "TERMS": TERMS,
    }


def login_required(view):
    """Redirect to the login page if the user is not signed in."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    """Allow only signed-in admins; send everyone else away with a message."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        if g.user["role"] != "admin":
            flash("You do not have permission to do that.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped_view


def school_id():
    """Return the school of the signed-in user.

    Every query on students, users, and everything attached to a student must
    be limited to this value, so one school can never see another's data.
    """
    return g.user["school_id"]


def read_student_form():
    """Read and clean the student form fields from the request."""
    return {
        "name": request.form.get("name", "").strip(),
        "grade": request.form.get("grade", "").strip(),
        "section": request.form.get("section", "").strip(),
        "gender": request.form.get("gender", "").strip(),
        "parent_phone": request.form.get("parent_phone", "").strip(),
        "status": request.form.get("status", "").strip(),
    }


def validate_student(form):
    """Return a dict of field errors. An empty dict means the data is valid."""
    errors = {}
    name = form["name"]

    if not name:
        errors["name"] = "Full name is required."
    elif len(name) < MIN_LENGTH:
        errors["name"] = f"Full name must be at least {MIN_LENGTH} characters."
    elif len(name) > MAX_LENGTH:
        errors["name"] = f"Full name must be at most {MAX_LENGTH} characters."

    if form["grade"] not in [str(g) for g in GRADES]:
        errors["grade"] = "Please choose a grade between 9 and 12."

    if form["section"] not in SECTIONS:
        errors["section"] = "Please choose a valid section."

    if form["gender"] not in GENDERS:
        errors["gender"] = "Please choose a gender."

    phone = form["parent_phone"]
    if phone and not PHONE_PATTERN.match(phone):
        errors["parent_phone"] = "Enter a valid phone number (9-15 digits)."

    if form["status"] not in VALID_STATUSES:
        errors["status"] = "Please choose a valid status."

    return errors


def validate_registration(email, password, confirm):
    """Return a dict of field errors for the registration form."""
    errors = {}

    if not email:
        errors["email"] = "Email is required."
    elif len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email):
        errors["email"] = "Enter a valid email address."

    if not password:
        errors["password"] = "Password is required."
    elif len(password) < MIN_PASSWORD_LENGTH:
        errors["password"] = (
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )

    if password and confirm != password:
        errors["confirm"] = "Passwords do not match."

    return errors


def validate_school_name(name):
    """Return an error message for a bad school name, or None if it is fine."""
    if not name:
        return "School name is required."
    if len(name) < MIN_LENGTH:
        return f"School name must be at least {MIN_LENGTH} characters."
    if len(name) > MAX_LENGTH:
        return f"School name must be at most {MAX_LENGTH} characters."
    return None


def average_remark(average):
    """Turn an average score into a short written remark."""
    if average >= 90:
        return "Excellent"
    if average >= 75:
        return "Very Good"
    if average >= 60:
        return "Good"
    if average >= PASS_MARK:
        return "Satisfactory"
    return "Needs Improvement"


def build_today_attendance(active_students, attendance_rows):
    """Summarise one day's attendance for the dashboard.

    ``active_students`` are the students expected in school. A student with no
    record that day counts as "Pending" (not recorded yet), never as absent.
    Late counts as attended, matching the report card.
    """
    status_by_student = {row["student_id"]: row["status"] for row in attendance_rows}

    counts = {"Present": 0, "Absent": 0, "Late": 0, "Pending": 0}
    classes = {}

    for student in active_students:
        status = status_by_student.get(student["id"])
        if status not in ATTENDANCE_STATUSES:
            status = "Pending"
        counts[status] += 1

        key = (student["grade"], student["section"])
        class_row = classes.setdefault(
            key,
            {
                "grade": key[0],
                "section": key[1],
                "total": 0,
                "Present": 0,
                "Absent": 0,
                "Late": 0,
                "Pending": 0,
            },
        )
        class_row["total"] += 1
        class_row[status] += 1

    total = len(active_students)
    recorded = total - counts["Pending"]

    if recorded:
        attended = counts["Present"] + counts["Late"]
        rate_text = f"{round(attended * 100 / recorded)}%"
    else:
        rate_text = "—"

    return {
        "counts": counts,
        "total": total,
        "recorded": recorded,
        "rate_text": rate_text,
        "classes": [classes[key] for key in sorted(classes)],
    }


def build_class_report(class_students, mark_rows):
    """Compute per-student results, per-subject statistics, and class totals.

    Returns a tuple: (rows, subject_stats, summary).
    Rows are sorted by rank; students with no marks come last.
    """
    scores_by_student = {}
    for row in mark_rows:
        student_scores = scores_by_student.setdefault(row["student_id"], {})
        student_scores[row["subject"]] = row["score"]

    # One row per student, with a score cell for every subject.
    rows = []
    for student in class_students:
        scores = scores_by_student.get(student["id"], {})

        cells = []
        for subject in SUBJECTS:
            score = scores.get(subject)
            cells.append(
                {
                    "text": "—" if score is None else f"{score:g}",
                    "failed": score is not None and score < PASS_MARK,
                }
            )

        row = {
            "student": student,
            "cells": cells,
            "average": None,
            "rank": None,
            "rank_text": "—",
            "total_text": "—",
            "average_text": "—",
            "remark": "",
            "result": "",
        }

        if scores:
            total = sum(scores.values())
            average = total / len(scores)
            row["average"] = average
            row["total_text"] = f"{total:g}"
            row["average_text"] = f"{average:.1f}"
            row["remark"] = average_remark(average)
            row["result"] = "Pass" if average >= PASS_MARK else "Fail"

        rows.append(row)

    # Rank by average. Equal averages share the same rank (1, 1, 3, ...).
    ranked = [row for row in rows if row["average"] is not None]
    for row in ranked:
        row["rank"] = 1 + sum(
            1 for other in ranked if other["average"] > row["average"]
        )
        row["rank_text"] = str(row["rank"])

    ranked.sort(key=lambda row: (row["rank"], row["student"]["name"]))
    unranked = [row for row in rows if row["average"] is None]
    rows = ranked + unranked

    # Statistics for each subject across the whole class.
    subject_stats = []
    for subject in SUBJECTS:
        values = [
            scores_by_student.get(student["id"], {}).get(subject)
            for student in class_students
        ]
        values = [value for value in values if value is not None]

        if values:
            passed = sum(1 for value in values if value >= PASS_MARK)
            subject_stats.append(
                {
                    "subject": subject,
                    "average": f"{sum(values) / len(values):.1f}",
                    "highest": f"{max(values):g}",
                    "lowest": f"{min(values):g}",
                    "pass_rate": f"{round(passed * 100 / len(values))}%",
                }
            )
        else:
            subject_stats.append(
                {
                    "subject": subject,
                    "average": "—",
                    "highest": "—",
                    "lowest": "—",
                    "pass_rate": "—",
                }
            )

    # Class-wide summary.
    if ranked:
        averages = [row["average"] for row in ranked]
        passed_students = sum(1 for row in ranked if row["result"] == "Pass")
        summary = {
            "students": len(class_students),
            "with_marks": len(ranked),
            "class_average": f"{sum(averages) / len(averages):.1f}",
            "pass_rate": f"{round(passed_students * 100 / len(ranked))}%",
            "top": ", ".join(
                row["student"]["name"] for row in ranked if row["rank"] == 1
            ),
        }
    else:
        summary = {
            "students": len(class_students),
            "with_marks": 0,
            "class_average": "—",
            "pass_rate": "—",
            "top": "—",
        }

    return rows, subject_stats, summary


@app.errorhandler(404)
def page_not_found(error):
    """Render a friendly page when a URL or student does not exist."""
    return render_template("404.html"), 404


# ---------------------------------------------------------------- Auth routes


@app.route("/register", methods=["GET", "POST"])
def register():
    """Create a new school together with its first (admin) account."""
    if g.user is not None:
        return redirect(url_for("dashboard"))

    errors = {}
    form = {"email": "", "school_name": ""}

    if request.method == "POST":
        # Emails are stored in lowercase so they match regardless of typing.
        form["email"] = request.form.get("email", "").strip().lower()
        form["school_name"] = request.form.get("school_name", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        errors = validate_registration(form["email"], password, confirm)
        school_error = validate_school_name(form["school_name"])
        if school_error:
            errors["school_name"] = school_error

        if not errors:
            conn = get_db()
            try:
                # School and admin are created together. If the email is already
                # taken, the whole transaction is rolled back, so no empty school
                # is left behind.
                with conn:
                    new_school_id = create_school(conn, form["school_name"])
                    conn.execute(
                        "INSERT INTO users (email, password_hash, role, school_id) "
                        "VALUES (?, ?, 'admin', ?)",
                        (form["email"], generate_password_hash(password), new_school_id),
                    )
            except integrity_errors():
                errors["email"] = "This email is already registered."
            finally:
                conn.close()

            if not errors:
                flash("School created! You can now log in.", "success")
                return redirect(url_for("login"))

    return render_template("register.html", form=form, errors=errors)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Show the login form (GET) and sign the user in (POST)."""
    if g.user is not None:
        return redirect(url_for("dashboard"))

    form = {"email": ""}

    if request.method == "POST":
        form["email"] = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        try:
            user = conn.execute(
                "SELECT * FROM users WHERE email = ?", (form["email"],)
            ).fetchone()
        finally:
            conn.close()

        if user is not None and check_password_hash(user["password_hash"], password):
            session.clear()
            # A permanent session survives closing the browser (up to 7 days).
            session.permanent = True
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['email']}!", "success")
            return redirect(url_for("dashboard"))

        # Same message for unknown email and wrong password (security best practice).
        flash("Invalid email or password.", "error")

    return render_template("login.html", form=form)


@app.route("/logout", methods=["POST"])
def logout():
    """Sign the user out."""
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    """Let the signed-in user change their own password."""
    errors = {}

    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm", "")

        conn = get_db()
        try:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (g.user["id"],)
            ).fetchone()

            if row is None or not check_password_hash(row["password_hash"], current):
                errors["current_password"] = "Current password is incorrect."
            if len(new) < MIN_PASSWORD_LENGTH:
                errors["new_password"] = (
                    f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
                )
            elif confirm != new:
                errors["confirm"] = "Passwords do not match."

            if not errors:
                with conn:
                    conn.execute(
                        "UPDATE users SET password_hash = ? WHERE id = ?",
                        (generate_password_hash(new), g.user["id"]),
                    )
                flash("Password changed.", "success")
                return redirect(url_for("account"))
        finally:
            conn.close()

    return render_template("account.html", errors=errors)


# ---------------------------------------------------------------- User routes


@app.route("/users")
@admin_required
def user_list():
    """List the accounts of this school so an admin can manage them."""
    conn = get_db()
    try:
        users = conn.execute(
            "SELECT id, email, role FROM users WHERE school_id = ? ORDER BY id",
            (school_id(),),
        ).fetchall()
    finally:
        conn.close()

    return render_template("users.html", users=users)


@app.route("/users/add", methods=["POST"])
@admin_required
def add_user():
    """Create a teacher account inside the admin's own school."""
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    errors = validate_registration(email, password, password)
    if errors:
        flash(" ".join(errors.values()), "error")
        return redirect(url_for("user_list"))

    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO users (email, password_hash, role, school_id) "
                "VALUES (?, ?, 'teacher', ?)",
                (email, generate_password_hash(password), school_id()),
            )
    except integrity_errors():
        flash("This email is already registered.", "error")
        return redirect(url_for("user_list"))
    finally:
        conn.close()

    flash(f"Teacher account created for {email}.", "success")
    return redirect(url_for("user_list"))


@app.route("/users/<int:user_id>/role", methods=["POST"])
@admin_required
def change_role(user_id):
    """Change the role of a user in this school (not your own)."""
    new_role = request.form.get("role", "")

    if new_role not in ROLES:
        flash("Invalid role.", "error")
        return redirect(url_for("user_list"))

    if user_id == g.user["id"]:
        flash("You cannot change your own role.", "error")
        return redirect(url_for("user_list"))

    conn = get_db()
    try:
        with conn:
            cursor = conn.execute(
                "UPDATE users SET role = ? WHERE id = ? AND school_id = ?",
                (new_role, user_id, school_id()),
            )
        if cursor.rowcount == 0:
            abort(404)
    finally:
        conn.close()

    flash("Role updated.", "success")
    return redirect(url_for("user_list"))


# ------------------------------------------------------------- Student routes


@app.route("/")
@login_required
def dashboard():
    """Render the main dashboard with statistics and today's attendance."""
    today = today_local()

    conn = get_db()
    try:
        all_students = conn.execute(
            "SELECT * FROM students WHERE school_id = ? ORDER BY id DESC",
            (school_id(),),
        ).fetchall()
        today_rows = conn.execute(
            "SELECT a.student_id AS student_id, a.status AS status "
            "FROM attendance a JOIN students s ON s.id = a.student_id "
            "WHERE a.date = ? AND s.school_id = ?",
            (today.isoformat(), school_id()),
        ).fetchall()
    finally:
        conn.close()

    active_students = [s for s in all_students if s["status"] == "Active"]

    total = len(all_students)
    active = len(active_students)
    classes = len({(s["grade"], s["section"]) for s in all_students})

    by_grade = []
    for grade in GRADES:
        count = sum(1 for s in all_students if s["grade"] == grade)
        percent = round(count * 100 / total) if total else 0
        by_grade.append({"grade": grade, "count": count, "percent": percent})

    stats = {
        "total": total,
        "active": active,
        "inactive": total - active,
        "classes": classes,
    }
    return render_template(
        "dashboard.html",
        stats=stats,
        by_grade=by_grade,
        recent_students=all_students[:5],
        today_attendance=build_today_attendance(active_students, today_rows),
        today_iso=today.isoformat(),
        today_label=today.strftime("%A, %B %d, %Y"),
    )


@app.route("/sample-data", methods=["POST"])
@admin_required
def load_sample_data():
    """Fill an empty school with a few sample students to try the app."""
    conn = get_db()
    try:
        with conn:
            existing = conn.execute(
                "SELECT COUNT(*) AS total FROM students WHERE school_id = ?",
                (school_id(),),
            ).fetchone()["total"]

            if existing:
                flash("Sample data can only be added to an empty school.", "error")
                return redirect(url_for("dashboard"))

            insert_sample_students(conn, school_id())
    finally:
        conn.close()

    flash("Sample students added.", "success")
    return redirect(url_for("dashboard"))


@app.route("/students")
@login_required
def student_list():
    """Render one page of students, filtered by name and/or grade."""
    query = request.args.get("q", "").strip()
    grade_filter = request.args.get("grade", "").strip()
    # A missing or non-numeric page number falls back to page 1.
    requested_page = request.args.get("page", 1, type=int)

    conditions = ["school_id = ?"]
    params = [school_id()]

    if query:
        # LOWER() on both sides gives a case-insensitive search in both databases.
        conditions.append("LOWER(name) LIKE LOWER(?)")
        params.append(f"%{query}%")
    if grade_filter in [str(g) for g in GRADES]:
        conditions.append("grade = ?")
        params.append(int(grade_filter))
    else:
        grade_filter = ""

    where = " WHERE " + " AND ".join(conditions)

    conn = get_db()
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS total FROM students" + where, params
        ).fetchone()["total"]
        pager = paginate(total, requested_page, STUDENTS_PER_PAGE)

        # "id" breaks ties so students never repeat or vanish between pages.
        results = conn.execute(
            "SELECT * FROM students"
            + where
            + " ORDER BY grade, section, name, id LIMIT ? OFFSET ?",
            [*params, STUDENTS_PER_PAGE, pager["offset"]],
        ).fetchall()
    finally:
        conn.close()

    return render_template(
        "students.html",
        students=results,
        query=query,
        grade_filter=grade_filter,
        pager=pager,
    )


@app.route("/students/add", methods=["GET", "POST"])
@admin_required
def add_student():
    """Show the add-student form (GET) and save a new student (POST)."""
    errors = {}
    form = {
        "name": "",
        "grade": "9",
        "section": "A",
        "gender": "Male",
        "parent_phone": "",
        "status": "Active",
    }

    if request.method == "POST":
        form = read_student_form()
        errors = validate_student(form)

        if not errors:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO students "
                        "(school_id, name, grade, section, gender, parent_phone, status) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            school_id(),
                            form["name"],
                            int(form["grade"]),
                            form["section"],
                            form["gender"],
                            form["parent_phone"],
                            form["status"],
                        ),
                    )
            finally:
                conn.close()
            flash("Student added successfully!", "success")
            return redirect(url_for("student_list"))

    return render_template("add_student.html", student=None, form=form, errors=errors)


@app.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_student(student_id):
    """Show the edit form (GET) and update the student (POST)."""
    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE id = ? AND school_id = ?",
            (student_id, school_id()),
        ).fetchone()
        if student is None:
            abort(404)

        errors = {}
        form = {
            "name": student["name"],
            "grade": str(student["grade"]),
            "section": student["section"],
            "gender": student["gender"],
            "parent_phone": student["parent_phone"],
            "status": student["status"],
        }

        if request.method == "POST":
            form = read_student_form()
            errors = validate_student(form)

            if not errors:
                with conn:
                    conn.execute(
                        "UPDATE students SET name = ?, grade = ?, section = ?, "
                        "gender = ?, parent_phone = ?, status = ? "
                        "WHERE id = ? AND school_id = ?",
                        (
                            form["name"],
                            int(form["grade"]),
                            form["section"],
                            form["gender"],
                            form["parent_phone"],
                            form["status"],
                            student_id,
                            school_id(),
                        ),
                    )
                flash("Student updated successfully!", "success")
                return redirect(url_for("student_list"))
    finally:
        conn.close()

    return render_template("add_student.html", student=student, form=form, errors=errors)


@app.route("/students/<int:student_id>/delete", methods=["POST"])
@admin_required
def delete_student(student_id):
    """Delete the student (and their attendance and marks) with the given ID."""
    conn = get_db()
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM students WHERE id = ? AND school_id = ?",
                (student_id, school_id()),
            )
        if cursor.rowcount == 0:
            abort(404)
    finally:
        conn.close()

    flash("Student deleted.", "success")
    return redirect(url_for("student_list"))


@app.route("/students/<int:student_id>/report")
@login_required
def report_card(student_id):
    """Show one student's report card: marks, average, rank, and attendance."""
    term = request.args.get("term", TERMS[0])
    if term not in TERMS:
        term = TERMS[0]

    conn = get_db()
    try:
        student = conn.execute(
            "SELECT * FROM students WHERE id = ? AND school_id = ?",
            (student_id, school_id()),
        ).fetchone()
        if student is None:
            abort(404)

        mark_rows = conn.execute(
            "SELECT subject, score FROM marks WHERE student_id = ? AND term = ?",
            (student_id, term),
        ).fetchall()

        attendance_rows = conn.execute(
            "SELECT status, COUNT(*) AS total FROM attendance "
            "WHERE student_id = ? GROUP BY status",
            (student_id,),
        ).fetchall()

        # Average per classmate (same school, grade, and section) for ranking.
        class_rows = conn.execute(
            "SELECT m.student_id AS student_id, AVG(m.score) AS average "
            "FROM marks m JOIN students s ON s.id = m.student_id "
            "WHERE s.school_id = ? AND s.grade = ? AND s.section = ? "
            "AND s.status = 'Active' AND m.term = ? GROUP BY m.student_id",
            (school_id(), student["grade"], student["section"], term),
        ).fetchall()
    finally:
        conn.close()

    scores = {row["subject"]: row["score"] for row in mark_rows}

    subject_rows = []
    for subject in SUBJECTS:
        score = scores.get(subject)
        if score is None:
            subject_rows.append({"subject": subject, "score": "—", "result": "—"})
        else:
            result = "Pass" if score >= PASS_MARK else "Fail"
            subject_rows.append(
                {"subject": subject, "score": f"{score:g}", "result": result}
            )

    average = None
    average_text = "—"
    remark = ""
    rank_text = "—"

    if scores:
        average = sum(scores.values()) / len(scores)
        average_text = f"{average:.1f}"
        remark = average_remark(average)

        classmates = {row["student_id"] for row in class_rows} | {student_id}
        higher = sum(
            1
            for row in class_rows
            if row["student_id"] != student_id and row["average"] > average
        )
        rank_text = f"{higher + 1} of {len(classmates)}"

    attendance_counts = {status: 0 for status in ATTENDANCE_STATUSES}
    for row in attendance_rows:
        if row["status"] in attendance_counts:
            attendance_counts[row["status"]] = row["total"]

    days_recorded = sum(attendance_counts.values())
    if days_recorded:
        # A late student still attended, so Late counts as attended.
        attended = attendance_counts["Present"] + attendance_counts["Late"]
        attendance_rate = f"{round(attended * 100 / days_recorded)}%"
    else:
        attendance_rate = "—"

    return render_template(
        "report_card.html",
        student=student,
        term=term,
        subject_rows=subject_rows,
        has_marks=bool(scores),
        average_text=average_text,
        remark=remark,
        rank_text=rank_text,
        attendance_counts=attendance_counts,
        days_recorded=days_recorded,
        attendance_rate=attendance_rate,
    )


def read_class_filters():
    """Read and validate the grade, section, and term from the URL."""
    grade = request.args.get("grade", "9")
    if grade not in [str(g) for g in GRADES]:
        grade = "9"

    section = request.args.get("section", "A")
    if section not in SECTIONS:
        section = "A"

    term = request.args.get("term", TERMS[0])
    if term not in TERMS:
        term = TERMS[0]

    return grade, section, term


def fetch_class_report_data(grade, section, term):
    """Load one class's active students and marks, limited to this school."""
    conn = get_db()
    try:
        class_students = conn.execute(
            "SELECT * FROM students "
            "WHERE school_id = ? AND grade = ? AND section = ? "
            "AND status = 'Active' ORDER BY name, id",
            (school_id(), int(grade), section),
        ).fetchall()

        mark_rows = conn.execute(
            "SELECT m.student_id AS student_id, m.subject AS subject, "
            "m.score AS score "
            "FROM marks m JOIN students s ON s.id = m.student_id "
            "WHERE s.school_id = ? AND s.grade = ? AND s.section = ? "
            "AND s.status = 'Active' AND m.term = ?",
            (school_id(), int(grade), section, term),
        ).fetchall()
    finally:
        conn.close()

    return class_students, mark_rows


@app.route("/class-report")
@login_required
def class_report():
    """Show every student's marks, average, and rank for one class and term."""
    grade, section, term = read_class_filters()
    class_students, mark_rows = fetch_class_report_data(grade, section, term)
    rows, subject_stats, summary = build_class_report(class_students, mark_rows)

    return render_template(
        "class_report.html",
        rows=rows,
        subject_stats=subject_stats,
        summary=summary,
        grade=grade,
        section=section,
        term=term,
    )


# ----------------------------------------------------------- Attendance route


@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    """Show and save daily attendance for one class (grade + section)."""
    grade = request.values.get("grade", "9")
    if grade not in [str(g) for g in GRADES]:
        grade = "9"

    section = request.values.get("section", "A")
    if section not in SECTIONS:
        section = "A"

    try:
        selected_date = date.fromisoformat(request.values.get("date", ""))
    except ValueError:
        selected_date = today_local()
    date_iso = selected_date.isoformat()

    conn = get_db()
    try:
        class_students = conn.execute(
            "SELECT * FROM students "
            "WHERE school_id = ? AND grade = ? AND section = ? "
            "AND status = 'Active' ORDER BY name, id",
            (school_id(), int(grade), section),
        ).fetchall()

        if request.method == "POST":
            # Only students of this class (and so of this school) are saved.
            records = []
            for student in class_students:
                value = request.form.get(f"status_{student['id']}")
                if value in ATTENDANCE_STATUSES:
                    records.append((student["id"], date_iso, value))

            with conn:
                conn.executemany(
                    "INSERT INTO attendance (student_id, date, status) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT (student_id, date) DO UPDATE SET status = excluded.status",
                    records,
                )
            flash("Attendance saved.", "success")
            return redirect(
                url_for("attendance", grade=grade, section=section, date=date_iso)
            )

        rows = conn.execute(
            "SELECT a.student_id AS student_id, a.status AS status "
            "FROM attendance a JOIN students s ON s.id = a.student_id "
            "WHERE a.date = ? AND s.school_id = ?",
            (date_iso, school_id()),
        ).fetchall()
    finally:
        conn.close()

    records = {row["student_id"]: row["status"] for row in rows}
    summary = {status: 0 for status in ATTENDANCE_STATUSES}
    for student in class_students:
        recorded = records.get(student["id"])
        if recorded in summary:
            summary[recorded] += 1

    return render_template(
        "attendance.html",
        students=class_students,
        records=records,
        summary=summary,
        grade=grade,
        section=section,
        date_iso=date_iso,
    )


# ----------------------------------------------------------------- Marks route


@app.route("/marks", methods=["GET", "POST"])
@login_required
def marks():
    """Show and save marks for one class, subject, and term."""
    grade = request.values.get("grade", "9")
    if grade not in [str(g) for g in GRADES]:
        grade = "9"

    section = request.values.get("section", "A")
    if section not in SECTIONS:
        section = "A"

    subject = request.values.get("subject", SUBJECTS[0])
    if subject not in SUBJECTS:
        subject = SUBJECTS[0]

    term = request.values.get("term", TERMS[0])
    if term not in TERMS:
        term = TERMS[0]

    errors = {}
    entered = {}

    conn = get_db()
    try:
        class_students = conn.execute(
            "SELECT * FROM students "
            "WHERE school_id = ? AND grade = ? AND section = ? "
            "AND status = 'Active' ORDER BY name, id",
            (school_id(), int(grade), section),
        ).fetchall()

        if request.method == "POST":
            # Only students of this class (and so of this school) are saved.
            records = []
            for student in class_students:
                raw = request.form.get(f"score_{student['id']}", "").strip()
                entered[student["id"]] = raw
                if raw == "":
                    continue  # Blank means "no mark yet".

                try:
                    score = float(raw)
                except ValueError:
                    errors[student["id"]] = "Enter a number."
                    continue

                # NaN fails this comparison too, so it is rejected as well.
                if not 0 <= score <= 100:
                    errors[student["id"]] = "Score must be between 0 and 100."
                    continue

                records.append((student["id"], subject, term, score))

            if not errors:
                with conn:
                    conn.executemany(
                        "INSERT INTO marks (student_id, subject, term, score) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT (student_id, subject, term) "
                        "DO UPDATE SET score = excluded.score",
                        records,
                    )
                flash("Marks saved.", "success")
                return redirect(
                    url_for(
                        "marks",
                        grade=grade,
                        section=section,
                        subject=subject,
                        term=term,
                    )
                )
            flash("Please fix the highlighted scores.", "error")

        rows = conn.execute(
            "SELECT m.student_id AS student_id, m.score AS score "
            "FROM marks m JOIN students s ON s.id = m.student_id "
            "WHERE m.subject = ? AND m.term = ? AND s.school_id = ?",
            (subject, term, school_id()),
        ).fetchall()
    finally:
        conn.close()

    saved = {row["student_id"]: row["score"] for row in rows}
    class_scores = [
        saved[s["id"]] for s in class_students if s["id"] in saved
    ]

    if class_scores:
        summary = {
            "count": len(class_scores),
            "average": f"{sum(class_scores) / len(class_scores):.1f}",
            "highest": f"{max(class_scores):g}",
            "lowest": f"{min(class_scores):g}",
        }
    else:
        summary = {"count": 0, "average": "—", "highest": "—", "lowest": "—"}

    scores = {student_id: f"{value:g}" for student_id, value in saved.items()}

    return render_template(
        "marks.html",
        students=class_students,
        scores=scores,
        entered=entered,
        errors=errors,
        summary=summary,
        grade=grade,
        section=section,
        subject=subject,
        term=term,
    )


# -------------------------------------------------------------- Export routes


def csv_response(filename, headers, rows):
    """Return a CSV file as a download."""
    response = Response(build_csv(headers, rows), mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/export")
@admin_required
def export_page():
    """List the available CSV downloads."""
    return render_template("export.html")


@app.route("/students/export.csv")
@admin_required
def students_export():
    """Download the student list (respecting the search and grade filters)."""
    query = request.args.get("q", "").strip()
    grade_filter = request.args.get("grade", "").strip()

    conditions = ["school_id = ?"]
    params = [school_id()]

    if query:
        conditions.append("LOWER(name) LIKE LOWER(?)")
        params.append(f"%{query}%")
    if grade_filter in [str(g) for g in GRADES]:
        conditions.append("grade = ?")
        params.append(int(grade_filter))

    sql = (
        "SELECT * FROM students WHERE "
        + " AND ".join(conditions)
        + " ORDER BY grade, section, name, id"
    )

    conn = get_db()
    try:
        students = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    rows = [
        [
            s["id"],
            s["name"],
            s["grade"],
            s["section"],
            s["gender"],
            s["parent_phone"],
            s["status"],
        ]
        for s in students
    ]
    return csv_response(
        f"students_{today_local().isoformat()}.csv",
        ["ID", "Name", "Grade", "Section", "Gender", "Parent Phone", "Status"],
        rows,
    )


@app.route("/class-report/export.csv")
@login_required
def class_report_export():
    """Download the class report for one grade, section, and term."""
    grade, section, term = read_class_filters()
    class_students, mark_rows = fetch_class_report_data(grade, section, term)
    report_rows, subject_stats, _summary = build_class_report(
        class_students, mark_rows
    )

    headers = ["Rank", "Name", *SUBJECTS, "Total", "Average", "Remark", "Result"]

    def blank_if_missing(text):
        return "" if text == "—" else text

    data = []
    for row in report_rows:
        data.append(
            [
                "" if row["rank"] is None else row["rank"],
                row["student"]["name"],
                *[blank_if_missing(cell["text"]) for cell in row["cells"]],
                blank_if_missing(row["total_text"]),
                blank_if_missing(row["average_text"]),
                row["remark"],
                row["result"],
            ]
        )

    # Subject statistics go at the bottom, like on the page.
    for label, key in (
        ("Subject Average", "average"),
        ("Highest", "highest"),
        ("Lowest", "lowest"),
        ("Pass Rate", "pass_rate"),
    ):
        values = [blank_if_missing(stat[key]) for stat in subject_stats]
        data.append(["", label, *values, "", "", "", ""])

    safe_term = term.replace(" ", "-")
    return csv_response(
        f"class_report_grade{grade}_{section}_{safe_term}.csv", headers, data
    )


@app.route("/export/marks.csv")
@admin_required
def marks_export():
    """Download every mark of this school (a backup of all scores)."""
    conn = get_db()
    try:
        mark_rows = conn.execute(
            "SELECT s.id AS student_id, s.name AS name, s.grade AS grade, "
            "s.section AS section, m.term AS term, m.subject AS subject, "
            "m.score AS score "
            "FROM marks m JOIN students s ON s.id = m.student_id "
            "WHERE s.school_id = ? "
            "ORDER BY s.grade, s.section, s.name, m.term, m.subject",
            (school_id(),),
        ).fetchall()
    finally:
        conn.close()

    rows = [
        [
            r["student_id"],
            r["name"],
            r["grade"],
            r["section"],
            r["term"],
            r["subject"],
            f"{r['score']:g}",
        ]
        for r in mark_rows
    ]
    return csv_response(
        f"marks_{today_local().isoformat()}.csv",
        ["Student ID", "Name", "Grade", "Section", "Term", "Subject", "Score"],
        rows,
    )


@app.route("/export/attendance.csv")
@admin_required
def attendance_export():
    """Download every attendance record of this school (a backup)."""
    conn = get_db()
    try:
        attendance_rows = conn.execute(
            "SELECT s.id AS student_id, s.name AS name, s.grade AS grade, "
            "s.section AS section, a.date AS day, a.status AS status "
            "FROM attendance a JOIN students s ON s.id = a.student_id "
            "WHERE s.school_id = ? "
            "ORDER BY a.date, s.grade, s.section, s.name",
            (school_id(),),
        ).fetchall()
    finally:
        conn.close()

    rows = [
        [r["student_id"], r["name"], r["grade"], r["section"], r["day"], r["status"]]
        for r in attendance_rows
    ]
    return csv_response(
        f"attendance_{today_local().isoformat()}.csv",
        ["Student ID", "Name", "Grade", "Section", "Date", "Status"],
        rows,
    )


init_db()

if __name__ == "__main__":
    # Debug mode is only enabled when FLASK_DEBUG=1 is set (local development).
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
