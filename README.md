# Classarit
Class Sarit .. The flow of knowledge, Simple FastAPI + SQLite dashboard for independent teachers who run online classes.
## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py --reload
```

Open `http://127.0.0.1:8000`.

## Features

### Dashboard and demo access

- Demo entry page using `demo@classarit.local`.
- Responsive dashboard with sidebar navigation for students, classes, payments, materials, calendar, and settings.
- Summary cards for today's classes, upcoming classes, active students, pending payments, and monthly revenue.
- Today's schedule with student names, subjects, start times, durations, and meeting links.
- Automatically seeded demo teacher, students, class sessions, attendance, payments, and material records.

### Students

- Student cards showing subject, contact email, active status, fee amount, and billing type.
- API support for listing, creating, and updating students.
- Student records include guardian details, phone, class duration, start date, and notes.
- Fee type and amount fields, with Monthly, Per Class, and Package examples in the demo data.

### Classes and attendance

- Class list showing student, subject, date, time, status, and make-up labels.
- Join Class links that open the stored meeting URL.
- API support for listing, creating, and updating classes, including rescheduling through date and time updates.
- Meeting URL validation requiring an `http://` or `https://` prefix.
- Mark Present action and API support for recording or updating attendance.
- Cancel action that records `Teacher Cancelled` as the attendance status; it does not change the class session's status.
- API support for creating a make-up class linked to its original session.
- Class API fields for lesson notes, homework, and practice instructions.

### Payments

- Payment table showing student ID, billing month, amount due, amount paid, status, and payment method.
- API support for creating payment records with payment date and notes.
- Pending balance and current-month revenue calculations on the dashboard.
- Demo examples of Paid, Partial, and Due payments using UPI, Cash, and Bank Transfer.

### Learning materials

- Material cards with titles, subjects, descriptions, and file links.
- API uploads with title, description, and subject metadata.
- Supported file extensions: PDF, PNG, JPG, JPEG, MP3, WAV, DOCX, and TXT.
- Local file storage and serving under `/uploads`.

### Settings, storage, and API tools

- Read-only teacher profile showing name, email, and timezone.
- Persistent SQLite storage in `classarit.db` using SQLAlchemy.
- Project-relative paths for the database, templates, static assets, and uploads.
- Interactive API documentation at `/docs`, alternative documentation at `/redoc`, and the OpenAPI schema at `/openapi.json`.

### Current MVP limitations

- Demo entry does not implement password authentication or account management.
- Add Student and Schedule Class dialogs are placeholders; create and edit records through the API.
- The Reschedule button and Add Notes workflow are not implemented in the UI.
- Calendar is a placeholder; scheduled sessions are available in the Classes section.
- Payment creation, material uploads, and make-up scheduling are available through the API, without UI forms.
- Settings are display-only. Repeat type is stored on classes, but recurring sessions are not generated automatically.
- Assignment and material-assignment models exist, but have no exposed management UI or API.
- Seeded materials contain sample file paths; the corresponding sample files are not bundled.

## Run from IntelliJ IDEA

Enable the Python plugin and select `.venv/bin/python` as the project Python SDK.
Install dependencies with `.venv/bin/python -m pip install -r requirements.txt`.

Create a **Python** configuration under **Run → Edit Configurations**:

- Name: `Classarit`
- Run target: **Script path**, set to `run.py` in the project root
- Parameters: leave blank (optionally use `--reload` for development)
- Working directory: the project root (`classarit`)
- Python interpreter: the project's `.venv/bin/python`

Click Run and open <http://127.0.0.1:8000>. For debugging, remove `--reload`
and click Debug. The FastAPI entry point is `app/main.py`; launch it through
the `run.py` launcher using the configuration above.

The SQLite database is `classarit.db`. The demo email is `demo@classarit.local`.

## Deploy on Render

The repository includes a `render.yaml` Blueprint for a Python web service.
It uses a **paid Starter instance and a 1 GB persistent disk** so SQLite records
and uploaded files survive restarts and redeploys. See
[Render's persistent disk documentation](https://render.com/docs/disks).

1. Commit and push these project changes to your GitHub repository.
2. In Render, choose **New → Blueprint** and connect the repository.
3. Render reads `render.yaml`. Review the service and disk charges, then deploy.
4. Open the service's generated URL. `/health` should return `{"status":"ok"}`;
   `/docs` provides the API interface.

For an existing Render web service, configure these settings manually:

| Setting | Value |
| --- | --- |
| Runtime | Python 3 |
| Root directory | Leave blank (repository root) |
| Build command | `python -m pip install -r requirements.txt` |
| Start command | `python run.py` |
| Health check path | `/health` |
| Environment variable | `CLASSARIT_DATA_DIR=/var/data` |
| Persistent disk | Mount at `/var/data`, size 1 GB, paid instance required |

Both `.python-version` and the Blueprint select Python 3.13.5. For an existing
Render service, set `PYTHON_VERSION=3.13.5` in its Environment settings. This
avoids the SQLAlchemy typing error seen with Python 3.14 and the current dependencies. The server listens on Render's assigned
port without development reload. See the official
[FastAPI deployment guide](https://render.com/docs/deploy-fastapi) and
[Python version settings](https://render.com/docs/python-version).

### Data and demo behavior

- On Render, the database is `/var/data/classarit.db` and uploads are stored in
  `/var/data/uploads`. Tables and demo records are initialized at application startup.
- A new disk starts with fresh demo data; it does not copy your local database or uploads.
- Local development continues to use the project-root database and `uploads` folder
  when `CLASSARIT_DATA_DIR` is unset.
- This remains a public demo: login does not authenticate users, and API mutations
  are unauthenticated. Use sample data until authentication is implemented.

### Free demo option

For a disposable demo, create a **Free Web Service** manually with the build,
start, and health check settings above. Omit the disk and set
`CLASSARIT_DATA_DIR=/tmp/classarit`. Records and uploads will be lost on restarts
or redeploys. The supplied Blueprint uses paid storage to preserve data.


### One launcher for local and Render

Run `python run.py` locally, or right-click the root `run.py` in IntelliJ and
choose Run with the project virtual environment selected. It listens on
`127.0.0.1:8000`. Use `python run.py --reload` for automatic local reloads.

On Render, the same command detects Render's `RENDER=true` environment variable,
binds to `0.0.0.0`, and uses the assigned `PORT`. Keep Root Directory blank.
Unlike the Flask reference project's Gunicorn command, this launcher uses
Uvicorn to serve FastAPI's ASGI application.

When updating an existing Render service, push the new files first, set the
start command to `python run.py`, set `PYTHON_VERSION=3.13.5`, and redeploy.
Confirm the build log selects Python 3.13.5. Local file changes are not deployed
until they are committed and pushed to the branch connected to Render.
