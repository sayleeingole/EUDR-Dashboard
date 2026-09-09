# EUDR Palm Risk Assessment Dashboard

A web app for reviewing evidence and legal requirements for EUDR (EU
Deforestation Regulation) palm-oil risk assessments, and tracking the
decisions made on them.

## What's in here

- A web app (built with FastAPI) — this is the actual dashboard people use.
- `core/` — the underlying logic (database, rules, exporting reports, etc.)
- `data/seeds/` — the starting data (rules, sections, sources) the app loads on first run.
- `docs/` — background notes on how the app is designed and why.

## How to install it

You need Python 3.11 or newer installed. Then, from this folder, run:

```bash
pip install -r requirements.txt
```

This installs everything the app needs.

## How to run it

```bash
uvicorn web.main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000` in a browser (or the server's address, if
hosted elsewhere).

## Settings you need to set before hosting this online

These are set as **environment variables** on the server — not written into
the code. If you skip these, the app will still run, but with settings meant
only for testing on one person's laptop, not for a real server:

| Variable | What it's for | What happens if you don't set it |
|---|---|---|
| `EUDR_ACCESS_PASSWORD` | The password visitors must enter to use the dashboard | **No password is required at all** — anyone with the link gets in. Must be set before going live. |
| `EUDR_SECRET_KEY` | A private key used to keep people securely logged in | Falls back to a fixed value that's the same for every install — fine for testing, not for production. Set it to any long random string. |
| `EUDR_DB_PATH` | Where the database file is saved | Defaults to `data/eudr.sqlite` inside this folder. On most hosting platforms, set this to point at a persistent storage location so data isn't lost when the app restarts. |

## Optional feature: AI chat and research assistant

The dashboard includes an AI chat bubble (to ask questions about a record)
and an AI-assisted research feature. Both work by calling a separate tool
called **Claude Code**, which needs to be installed and signed in on
whichever machine runs this app — it isn't bundled in the Python code above.

- If Claude Code **isn't** set up on the server, these two features will
  simply show a friendly "unavailable" message. Nothing else in the
  dashboard is affected.
- If you want these features working online, Claude Code needs to be
  installed on the server and given API access (an Anthropic API key is the
  usual way to do this on a server, since there's no browser to log in
  through).
