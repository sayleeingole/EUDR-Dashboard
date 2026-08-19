import json
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from core import db as db_module
from core import researcher
from core.legal_parse import parse_legacy

from ..common import base_context, with_flash
from ..deps import current_actor, get_conn
from ..templates_env import templates

router = APIRouter(prefix="/legal")


def _display_row(r):
    """Structured fields win when present (new research runs / manual entry);
    otherwise best-effort parse the old free-text blob at display time. Each
    field falls back independently — e.g. a legacy row that's since been
    refined has a real confirmed `verification_docs` even though it has no
    `req_type`, and that confirmed value must win over a parsed guess."""
    d = dict(r)
    docs = json.loads(r["verification_docs"]) if r["verification_docs"] else None
    parsed = None
    if not r["req_type"]:
        parsed = parse_legacy(r["requirement"], r["provision"] or "")

    if r["req_type"]:
        d["req_type"] = r["req_type"]
        d["explanation"] = r["requirement"]
        d["context"] = r["provision"] or ""
    else:
        d["req_type"] = parsed["req_type"]
        d["explanation"] = parsed["explanation"]
        d["context"] = parsed["context"]
    d["authority"] = r["authority"] or (parsed["authority"] if parsed else None)
    d["docs"] = docs if docs is not None else (parsed["verification_docs"] if parsed else [])
    d["parsed"] = parsed is not None
    return d


def _legal_url(country_name, req_id=None):
    params = {"country": country_name}
    if req_id:
        params["req"] = req_id
    return "/legal?" + urlencode(params)


def _load_rows(conn, cycle_id, country_id):
    """All requirements for the scope, ordered by area then id, each decorated
    with display fields plus prev/next ids so the reading pane can move on."""
    all_reqs = db_module.get_requirements(conn, cycle_id, country_id)
    rows = [_display_row(r) for r in all_reqs]
    for i, r in enumerate(rows):
        r["prev_id"] = rows[i - 1]["id"] if i > 0 else None
        r["next_id"] = rows[i + 1]["id"] if i + 1 < len(rows) else None
        r["pos"] = i + 1
    return rows


def _pane_context(rows, req_id, country_name):
    """The reading pane needs its requirement plus where it sits in the list
    (`n of N` inside its area) and where Accept/Reject should land afterwards
    (the next requirement, so the reviewer keeps flowing down the list)."""
    r = next((x for x in rows if x["id"] == req_id), None)
    if r is None:
        return None
    area_rows = [x for x in rows if x["area_code"] == r["area_code"]]
    return {
        "r": r,
        "area_pos": area_rows.index(r) + 1,
        "area_total": len(area_rows),
        "after_url": _legal_url(country_name, r["next_id"] or r["id"]),
        "self_url": _legal_url(country_name, r["id"]),
    }


@router.get("")
def legal_view(request: Request, country: str | None = None, region: str | None = None,
               req: int | None = None,
               conn=Depends(get_conn), actor: str = Depends(current_actor)):
    ctx = base_context(conn, request, actor, country, region, "legal")
    cycle, sel_country = ctx["cycle"], ctx["sel_country"]
    areas = db_module.get_legal_areas(conn)
    ctx["areas"] = areas
    ctx["claude_ok"] = researcher.claude_available()
    if not cycle or not sel_country:
        ctx.update({"groups": [], "n_cand": 0, "n_rel": 0, "n_total": 0,
                    "baseline": [], "pane": None, "pending_batches": [],
                    "consolidatable": False, "research_counts": {}})
        return templates.TemplateResponse(request, "views/legal.html", ctx)
    ctx["pending_batches"] = researcher.pending_batches(sel_country["name"], run_type="legal")
    ctx["research_counts"] = db_module.evidence_counts_by_code(
        conn, cycle["id"], sel_country["id"], ctx["region_id"])

    area_approved = {a["code"]: db_module.evidence_counts(
        conn, cycle["id"], sel_country["id"], ctx["region_id"], a["code"]
    ).get("approved", 0) for a in areas}
    ctx["consolidatable"] = any(n > 1 for n in area_approved.values())

    rows = _load_rows(conn, cycle["id"], sel_country["id"])
    n_cand = sum(1 for r in rows if r["relevance"] == "candidate")
    n_rel = sum(1 for r in rows if r["relevance"] == "relevant")

    # Group by legal area, preserving A1..A7 order and including titles so the
    # list reads "A1 · Land use rights · 23 · 8 to refine".
    title_by_code = {a["code"]: a["title"] for a in areas}
    groups = []
    for r in rows:
        if not groups or groups[-1]["code"] != r["area_code"]:
            groups.append({"code": r["area_code"],
                           "title": title_by_code.get(r["area_code"], ""),
                           "rows": [], "n_cand": 0, "n_rel": 0})
        groups[-1]["rows"].append(r)
        if r["relevance"] == "candidate":
            groups[-1]["n_cand"] += 1
        elif r["relevance"] == "relevant":
            groups[-1]["n_rel"] += 1

    # Which requirement opens in the pane: the one asked for, else the first
    # still-to-refine one, else the first row.
    selected_id = req if req and any(r["id"] == req for r in rows) else None
    if selected_id is None:
        first_cand = next((r for r in rows if r["relevance"] == "candidate"), None)
        selected_id = (first_cand or (rows[0] if rows else None) or {}).get("id")

    baseline = {}
    for r in rows:
        if r["relevance"] == "relevant" and r["verification_docs"]:
            for d in json.loads(r["verification_docs"]):
                baseline.setdefault(d, []).append(f"{r['area_code']}#{r['id']}")

    ctx.update({
        "groups": groups, "n_cand": n_cand, "n_rel": n_rel,
        "n_total": len(rows), "baseline": sorted(baseline.items()),
        "selected_id": selected_id,
        "pane": _pane_context(rows, selected_id, sel_country["name"]) if selected_id else None,
    })
    return templates.TemplateResponse(request, "views/legal.html", ctx)


