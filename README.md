# 🎓 EduTrack

> Simple student records, managed well.

EduTrack is a student management web application built with **Flask** and
**SQLite**. It was created as a learning and portfolio project to practice
full-stack web development: routing, templating, database access, form
validation, and automated testing.

## Features

- Dashboard with summary statistics (total, active, inactive, courses)
- Student list with search by name or course
- Add, edit, and delete students
- Server-side form validation with clear error messages
- Flash notifications and a custom 404 page
- Persistent storage with SQLite
- Automated tests with pytest

## Tech Stack

| Layer      | Technology                     |
|------------|--------------------------------|
| Backend    | Python 3, Flask                |
| Database   | SQLite (via the `sqlite3` module) |
| Frontend   | HTML, CSS, Jinja2 templates    |
| Testing    | pytest                         |

## Project Structure

```
edutrack/
├── app.py              # Flask application and routes
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

Open http://127.0.0.1:5000 in your browser. The database file
(`edutrack.db`) is created automatically on first run.

## Running Tests

```bash
python -m pytest
```

Tests use a temporary database, so your real data is never modified.

## Roadmap

- [x] Dashboard
- [x] Student CRUD and search
- [x] SQLite persistence
- [x] Validation, flash messages, and 404 page
- [x] Automated tests
- [ ] User authentication
- [ ] Pagination
- [ ] Deployment

## License

MIT