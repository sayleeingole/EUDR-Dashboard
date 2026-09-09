"""Evidence review — split view (grouped list + reading pane), same pattern
as /legal: the list gives an overview of the whole pending batch, the pane is
where you actually read and decide one record. Checkboxes on the list support
bulk approve for records that don't need a close look; the pane is for the
records that do."""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from core import db as db_module
from core.source_type import SOURCE_TYPE_LABELS

from ..common import base_context, with_flash
from ..deps import current_actor, get_conn
from ..templates_env import code_label, templates

router = APIRouter(prefix="/evidence")


def _queue(conn, cycle, sel_country):
    return db_module.pending_evidence(conn, cycle["id"], sel_country["id"])


def _ev_url(country_name, ev_id=None):
    params = {"country": country_name}
    if ev_id:
        params["ev"] = ev_id
    return "/evidence?" + urlencode(params)


def _section_rank(conn):
    """S1..S10 then A1..A7, in the fixed order they're defined — not the
    order records happen to appear in. Grouping by section only reads right
    if the groups themselves are always in the same order."""
    codes = ([s["code"] for s in db_module.get_sections(conn)]
            + [a["code"] for a in db_module.get_legal_areas(conn)])
    return {code: i for i, code in enumerate(codes)}


def _load_rows(conn, cycle, sel_country):
    """Pending queue, decorated with prev/next ids for the pane's J/K nav —
    same technique as legal.py's _load_rows. Sorted by canonical section
    order (then id within a section) so groups always appear in the same
    order regardless of which records a research run happened to add first."""
    rank = _section_rank(conn)
    rows = [dict(r) for r in _queue(conn, cycle, sel_country)]
    rows.sort(key=lambda r: (rank.get(r["section_code"], 999), r["id"]))
    for i, r in enumerate(rows):
        r["prev_id"] = rows[i - 1]["id"] if i > 0 else None
        r["next_id"] = rows[i + 1]["id"] if i + 1 < len(rows) else None
    return rows


def _pane_context(rows, ev_id, country_name):
    r = next((x for x in rows if x["id"] == ev_id), None)
    if r is None:
        return None
    return {"ev": r, "after_url": _ev_url(country_name, r["next_id"] or r["id"]),
           "self_url": _ev_url(country_name, r["id"])}


def _summary(rows):
    unlisted = sum(1 for r in rows if r["flag"] == "unlisted-source")
    dup = sum(1 for r in rows if r["flag"] == "possible-duplicate")
    low_conf = sum(1 for r in rows if r["confidence"] == "low")
    sections = sorted({r["section_code"] for r in rows})
    return {"total": len(rows), "unlisted": unlisted, "possible_duplicate": dup,
           "low_confidence": low_conf, "n_sections": len(sections)}


@router.get("")
def evidence_view(request: Request, country: str | None = None, region: str | None = None,
                  ev: int | None = None,
                  conn=Depends(get_conn), actor: str = Depends(current_actor)):
    ctx = base_context(conn, request, actor, country, region, "evidence")
    cycle, sel_country = ctx["cycle"], ctx["sel_country"]
    if not cycle or not sel_country:
        ctx.update({"groups": [], "summary": None, "pane": None})
        return templates.TemplateResponse(request, "views/evidence.html", ctx)

    rows = _load_rows(conn, cycle, sel_country)
    groups = []
    for r in rows:
        if not groups or groups[-1]["code"] != r["section_code"]:
            groups.append({"code": r["section_code"],
                           "label": code_label(r["section_code"]), "rows": []})
        groups[-1]["rows"].append(r)

    selected_id = ev if ev and any(r["id"] == ev for r in rows) else (rows[0]["id"] if rows else None)

    ctx.update({
        "groups": groups, "summary": _summary(rows), "selected_id": selected_id,
        "pane": _pane_context(rows, selected_id, sel_country["name"]) if selected_id else None,
        "batch_count": sum(1 for r in rows if r["flag"] is None),
        "list_url": _ev_url(sel_country["name"]),
        "sections": db_module.get_sections(conn),
        "areas": db_module.get_legal_areas(conn),
    })
    return templates.TemplateResponse(request, "views/evidence.html", ctx)


@router.get("/{evidence_id}/pane")
def evidence_pane(evidence_id: int, request: Request, country: str | None = None,
                  conn=Depends(get_conn), actor: str = Depends(current_actor)):
    ctx = base_context(conn, request, actor, country, None, "evidence")
    cycle, sel_country = ctx["cycle"], ctx["sel_country"]
    if not cycle or not sel_country:
        raise HTTPException(status_code=404)
    rows = _load_rows(conn, cycle, sel_country)
    pane = _pane_context(rows, evidence_id, sel_country["name"])
    if pane is None:
        raise HTTPException(status_code=404)
    ctx["pane"] = pane
    ctx["sections"] = db_module.get_sections(conn)
    ctx["areas"] = db_module.get_legal_areas(conn)
    return templates.TemplateResponse(request, "partials/evidence_pane.html", ctx)


