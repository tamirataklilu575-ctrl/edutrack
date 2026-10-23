"""EduTrack - Student Management System (Phase 2: Student CRUD)."""

from flask import Flask, abort, redirect, render_template, request, url_for

app = Flask(__name__)

# Temporary in-memory data. This will be replaced by SQLite in Phase 3.
students = [
    {"id": 1, "name": "Abebe Kebede", "course": "Computer Science", "status": "Active"},
    {"id": 2, "name": "Selam Tadesse", "course": "Information Systems", "status": "Active"},
    {"id": 3, "name": "Dawit Alemu", "course": "Software Engineering", "status": "Inactive"},
    {"id": 4, "name": "Hana Girma", "course": "Computer Science", "status": "Active"},
]


def next_id():
    """Return the next available student ID."""
    return max((s["id"] for s in students), default=0) + 1


def find_student(student_id):
    """Return the student with the given ID, or None if not found."""
    return next((s for s in students if s["id"] == student_id), None)


@app.route("/")
def dashboard():
    """Render the main dashboard with summary statistics."""
    total = len(students)
    active = sum(1 for s in students if s["status"] == "Active")
    courses = len({s["course"] for s in students})

    stats = {
        "total": total,
        "active": active,
        "inactive": total - active,
        "courses": courses,
    }
    return render_template("dashboard.html", stats=stats, recent_students=students)


@app.route("/students")
def student_list():
    """Render the list of students, optionally filtered by a search query."""
    query = request.args.get("q", "").strip()

    if query:
        search = query.lower()
        results = [
            s for s in students
            if search in s["name"].lower() or search in s["course"].lower()
        ]
    else:
        results = students

    return render_template("students.html", students=results, query=query)


@app.route("/students/add", methods=["GET", "POST"])
def add_student():
    """Show the add-student form (GET) and save a new student (POST)."""
    if request.method == "POST":
        name = request.form["name"].strip()
        course = request.form["course"].strip()
        status = request.form["status"]

        if name and course:
            students.append(
                {"id": next_id(), "name": name, "course": course, "status": status}
            )
            return redirect(url_for("student_list"))

    return render_template("add_student.html", student=None)


@app.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
def edit_student(student_id):
    """Show the edit form (GET) and update the student (POST)."""
    student = find_student(student_id)
    if student is None:
        abort(404)

    if request.method == "POST":
        name = request.form["name"].strip()
        course = request.form["course"].strip()

        if name and course:
            student["name"] = name
            student["course"] = course
            student["status"] = request.form["status"]
            return redirect(url_for("student_list"))

    return render_template("add_student.html", student=student)


@app.route("/students/<int:student_id>/delete", methods=["POST"])
def delete_student(student_id):
    """Delete the student with the given ID."""
    student = find_student(student_id)
    if student is None:
        abort(404)

    students.remove(student)
    return redirect(url_for("student_list"))


if __name__ == "__main__":
    app.run(debug=True)