# 🎓 EduTrack

> A high school management system: students, attendance, marks, and report cards.

**🔗 Live Demo:** https://edutrack-6jlc.onrender.com

> The demo runs on a free hosting plan. The first load can take up to a
> minute while the server wakes up. Register with any email to try it
> (new accounts get the **Teacher** role). Please use fake data only.

EduTrack is a full-stack web application built with **Flask** and
**PostgreSQL**. It was created as a learning and portfolio project to
practice routing, templating, database design, authentication, role-based
access, form validation, automated testing, and deployment.

## Features

- Email registration and login with securely hashed passwords
- Persistent sessions (users stay signed in for 7 days)
- **Roles:** admins manage students and users; teachers take attendance and
  enter marks
- Dashboard with summary statistics, a students-by-grade chart, and today's attendance (present, absent, late, and classes still pending)
- Student records: grade (9-12), section, gender, and parent phone
- Search by name and filter by grade
- Daily **attendance** per class (Present / Absent / Late)
- **Marks** by subject and semester, with class average, highest, and lowest
- Printable **report card** per student: marks, average, class rank, and
  attendance rate
- **Class report**: every student's scores, total, average, rank, and result,
  plus per-subject statistics
- Server-side form validation, flash messages, and a custom 404 page
- **CSV export** for students, class reports, marks, and attendance (Excel-friendly, with spreadsheet-formula protection)
- Automated tests with pytest

## Tech Stack

| Layer      | Technology                                        |
|------------|---------------------------------------------------|
| Backend    | Python 3, Flask                                   |
| Database   | PostgreSQL in production (Neon); SQLite locally   |
| Frontend   | HTML, CSS, Jinja2 templates                       |
| Auth       | Werkzeug password hashing, Flask sessions         |
| Testing    | pytest                                            |
| Hosting    | Render (web service) + Neon (database)            |

## Project Structure

```
edutrack/
├── app.py              # Flask application, routes, and database layer
├── Procfile            # Production start command (gunicorn)
├── requirements.txt    # Python dependencies
├── static/css/         # Stylesheets
├── templates/          # Jinja2 HTML templates
└── tests/              # Automated tests
```

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git

### Installation

```bash
git clone https://github.com/tamirataklilu575-ctrl/edutrack.git
cd edutrack
python -m venv venv
```

Activate the virtual environment:

```bash
# Windows (PowerShell)
venv\Scripts\Activate.ps1

# macOS / Linux
source venv/bin/activate
```

Install dependencies and run the app:

```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in your browser. Locally the app uses a SQLite
file (`edutrack.db`) that is created automatically. The **first account you
register becomes the admin**.

## Configuration

| Variable       | Purpose                                                         |
|----------------|-----------------------------------------------------------------|
| `DATABASE_URL` | PostgreSQL connection string. If unset, SQLite is used.         |
| `SECRET_KEY`   | Secret used to sign session cookies. Set it in production.      |
| `FLASK_DEBUG`  | Set to `1` to enable debug mode (local development only).       |

Never commit real secrets. Set them in your hosting provider's dashboard.

## Running Tests

```bash
python -m pytest
```

Tests always run on a temporary SQLite database, so real data is never
modified.

## Deployment

The app is deployed on [Render](https://render.com) using `gunicorn app:app`,
with a free [Neon](https://neon.com) PostgreSQL database for persistent
storage. Set `DATABASE_URL` and `SECRET_KEY` as environment variables on the
web service.

## Roadmap

- [x] Dashboard
- [x] Student management and search
- [x] Authentication with roles
- [x] Attendance and marks
- [x] Report card and class report
- [x] Persistent PostgreSQL storage
- [x] Automated tests
- [ ] Email verification and password reset
- [x] Export reports to CSV
- [ ] Pagination
- [x] Attendance summary on the dashboard

## License

MIT