"""Overview screen (08 §4.2) — the landing page that answers "how far along
am I", absent from the original Streamlit app entirely. Read-only aggregation
over data core/ already exposes; no new core/ logic."""

from fastapi import APIRouter, Depends, Request

from core import checklist as checklist_engine
from core import db as db_module
from core.palm_regions import regions_for
from core.source_type import source_mix, source_mix_segments

from ..common import base_context
from ..deps import current_actor, get_conn
from ..templates_env import templates

router = APIRouter(prefix="/overview")


@router.get("")
def overview_view(request: Request, country: str | None = None, region: str | None = None,
                  conn=Depends(get_conn), actor: str = Depends(current_actor)):
    ctx = base_context(conn, request, actor, country, region, "overview")
    cycle, sel_country, region_id = ctx["cycle"], ctx["sel_country"], ctx["region_id"]
    if not cycle or not sel_country:
        ctx.update({"tiles": [], "signed_count": 0, "total_sections": 0,
                    "total_requirements": 0, "refined_requirements": 0,
                    "needs": [], "gaps": [], "recent": [], "palm_map": None,
                    "evidence_mix": [], "evidence_mix_total": 0})
        return templates.TemplateResponse(request, "views/overview.html", ctx)

    sections = db_module.get_sections(conn)
    tiles = []
    signed_count = 0
    draft_sections = []
    all_approved_ev = []
    for s in sections:
        a, level = checklist_engine.latest_signed(conn, cycle["id"], sel_country["id"],
                                                   region_id, s["code"])
        current = db_module.current_assessment(conn, cycle["id"], sel_country["id"],
                                                region_id, s["code"])
        if a:
            signed_count += 1
        if current and current["status"] == "draft":
            draft_sections.append(s)
        tiles.append({"s": s, "assessment": a, "current": current})
        all_approved_ev.extend(db_module.approved_evidence(
            conn, cycle["id"], sel_country["id"], region_id, s["code"]))

    evidence_mix = sorted(source_mix_segments(source_mix(all_approved_ev)),
                         key=lambda seg: -seg["count"])

    pending_all = db_module.pending_evidence(conn, cycle["id"], sel_country["id"])
    reqs = db_module.get_requirements(conn, cycle["id"], sel_country["id"])
    candidate_reqs = [r for r in reqs if r["relevance"] == "candidate"]
    refined_count = len(reqs) - len(candidate_reqs)

    gen_row, _items = checklist_engine.latest_generation(conn, cycle["id"],
                                                          sel_country["id"], region_id)
    stale = checklist_engine.is_stale(conn, gen_row, cycle["id"], sel_country["id"])

    qs = f"?country={sel_country['name']}" + (
        f"&region={ctx['sel_region']['name']}" if ctx["sel_region"] else "")

    needs = []
    if pending_all:
        needs.append({"label": f"{len(pending_all)} evidence record(s) pending review",
                      "href": f"/evidence{qs}"})
    if draft_sections:
        codes = ", ".join(s["code"] for s in draft_sections)
        needs.append({"label": f"{len(draft_sections)} section(s) drafted but not signed ({codes})",
                      "href": f"/risk{qs}"})
    if candidate_reqs:
        needs.append({"label": f"{len(candidate_reqs)} legal requirement(s) awaiting refinement",
                      "href": f"/legal{qs}"})
    if gen_row and stale:
        needs.append({"label": "Checklist is stale — ratings or requirements changed since generation",
                      "href": f"/checklist{qs}"})

    _is_complete, gaps = checklist_engine.completeness(
        conn, cycle["id"], sel_country["id"], region_id,
        ctx["sel_region"]["name"] if ctx["sel_region"] else None)

    recent = db_module.audit_rows(conn, limit=5, country=sel_country["name"])

    ctx.update({
        "tiles": tiles, "signed_count": signed_count, "total_sections": len(sections),
        "total_requirements": len(reqs), "refined_requirements": refined_count,
        "needs": needs, "gaps": gaps, "recent": recent,
        "palm_map": regions_for(sel_country["iso3"]),
        "evidence_mix": evidence_mix, "evidence_mix_total": len(all_approved_ev),
    })
    return templates.TemplateResponse(request, "views/overview.html", ctx)
