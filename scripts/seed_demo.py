"""Fill the database with FAKE demo data (for screenshots and demos).

Run it from the project folder:

    python scripts/seed_demo.py

It adds about 30 students, one semester of marks, and recent attendance.
Running it twice is safe: it does nothing if the demo data already exists.
"""

import random
import sys
from datetime import timedelta
from pathlib import Path

# Let "import app" work when this file is run from any folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as app_module  # noqa: E402

# Demo students get phone numbers with this prefix, which marks them as demo data.
DEMO_PHONE_PREFIX = "+251922"

MALE_NAMES = [
    "Abel", "Biruk", "Dagim", "Eyob", "Fikadu",
    "Henok", "Kaleb", "Nahom", "Samson", "Yonas",
]
FEMALE_NAMES = [
    "Bethlehem", "Eden", "Hiwot", "Liya", "Rahel",
    "Saron", "Tigist", "Yordanos", "Mahlet", "Ruth",
]
FATHER_NAMES = [
    "Alemu", "Bekele", "Chala", "Desta", "Gebre", "Haile", "Kebede",
    "Lemma", "Mulugeta", "Negash", "Tadesse", "Wolde", "Yilma", "Zewdu",
]

# (grade, section, number of students)
DEMO_CLASSES = [
    (9, "A", 8),
    (9, "B", 4),
    (10, "A", 5),
    (10, "B", 4),
    (11, "A", 4),
    (12, "C", 4),
]

TERM = "Semester 1"
ATTENDANCE_DAYS = 10


def make_students():
    """Return a list of (name, grade, section, gender, phone, status) tuples."""
    students = []
    index = 0

    for grade, section, count in DEMO_CLASSES:
        for _ in range(count):
            if index % 2 == 0:
                gender = "Male"
                first = MALE_NAMES[(index // 2) % len(MALE_NAMES)]
            else:
                gender = "Female"
                first = FEMALE_NAMES[(index // 2) % len(FEMALE_NAMES)]

            father = FATHER_NAMES[(index * 3 + 1) % len(FATHER_NAMES)]
            phone = f"{DEMO_PHONE_PREFIX}{100000 + index}"
            # A couple of inactive students make the dashboard more realistic.
            status = "Inactive" if index % 13 == 12 else "Active"

            students.append(
                (f"{first} {father}", grade, section, gender, phone, status)
            )
            index += 1

    return students


def seed_demo_data(today=None):
    """Add demo students, marks, and attendance.

    Returns a dict of how many rows were added, or None if the demo data is
    already there.
    """
    today = today or app_module.today_local()
    rng = random.Random(2026)  # A fixed seed gives the same data every time.
    students = make_students()

    conn = app_module.get_db()
    try:
        with conn:
            already = conn.execute(
                "SELECT COUNT(*) AS total FROM students WHERE parent_phone LIKE ?",
                (f"{DEMO_PHONE_PREFIX}%",),
            ).fetchone()["total"]
            if already:
                return None

            conn.executemany(
                "INSERT INTO students "
                "(name, grade, section, gender, parent_phone, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                students,
            )

            active = conn.execute(
                "SELECT id, grade, section FROM students "
                "WHERE status = 'Active' ORDER BY id"
            ).fetchall()

            # Each student has an "ability", so their scores are believable.
            marks = []
            for student in active:
                ability = rng.randint(48, 92)
                for subject in app_module.SUBJECTS:
                    score = max(20, min(100, ability + rng.randint(-18, 10)))
                    marks.append((student["id"], subject, TERM, float(score)))

            # Today, plus recent weekdays.
            days = [today - timedelta(days=n) for n in range(ATTENDANCE_DAYS)]
            school_days = [d for d in days if d == today or d.weekday() < 5]

            attendance = []
            for day in school_days:
                for student in active:
                    # Leave Grade 9 B blank today, so the dashboard shows a
                    # class that still needs its attendance taken.
                    is_pending_class = (student["grade"], student["section"]) == (9, "B")
                    if day == today and is_pending_class:
                        continue

                    status = rng.choices(
                        ["Present", "Late", "Absent"], weights=[86, 6, 8]
                    )[0]
                    attendance.append((student["id"], day.isoformat(), status))

            conn.executemany(
                "INSERT INTO marks (student_id, subject, term, score) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (student_id, subject, term) "
                "DO UPDATE SET score = excluded.score",
                marks,
            )
            conn.executemany(
                "INSERT INTO attendance (student_id, date, status) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT (student_id, date) "
                "DO UPDATE SET status = excluded.status",
                attendance,
            )
    finally:
        conn.close()

    return {
        "students": len(students),
        "marks": len(marks),
        "attendance": len(attendance),
    }


def main(argv):
    """Run the script from the command line."""
    if app_module.using_postgres() and "--allow-postgres" not in argv:
        print("DATABASE_URL is set, so this would write to the PostgreSQL database.")
        print("Run again with --allow-postgres if that is really what you want.")
        return 1

    result = seed_demo_data()
    if result is None:
        print("Demo data is already in the database. Nothing to do.")
        return 0

    print(
        f"Added {result['students']} demo students, {result['marks']} marks, "
        f"and {result['attendance']} attendance records."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))