@router.get("/requirement/{req_id}/pane")
def requirement_pane(req_id: int, request: Request, country: str | None = None,
                     conn=Depends(get_conn), actor: str = Depends(current_actor)):
    """htmx target: just the reading pane for one requirement, swapped into
    the right-hand column when a row on the left is selected."""
    ctx = base_context(conn, request, actor, country, None, "legal")
    cycle, sel_country = ctx["cycle"], ctx["sel_country"]
    if not cycle or not sel_country:
        raise HTTPException(status_code=404)
    rows = _load_rows(conn, cycle["id"], sel_country["id"])
    pane = _pane_context(rows, req_id, sel_country["name"])
    if pane is None:
        raise HTTPException(status_code=404)
    ctx["pane"] = pane
    ctx["areas"] = db_module.get_legal_areas(conn)
    return templates.TemplateResponse(request, "partials/requirement_pane.html", ctx)


@router.post("/consolidate-all")
def consolidate_all(request: Request, cycle_id: int = Form(...),
                    country_id: int = Form(...), region_id: str = Form(""),
                    nxt: str = Form("/legal", alias="next"),
                    conn=Depends(get_conn), actor: str = Depends(current_actor)):
    region_id_val = int(region_id) if region_id else None
    areas_hit = 0
    duplicates_total = 0
    for a in db_module.get_legal_areas(conn):
        counts = db_module.evidence_counts(conn, cycle_id, country_id, region_id_val, a["code"])
        if counts.get("approved", 0) <= 1:
            continue
        n = db_module.consolidate_duplicates(conn, cycle_id, country_id, a["code"], actor)
        if n:
            areas_hit += 1
            duplicates_total += n
    if duplicates_total:
        msg = f"{duplicates_total} duplicate(s) superseded across {areas_hit} area(s)."
    else:
        msg = "No duplicates found."
    return RedirectResponse(with_flash(nxt, ok=msg), status_code=303)


@router.post("/requirement/{req_id}/reopen")
def reopen_requirement(req_id: int, request: Request, reason: str = Form(...),
                       nxt: str = Form("/legal", alias="next"),
                       conn=Depends(get_conn), actor: str = Depends(current_actor)):
    try:
        db_module.reopen_requirement(conn, req_id, reason, actor)
    except ValueError as err:
        return RedirectResponse(with_flash(nxt, error=str(err)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Requirement reopened for re-decision."),
                            status_code=303)


@router.post("/requirement/{req_id}/move-area")
def move_requirement_area(req_id: int, request: Request, area_code: str = Form(...),
                          nxt: str = Form("/legal", alias="next"),
                          conn=Depends(get_conn), actor: str = Depends(current_actor)):
    try:
        db_module.move_requirement_area(conn, req_id, area_code, actor)
    except ValueError as err:
        return RedirectResponse(with_flash(nxt, error=str(err)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok=f"Moved to {area_code}."), status_code=303)


@router.post("/requirement/{req_id}/refine")
def refine_requirement(req_id: int, request: Request, relevance: str = Form(...),
                       reason: str = Form(""), docs: str = Form(""),
                       authority: str = Form(""),
                       reference_law: str = Form(""),
                       applicability: str = Form(""),
                       supply_chain_node: list[str] = Form([]),
                       is_mandatory: str = Form(""),
                       mandatory_condition: str = Form(""),
                       alt_document: str = Form(""),
                       nxt: str = Form("/legal", alias="next"),
                       back: str = Form("", alias="self"),
                       conn=Depends(get_conn), actor: str = Depends(current_actor)):
    """`next` is where to go on success (the following requirement, so the
    reviewer keeps flowing); `self` is where to go on a validation error (this
    same requirement, so they can fix and resubmit)."""
    doc_list = [d.strip() for d in docs.split(",") if d.strip()] if relevance == "relevant" else None
    node_str = ",".join(supply_chain_node) if supply_chain_node else ""
    try:
        db_module.refine_requirement(conn, req_id, relevance, reason, doc_list, actor,
                                     authority=authority, reference_law=reference_law,
                                     applicability=applicability,
                                     supply_chain_node=node_str,
                                     is_mandatory=is_mandatory,
                                     alt_document=alt_document,
                                     mandatory_condition=mandatory_condition)
    except ValueError as err:
        return RedirectResponse(with_flash(back or nxt, error=str(err)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Requirement refined."), status_code=303)
