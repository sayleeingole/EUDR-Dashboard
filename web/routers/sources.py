"""Trusted sources page (Settings) — see and manage the source whitelist
directly, instead of only through the evidence queue's approve-source step.
A domain-level entry trusts every future article from that website; a
name-only entry (the historical default, saved from the queue) only matches
one article title. This page lets a name-only entry get a domain attached,
lets a source be added ahead of any evidence citing it, and offers a small
curated list of civil-society/academic sources the reviewer can accept."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from core import db as db_module
from core.source_candidates import CANDIDATE_SOURCES

from ..common import base_context, with_flash
from ..deps import current_actor, get_conn
from ..templates_env import templates

router = APIRouter(prefix="/settings/sources")


@router.get("")
def sources_view(request: Request, conn=Depends(get_conn),
                 actor: str = Depends(current_actor)):
    ctx = base_context(conn, request, actor, None, None, "settings")
    sources = db_module.list_sources(conn)
    active = [s for s in sources if s["status"] == "active"]
    retired = [s for s in sources if s["status"] == "retired"]
    no_domain = [s for s in active if not s["url_pattern"]]

    known = {(s["url_pattern"] or "").lower() for s in sources if s["url_pattern"]}
    known_names = {s["name"].lower() for s in sources}
    candidates = [c for c in CANDIDATE_SOURCES
                 if c["url_pattern"].lower() not in known
                 and c["name"].lower() not in known_names]

    ctx.update({"active": active, "retired": retired, "no_domain": no_domain,
               "candidates": candidates, "n_total": len(active)})
    return templates.TemplateResponse(request, "views/sources.html", ctx)


@router.post("/add")
def add_source(request: Request, name: str = Form(""), url_pattern: str = Form(""),
              applies_to: str = Form("all"), publisher: str = Form(""),
              reason: str = Form(""),
              nxt: str = Form("/settings/sources", alias="next"),
              conn=Depends(get_conn), actor: str = Depends(current_actor)):
    try:
        db_module.add_source(conn, name, url_pattern, applies_to, actor,
                             publisher=publisher, reason=reason)
    except ValueError as err:
        return with_flash_redirect(nxt, error=str(err))
    return with_flash_redirect(nxt, ok=f"Trusted: {name or url_pattern}.")


@router.post("/{source_id}/domain")
def set_domain(source_id: int, request: Request, url_pattern: str = Form(...),
               nxt: str = Form("/settings/sources", alias="next"),
               conn=Depends(get_conn), actor: str = Depends(current_actor)):
    try:
        domain = db_module.set_source_domain(conn, source_id, url_pattern, actor)
    except ValueError as err:
        return with_flash_redirect(nxt, error=str(err))
    return with_flash_redirect(nxt, ok=f"Now trusts the whole website ({domain}).")


@router.post("/{source_id}/retire")
def retire_source(source_id: int, request: Request, reason: str = Form(...),
                  nxt: str = Form("/settings/sources", alias="next"),
                  conn=Depends(get_conn), actor: str = Depends(current_actor)):
    try:
        db_module.set_source_status(conn, source_id, "retired", reason, actor)
    except ValueError as err:
        return with_flash_redirect(nxt, error=str(err))
    return with_flash_redirect(nxt, ok="Source retired.")


@router.post("/{source_id}/reactivate")
def reactivate_source(source_id: int, request: Request,
                      nxt: str = Form("/settings/sources", alias="next"),
                      conn=Depends(get_conn), actor: str = Depends(current_actor)):
    db_module.set_source_status(conn, source_id, "active", "reactivated", actor)
    return with_flash_redirect(nxt, ok="Source reactivated.")


def with_flash_redirect(url, **kw):
    return RedirectResponse(with_flash(url, **kw), status_code=303)
