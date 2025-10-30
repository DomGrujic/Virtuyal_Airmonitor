# Virtuyal

IoT air-quality monitoring project with a Flask API (Python), Tuya device integration, a simple web frontend, and generated documentation with Doxygen.

Authors: Alina S. & Dominik Grujic \
This was a final project for the LBS4 (Vocational School)

## Overview

Virtuyal reads sensor data from Tuya-based devices (tinytuya), persists data in MySQL via Flask‑SQLAlchemy, exposes a REST API (with Swagger UI), and serves a small frontend for viewing current and historical sensor values. Developer documentation is generated with Doxygen (Python docstrings are parsed via doxypypy).

Key features:
- Device management (add, list, edit, deactivate)
- Current data retrieval from devices via LAN
- History endpoints with aggregation (hour/day/week/month/year)
- User management (create/delete/validate, roles)
- Threshold warning preferences (email opt-in)
- SMTP settings stored in DB and used by email helpers
- Swagger UI for API exploration
- Doxygen site for developer docs

## Repository layout

- Frontend (static): `index.html`, `login.html`, `profil.html`, `historie.html`, `sensorvergleich.html`, `style.css`, and JS files like `charts-history.js`, `DataMainpage.js`, `LoginLogic.js`
- Backend (API): `pythonFiles/`
	- `api.py` – Flask app and all routes (sensor, data, user, settings)
	- `db.py` – SQLAlchemy models and DB helpers
	- `functions.py` – aggregation, email, scheduling, utilities
	- `models.py` – thin data models for devices and DPS parsing
	- `Doxyfile` – Doxygen configuration
	- `html/` – generated Doxygen site (output)
- Virtual environment: `virtuyalEnv/` (local dev only)

## Requirements

- Python 3.9+
- MySQL (database name expected: `virtuyal`)
- Recommended Python packages (install in your venv):
	- flask, flask-sqlalchemy, pymysql
	- flask-cors, flasgger, python-dotenv
	- tinytuya, apscheduler
	- doxypypy (for docs), doxygen (system package)

## Configuration

Environment variables used by the API:

- `DB_USER`, `DB_PASS` – used to build the DSN `mysql+pymysql://{DB_USER}:{DB_PASS}@localhost/virtuyal`
- `SMTP_HOST`, `SMTP_PORT` – optional defaults for SMTP if DB row isn’t set

Create a `.env` file at repo root or set environment variables via your shell. Also ensure the MySQL schema `virtuyal` exists and credentials are valid.

## Run the API (development)

From the repo root or `pythonFiles/`, activate your virtual environment and start the Flask app.

PowerShell (Windows):

```powershell
# activate your venv first
# .\virtuyalEnv\Scripts\Activate.ps1

# run the API
python .\pythonFiles\api.py
```

Linux/macOS (bash):

```bash
# source venv and run
# source virtuyalEnv/bin/activate
python pythonFiles/api.py
```

By default, the API listens on `http://0.0.0.0:8000` (debug mode). The Swagger UI is available at `/apidocs`.

Background job: a scheduler runs `two_minute_update` periodically to ingest data and check thresholds. It starts only in the reloader child when Flask debug mode is used.

## API highlights

- Current data: `GET /sensor/getCurrentData/<device_id>`
- Add device: `POST /sensor/add` (201 on create/reactivation, 409 if already active)
- Devices: list/edit/delete under `/sensor/*`
- History: `GET /sensor/history/{hour|day|week|month|year}/<device_id>?metric=...`
- Users: create/delete/validate, change role, list users
- Threshold warnings: set or list recipients
- SMTP settings: `GET/POST /settings/smtp`

See Swagger UI at `/apidocs` for full schemas and examples.

## Data precision and scaling

- HCHO and TVOC raw values from the device are scaled by `1/1000` for storage and API responses.
- Small values are rounded to 6 decimals so tiny concentrations (e.g., 0.00025) are visible.
- History aggregation also uses 6 decimals for averages.

## Doxygen documentation

Generate developer docs (Python docstrings are Google-style and parsed by doxypypy):

```powershell
# from the pythonFiles directory
cd pythonFiles
# run doxygen with the provided Doxyfile
doxygen Doxyfile
```

HTML output is written to `pythonFiles/html/`. Open `pythonFiles/html/index.html` in a browser.

Deploy docs to a web server (example):

```powershell
# copy the contents of pythonFiles/html/ to your server directory
scp -r .\pythonFiles\html\* user@server:/var/www/html/docs/
```

To combine frontend and backend docs in one Doxygen site, include `*.js` in `FILE_PATTERNS` and add your project root to `INPUT` in `Doxyfile`. Keep the doxypypy filter for `*.py` only.

## Frontend

The frontend is a set of static HTML/CSS/JS files calling the Flask API. You can serve them via any static server, or open locally during development. For production, place them behind a web server (e.g., Nginx/Apache) and configure the API base URL if needed.

## Notes

- Don’t commit secrets (DB or SMTP creds). Use `.env` or server-side env vars.
- Ensure network access to Tuya devices (LAN, port 6668). IPs are discovered via a scan helper.
- MySQL schema migrations are not automated; tables are created by SQLAlchemy when needed.

---

© 2025 Virtuyal – Alina S. & Dominik Grujic
