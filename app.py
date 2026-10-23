"""EduTrack - Student Management System (Phase 3: SQLite Database)."""

import sqlite3
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for

app = Flask(__name__)

DATABASE = Path(__file__).parent / "edutrack.db"

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
    # `with` commits the transaction but does not close the connection.


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
    if request.method == "POST":
        name = request.form["name"].strip()
        course = request.form["course"].strip()
        status = request.form["status"]

        if name and course:
            conn = get_db()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO students (name, course, status) VALUES (?, ?, ?)",
                        (name, course, status),
                    )
            finally:
                conn.close()
            return redirect(url_for("student_list"))

    return render_template("add_student.html", student=None)


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

        if request.method == "POST":
            name = request.form["name"].strip()
            course = request.form["course"].strip()
            status = request.form["status"]

            if name and course:
                with conn:
                    conn.execute(
                        "UPDATE students SET name = ?, course = ?, status = ? WHERE id = ?",
                        (name, course, status, student_id),
                    )
                return redirect(url_for("student_list"))
    finally:
        conn.close()

    return render_template("add_student.html", student=student)


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

    return redirect(url_for("student_list"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)