import json
import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, RedirectResponse

from core import checklist as checklist_engine
from core import db as db_module
from core import exporter

from ..common import base_context, with_flash
from ..deps import current_actor, get_conn
from ..templates_env import templates

router = APIRouter(prefix="/checklist")


def _group_sort_key(name):
    """Domain order, not alphabetical: Universal, then legal-baseline areas
    (A1, A2, ...), then risk sections (S1, S2, ...) — plain string sort would
    put 'Risk S10' before 'Risk S3' since '1' < '3' as characters."""
    if name.startswith("Universal"):
        return (0, 0, name)
    m = re.match(r"Area A(\d+)", name)
    if m:
        return (1, int(m.group(1)), name)
    m = re.match(r"Risk S(\d+)", name)
    if m:
        return (2, int(m.group(1)), name)
    return (3, 0, name)


def _cluster_rows(items):
    """Fold consecutive items that share an alt_group into one row unit —
    they're alternative documents (any ONE satisfies the requirement), not
    separate independently-required items. Order is preserved; a group id
    reappearing non-consecutively (shouldn't happen — generate() keeps a
    requirement's docs together) still gets a fresh cluster rather than
    silently merging with an earlier one."""
    rows = []
    for it in items:
        grp = it.get("alt_group")
        if grp and rows and rows[-1]["kind"] == "group" and rows[-1]["alt_group"] == grp:
            rows[-1]["docs"].append(it)
        elif grp:
            rows.append({"kind": "group", "alt_group": grp, "docs": [it]})
        else:
            rows.append({"kind": "single", "docs": [it]})
    return rows


def _export_history():
    if not exporter.EXPORTS_DIR.exists():
        return []
    files = sorted(exporter.EXPORTS_DIR.glob("*"), key=lambda p: p.stat().st_mtime,
                   reverse=True)
    return [f.name for f in files][:30]


@router.get("")
def checklist_view(request: Request, country: str | None = None, region: str | None = None,
                   conn=Depends(get_conn), actor: str = Depends(current_actor)):
    ctx = base_context(conn, request, actor, country, region, "checklist")
    cycle, sel_country, region_id = ctx["cycle"], ctx["sel_country"], ctx["region_id"]
    ctx["export_history"] = _export_history()
    if not cycle or not sel_country:
        ctx.update({"is_complete": False, "gaps": [], "gen_row": None,
                    "gen_items": [], "stale": False, "grouped_items": [],
                    "changes": []})
        return templates.TemplateResponse(request, "views/checklist.html", ctx)

    is_complete, gaps = checklist_engine.completeness(
        conn, cycle["id"], sel_country["id"], region_id,
        ctx["sel_region"]["name"] if ctx["sel_region"] else None)
    gen_row, gen_items = checklist_engine.latest_generation(
        conn, cycle["id"], sel_country["id"], region_id)
    stale = checklist_engine.is_stale(conn, gen_row, cycle["id"], sel_country["id"])

    grouped, order = {}, []
    for it in gen_items:
        grp = it["grouping"] or "Other"
        if grp not in grouped:
            grouped[grp] = []
            order.append(grp)
        grouped[grp].append({**dict(it), "_justification": json.loads(it["justification"])})
    order.sort(key=_group_sort_key)
    grouped_items = [(g, _cluster_rows(grouped[g]), len(grouped[g])) for g in order]

    exclusions = db_module.get_checklist_exclusions(conn, sel_country["id"], region_id)
    renames = db_module.get_checklist_renames(conn, sel_country["id"], region_id)
    removed_additions = db_module.get_checklist_additions(conn, sel_country["id"], region_id,
                                                           status="removed")

    changes = (
        [{"kind": "excluded", "label": r["document_name"], "who": r["excluded_by"],
          "at": r["excluded_at"], "undo_action": f"/checklist/exclusion/{r['id']}/restore",
          "undo_label": "Restore"} for r in exclusions]
        + [{"kind": "renamed", "label": f"{r['original_name']} → {r['new_name']}",
            "who": r["renamed_by"], "at": r["renamed_at"],
            "undo_action": f"/checklist/rename/{r['id']}/revert",
            "undo_label": "Revert"} for r in renames]
        + [{"kind": "added then removed", "label": r["document_name"], "who": r["removed_by"],
            "at": r["removed_at"], "undo_action": f"/checklist/addition/{r['id']}/restore",
            "undo_label": "Restore"} for r in removed_additions]
    )
    changes.sort(key=lambda c: c["at"], reverse=True)

    ctx.update({
        "is_complete": is_complete, "gaps": gaps, "gen_row": gen_row,
        "gen_items": gen_items, "grouped_items": grouped_items, "stale": stale,
        "changes": changes,
    })
    return templates.TemplateResponse(request, "views/checklist.html", ctx)