@router.get("/table")
def evidence_table_redirect(request: Request):
    """Old two-screen layout (one-by-one queue + separate bulk table) merged
    into a single split view at /evidence. Kept so bookmarks/links elsewhere
    in the app still land somewhere correct."""
    qs = request.url.query
    return RedirectResponse(url="/evidence" + (f"?{qs}" if qs else ""), status_code=307)


@router.post("/approve-selected")
def approve_selected(request: Request, ids: list[int] = Form([]),
                     nxt: str = Form("/evidence", alias="next"),
                     conn=Depends(get_conn), actor: str = Depends(current_actor)):
    n, trusted = 0, 0
    for evidence_id in ids:
        ev = conn.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
        if ev is None or ev["status"] != "pending":
            continue
        if ev["flag"] == "unlisted-source":
            try:
                db_module.approve_source(conn, evidence_id, ev["section_code"],
                                         "bulk-approved from evidence list", actor)
                trusted += 1
            except ValueError:
                continue
        db_module.decide_evidence(conn, evidence_id, "approved", None, actor)
        n += 1
    if n == 0:
        return RedirectResponse(with_flash(nxt, error="Nothing selected to approve."),
                                status_code=303)
    msg = f"Approved {n} record(s)."
    if trusted:
        msg += f" {trusted} previously-untrusted source(s) now trusted."
    return RedirectResponse(with_flash(nxt, ok=msg), status_code=303)


@router.post("/{evidence_id}/decide")
def decide(evidence_id: int, request: Request, decision: str = Form(...),
          reason: str = Form(None), reject_other: str = Form(None),
          nxt: str = Form("/evidence", alias="next"),
          back: str = Form("", alias="self"),
          conn=Depends(get_conn), actor: str = Depends(current_actor)):
    final_reason = (reject_other or "").strip() if reason == "__other__" else reason
    try:
        db_module.decide_evidence(conn, evidence_id, decision, final_reason, actor)
    except ValueError as err:
        return RedirectResponse(with_flash(back or nxt, error=str(err)), status_code=303)
    if decision == "approved":
        return RedirectResponse(with_flash(nxt, ok="Approved.", undo=evidence_id),
                                status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Rejected."), status_code=303)


@router.post("/{evidence_id}/move-section")
def move_section(evidence_id: int, request: Request, section_code: str = Form(...),
                 nxt: str = Form("/evidence", alias="next"),
                 conn=Depends(get_conn), actor: str = Depends(current_actor)):
    try:
        db_module.move_evidence_section(conn, evidence_id, section_code, actor)
    except ValueError as err:
        return RedirectResponse(with_flash(nxt, error=str(err)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok=f"Moved to {section_code}."),
                            status_code=303)


@router.post("/{evidence_id}/undo")
def undo(evidence_id: int, request: Request, nxt: str = Form("/evidence", alias="next"),
        conn=Depends(get_conn), actor: str = Depends(current_actor)):
    try:
        db_module.undo_decision(conn, evidence_id, actor)
    except ValueError as err:
        return RedirectResponse(with_flash(nxt, error=str(err)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Undone — back in the queue."),
                            status_code=303)


@router.post("/{evidence_id}/approve-source")
def approve_source(evidence_id: int, request: Request, reason: str = Form(""),
                   trust_scope: str = Form("article"),
                   nxt: str = Form("/evidence", alias="next"),
                   back: str = Form("", alias="self"),
                   conn=Depends(get_conn), actor: str = Depends(current_actor)):
    ev = conn.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    if not reason.strip():
        return RedirectResponse(with_flash(back or nxt, error="Reason required."),
                                status_code=303)
    if trust_scope not in ("website", "article"):
        trust_scope = "article"
    try:
        db_module.approve_source(conn, evidence_id, ev["section_code"], reason.strip(),
                                 actor, trust_scope=trust_scope)
        db_module.decide_evidence(conn, evidence_id, "approved", None, actor)
    except ValueError as err:
        return RedirectResponse(with_flash(back or nxt, error=str(err)), status_code=303)
    msg = ("Website trusted and record approved." if trust_scope == "website"
          else "This article's source approved and record approved.")
    return RedirectResponse(with_flash(nxt, ok=msg, undo=evidence_id), status_code=303)


@router.post("/batch-approve")
def batch_approve(request: Request, country: str = Form(...), region: str = Form(""),
                  nxt: str = Form("/evidence", alias="next"),
                  conn=Depends(get_conn), actor: str = Depends(current_actor)):
    cycle = db_module.get_open_cycle(conn)
    countries = db_module.get_countries(conn)
    sel_country = next((c for c in countries if c["name"] == country), None)
    if not cycle or not sel_country:
        return RedirectResponse(with_flash(nxt, error="No open cycle or country."),
                                status_code=303)
    queue = _queue(conn, cycle, sel_country)
    n = 0
    for e in queue:
        if e["flag"] is None:
            db_module.decide_evidence(conn, e["id"], "approved", None, actor)
            n += 1
    return RedirectResponse(with_flash(nxt, ok=f"Approved {n} unflagged record(s)."),
                            status_code=303)
