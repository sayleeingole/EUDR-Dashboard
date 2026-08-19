"""EUDR palm risk assessment — FastAPI port of app.py (Streamlit).

Run with:  uvicorn web.main:app --reload --port 8000 --workers 1

Pinned to a single worker deliberately (08 §2.2 / 08a §1.4): runmanager.py
keeps research-run state in an in-process dict, which only one worker can
see. Move run state into SQLite before ever running >1 worker.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from core import db as db_module

from .auth import NotAuthenticated
from .routers import (audit, auth_router, checklist, cycles, evidence, legal,
                      overview, research, risk, settings, sources)

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="EUDR country risk assessment")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def _startup():
    conn = db_module.init_db(actor="system")
    conn.close()


@app.exception_handler(NotAuthenticated)
def _not_authenticated(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)


app.include_router(auth_router.router)
app.include_router(overview.router)
app.include_router(evidence.router)
app.include_router(risk.router)
app.include_router(legal.router)
app.include_router(checklist.router)
app.include_router(audit.router)
app.include_router(cycles.router)
app.include_router(settings.router)
app.include_router(sources.router)
app.include_router(research.router)


@app.get("/")
def root():
    return RedirectResponse(url="/overview")