@router.post("/generate")
def generate(request: Request, cycle_id: int = Form(...), country_id: int = Form(...),
            region_id: str = Form(""), region_name: str = Form(""),
            nxt: str = Form("/checklist", alias="next"), conn=Depends(get_conn),
            actor: str = Depends(current_actor)):
    region_id_val = int(region_id) if region_id else None
    gid, items_, final_, gaps_ = checklist_engine.generate(
        conn, cycle_id, country_id, region_id_val, region_name or None, actor)
    ok = f"Generated {len(items_)} items ({'final' if final_ else 'DRAFT'})."
    return RedirectResponse(with_flash(nxt, ok=ok), status_code=303)


@router.post("/item/{item_id}/notes")
def save_notes(item_id: int, request: Request, notes: str = Form(""),
               nxt: str = Form("/checklist", alias="next"), conn=Depends(get_conn),
               actor: str = Depends(current_actor)):
    try:
        db_module.set_checklist_item_notes(conn, item_id, notes, actor)
    except ValueError as e:
        return RedirectResponse(with_flash(nxt, error=str(e)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Remark saved."), status_code=303)


@router.post("/exclude")
def exclude_document(request: Request, country_id: int = Form(...),
                     region_id: str = Form(""), document_name: str = Form(...),
                     nxt: str = Form("/checklist", alias="next"), conn=Depends(get_conn),
                     actor: str = Depends(current_actor)):
    region_id_val = int(region_id) if region_id else None
    try:
        db_module.exclude_checklist_document(conn, country_id, region_id_val,
                                             document_name, actor)
    except ValueError as e:
        return RedirectResponse(with_flash(nxt, error=str(e)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok=f'Removed "{document_name}" from the checklist.'),
                            status_code=303)


@router.post("/exclusion/{exclusion_id}/restore")
def restore_document(exclusion_id: int, request: Request,
                     nxt: str = Form("/checklist", alias="next"), conn=Depends(get_conn),
                     actor: str = Depends(current_actor)):
    try:
        db_module.restore_checklist_document(conn, exclusion_id, actor)
    except ValueError as e:
        return RedirectResponse(with_flash(nxt, error=str(e)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Restored to the checklist."), status_code=303)


@router.post("/rename")
def rename_document(request: Request, country_id: int = Form(...),
                    region_id: str = Form(""), original_name: str = Form(...),
                    new_name: str = Form(...), nxt: str = Form("/checklist", alias="next"),
                    conn=Depends(get_conn), actor: str = Depends(current_actor)):
    region_id_val = int(region_id) if region_id else None
    try:
        db_module.rename_checklist_document(conn, country_id, region_id_val,
                                            original_name, new_name, actor)
    except ValueError as e:
        return RedirectResponse(with_flash(nxt, error=str(e)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Renamed."), status_code=303)


@router.post("/rename/{rename_id}/revert")
def revert_rename(rename_id: int, request: Request,
                  nxt: str = Form("/checklist", alias="next"), conn=Depends(get_conn),
                  actor: str = Depends(current_actor)):
    try:
        db_module.revert_checklist_rename(conn, rename_id, actor)
    except ValueError as e:
        return RedirectResponse(with_flash(nxt, error=str(e)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Reverted to the original name."), status_code=303)


@router.post("/add")
def add_document(request: Request, country_id: int = Form(...),
                 region_id: str = Form(""), document_name: str = Form(...),
                 grouping: str = Form(...), note: str = Form(""),
                 nxt: str = Form("/checklist", alias="next"), conn=Depends(get_conn),
                 actor: str = Depends(current_actor)):
    region_id_val = int(region_id) if region_id else None
    try:
        db_module.add_checklist_document(conn, country_id, region_id_val,
                                         document_name, grouping, note, actor)
    except ValueError as e:
        return RedirectResponse(with_flash(nxt, error=str(e)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok=f'Added "{document_name}".'), status_code=303)


@router.post("/addition/{addition_id}/remove")
def remove_addition(addition_id: int, request: Request,
                    nxt: str = Form("/checklist", alias="next"), conn=Depends(get_conn),
                    actor: str = Depends(current_actor)):
    try:
        db_module.remove_checklist_addition(conn, addition_id, actor)
    except ValueError as e:
        return RedirectResponse(with_flash(nxt, error=str(e)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Removed."), status_code=303)


@router.post("/addition/{addition_id}/restore")
def restore_addition(addition_id: int, request: Request,
                     nxt: str = Form("/checklist", alias="next"), conn=Depends(get_conn),
                     actor: str = Depends(current_actor)):
    try:
        db_module.restore_checklist_addition(conn, addition_id, actor)
    except ValueError as e:
        return RedirectResponse(with_flash(nxt, error=str(e)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Restored."), status_code=303)


@router.post("/addition/{addition_id}/note")
def save_addition_note(addition_id: int, request: Request, notes: str = Form(""),
                       nxt: str = Form("/checklist", alias="next"), conn=Depends(get_conn),
                       actor: str = Depends(current_actor)):
    try:
        db_module.set_checklist_addition_note(conn, addition_id, notes, actor)
    except ValueError as e:
        return RedirectResponse(with_flash(nxt, error=str(e)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Remark saved."), status_code=303)


@router.get("/export/{doctype}")
def export(doctype: str, request: Request, country: str, region: str = "",
          conn=Depends(get_conn), actor: str = Depends(current_actor)):
    cycle = db_module.get_open_cycle(conn)
    if not cycle:
        return RedirectResponse(with_flash("/checklist", error="No open cycle."),
                                status_code=303)
    countries = db_module.get_countries(conn)
    sel_country = next((c for c in countries if c["name"] == country), None)
    if sel_country is None:
        return RedirectResponse(with_flash("/checklist", error="Unknown country."),
                                status_code=303)
    regions = db_module.get_regions(conn, sel_country["id"])
    sel_region = next((r for r in regions if r["name"] == region), None) if region else None
    region_id = sel_region["id"] if sel_region else None

    if doctype == "risk":
        path, _final = exporter.risk_report_docx(conn, cycle, sel_country, sel_region, actor)
    elif doctype in ("checklist-docx", "checklist-xlsx", "checklist-docx-supplier"):
        gen_row, gen_items = checklist_engine.latest_generation(
            conn, cycle["id"], sel_country["id"], region_id)
        if not gen_row:
            return RedirectResponse(with_flash("/checklist", error="Generate a checklist first."),
                                    status_code=303)
        fn = {"checklist-docx": exporter.checklist_docx,
              "checklist-xlsx": exporter.checklist_xlsx,
              "checklist-docx-supplier": exporter.checklist_docx_supplier}[doctype]
        path = fn(conn, cycle, sel_country, sel_region, gen_row, gen_items, actor)
    elif doctype == "audit":
        path = exporter.audit_xlsx(conn, cycle["year"], country, actor)
    else:
        return RedirectResponse(with_flash("/checklist", error="Unknown export type."),
                                status_code=303)
    return FileResponse(path, filename=path.name,
                        media_type="application/octet-stream")


@router.get("/exports/{filename}")
def download_past_export(filename: str, actor: str = Depends(current_actor)):
    path = exporter.EXPORTS_DIR / filename
    if not path.exists() or path.parent.resolve() != exporter.EXPORTS_DIR.resolve():
        return RedirectResponse(with_flash("/checklist", error="File not found."),
                                status_code=303)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
