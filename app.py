"""EduTrack - High School Management System."""

import os
import re
import sqlite3
from datetime import date
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
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

app = Flask(__name__)
# Read the secret key from the environment in production.
# The fallback value is for local development only.
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

DATABASE = Path(__file__).parent / "edutrack.db"

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

MIN_LENGTH = 2
MAX_LENGTH = 100
PHONE_PATTERN = re.compile(r"^\+?[0-9 ]{9,15}$")

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,30}$")
MIN_PASSWORD_LENGTH = 6

# (name, grade, section, gender, parent_phone, status)
SEED_STUDENTS = [
    ("Abebe Kebede", 9, "A", "Male", "+251911000001", "Active"),
    ("Meron Bekele", 9, "B", "Female", "+251911000002", "Active"),
    ("Selam Tadesse", 10, "B", "Female", "+251911000003", "Active"),
    ("Dawit Alemu", 11, "A", "Male", "", "Inactive"),
    ("Hana Girma", 12, "C", "Female", "+251911000005", "Active"),
]


def get_db():
    """Open a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    # SQLite does not enforce foreign keys unless this is switched on.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables, migrate older databases, and add sample students."""
    with get_db() as conn:
        # Development-stage migration: replace the old university-style table.
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(students)")]
        if columns and "grade" not in columns:
            conn.execute("DROP TABLE students")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'teacher'
            )
            """
        )

        # Migration: databases created before roles existed get a role column.
        # The oldest account becomes the admin; everyone else is a teacher.
        user_columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)")]
        if "role" not in user_columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'teacher'"
            )
            conn.execute(
                "UPDATE users SET role = 'admin' "
                "WHERE id = (SELECT MIN(id) FROM users)"
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL,
                UNIQUE (student_id, date),
                FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                term TEXT NOT NULL,
                score REAL NOT NULL,
                UNIQUE (student_id, subject, term),
                FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO students "
                "(name, grade, section, gender, parent_phone, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                SEED_STUDENTS,
            )


@app.before_request
def load_current_user():
    """Load the signed-in user (with their current role) for this request."""
    g.user = None
    if request.endpoint == "static":
        return

    user_id = session.get("user_id")
    if user_id is None:
        return

    conn = get_db()
    try:
        g.user = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    if g.user is None:
        # The account no longer exists, so end the session.
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
    """Show the registration form (GET) and create a new user (POST)."""
    if g.user is not None:
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
                    # The very first account becomes the admin.
                    user_count = conn.execute(
                        "SELECT COUNT(*) FROM users"
                    ).fetchone()[0]
                    role = "admin" if user_count == 0 else "teacher"
                    conn.execute(
                        "INSERT INTO users (username, password_hash, role) "
                        "VALUES (?, ?, ?)",
                        (form["username"], generate_password_hash(password), role),
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
    if g.user is not None:
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


# ---------------------------------------------------------------- User routes


@app.route("/users")
@admin_required
def user_list():
    """List all accounts so an admin can manage their roles."""
    conn = get_db()
    try:
        users = conn.execute(
            "SELECT id, username, role FROM users ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    return render_template("users.html", users=users)


@app.route("/users/<int:user_id>/role", methods=["POST"])
@admin_required
def change_role(user_id):
    """Change a user's role (admins cannot change their own)."""
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
                "UPDATE users SET role = ? WHERE id = ?", (new_role, user_id)
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
    )


@app.route("/students")
@login_required
def student_list():
    """Render students, optionally filtered by name and/or grade."""
    query = request.args.get("q", "").strip()
    grade_filter = request.args.get("grade", "").strip()

    sql = "SELECT * FROM students"
    conditions = []
    params = []

    if query:
        conditions.append("name LIKE ?")
        params.append(f"%{query}%")
    if grade_filter in [str(g) for g in GRADES]:
        conditions.append("grade = ?")
        params.append(int(grade_filter))
    else:
        grade_filter = ""

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY grade, section, name"

    conn = get_db()
    try:
        results = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    return render_template(
        "students.html", students=results, query=query, grade_filter=grade_filter
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
                        "(name, grade, section, gender, parent_phone, status) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
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
            "SELECT * FROM students WHERE id = ?", (student_id,)
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
                        "gender = ?, parent_phone = ?, status = ? WHERE id = ?",
                        (
                            form["name"],
                            int(form["grade"]),
                            form["section"],
                            form["gender"],
                            form["parent_phone"],
                            form["status"],
                            student_id,
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
            cursor = conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
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
            "SELECT * FROM students WHERE id = ?", (student_id,)
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

        # Average per classmate (same grade and section) for ranking.
        class_rows = conn.execute(
            "SELECT m.student_id AS student_id, AVG(m.score) AS average "
            "FROM marks m JOIN students s ON s.id = m.student_id "
            "WHERE s.grade = ? AND s.section = ? AND s.status = 'Active' "
            "AND m.term = ? GROUP BY m.student_id",
            (student["grade"], student["section"], term),
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


@app.route("/class-report")
@login_required
def class_report():
    """Show every student's marks, average, and rank for one class and term."""
    grade = request.args.get("grade", "9")
    if grade not in [str(g) for g in GRADES]:
        grade = "9"

    section = request.args.get("section", "A")
    if section not in SECTIONS:
        section = "A"

    term = request.args.get("term", TERMS[0])
    if term not in TERMS:
        term = TERMS[0]

    conn = get_db()
    try:
        class_students = conn.execute(
            "SELECT * FROM students "
            "WHERE grade = ? AND section = ? AND status = 'Active' ORDER BY name",
            (int(grade), section),
        ).fetchall()

        mark_rows = conn.execute(
            "SELECT m.student_id AS student_id, m.subject AS subject, "
            "m.score AS score "
            "FROM marks m JOIN students s ON s.id = m.student_id "
            "WHERE s.grade = ? AND s.section = ? AND s.status = 'Active' "
            "AND m.term = ?",
            (int(grade), section, term),
        ).fetchall()
    finally:
        conn.close()

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
        selected_date = date.today()
    date_iso = selected_date.isoformat()

    conn = get_db()
    try:
        class_students = conn.execute(
            "SELECT * FROM students "
            "WHERE grade = ? AND section = ? AND status = 'Active' ORDER BY name",
            (int(grade), section),
        ).fetchall()

        if request.method == "POST":
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
            "SELECT student_id, status FROM attendance WHERE date = ?", (date_iso,)
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
            "WHERE grade = ? AND section = ? AND status = 'Active' ORDER BY name",
            (int(grade), section),
        ).fetchall()

        if request.method == "POST":
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
            "SELECT student_id, score FROM marks WHERE subject = ? AND term = ?",
            (subject, term),
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


init_db()

if __name__ == "__main__":
    # Debug mode is only enabled when FLASK_DEBUG=1 is set (local development).
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")