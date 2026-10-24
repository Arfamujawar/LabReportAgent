# LabReportAgent

Educational lab report explainer (Flask + SQLite). It does not diagnose or recommend treatment.

## Status
Available: registration/login, upload validation, text-PDF extraction, report history/search/delete, rule-based explanations (demo mode, no AI model called), summary download, per-user authorization, CSRF protection.
Requires configuration: OCR for scans/images (install Tesseract), external AI provider (not wired up), password reset email.
In development / Coming soon: trends, comparison, insights, assistant, glossary, reminders, multilingual, voice, family sharing. See the in-app "All features" page.

## Run on Windows (PowerShell)
Open the `LabReportAgent` folder in VS Code (the one containing `run.py`), then:
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then set SECRET_KEY to a long random string
python run.py
```
Open http://127.0.0.1:5000. The database is created automatically in `instance/`.
If activation is blocked: `Set-ExecutionPolicy -Scope Process Bypass`.

## OCR (optional)
Install Tesseract (UB Mannheim Windows build), then set `TESSERACT_CMD` in `.env`. Without it, scanned PDFs and images fail with a clear message.

## Tests
`python -m pytest -q`

## Layout
`app/` factory, `models.py`, `routes.py`, `extract.py`, `explain.py`, `templates/`, `static/`; `tests/`; `instance/` (database and uploads, git-ignored).

## Limits
Uploads are stored unencrypted locally. Extraction only recognises rows like `Hemoglobin 13.5 g/dL 12.0 - 15.5`. The Bootstrap CSS loads from a CDN, so the first page view needs internet. No regulatory compliance is claimed.
