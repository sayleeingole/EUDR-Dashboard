from fastapi import APIRouter, Depends, Form, Request

from core import db as db_module
from core import importer, researcher, runmanager

from ..common import with_flash
from ..deps import current_actor, get_conn
from ..templates_env import templates
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/research")


def _scoped_runs(country, region):
    """Only the runs relevant to the country/region currently being viewed —
    otherwise a run started on one country's page shows up on every other
    page too, which reads as a bug (and is confusing with several open)."""
    return [r for r in runmanager.runs()
           if r["country"] == country and (r["region"] or "") == (region or "")]


@router.get("/status")
def status(request: Request, country: str = "", region: str = "",
          actor: str = Depends(current_actor)):
    return templates.TemplateResponse(request, "partials/run_banner.html",
                                      {"runs": _scoped_runs(country, region),
                                       "scope_country": country, "scope_region": region})


@router.post("/start")
def start(request: Request, run_type: str = Form(...), country: str = Form(...),
         region: str = Form(""), cycle_year: int = Form(...),
         item_codes: list[str] = Form([]), nxt: str = Form("/risk", alias="next"),
         conn=Depends(get_conn), actor: str = Depends(current_actor)):
    if run_type == "risk":
        pool = [{"code": s["code"], "title": s["title"], "scope": s["min_scope"]}
               for s in db_module.get_sections(conn)]
    else:
        pool = [{"code": a["code"], "title": a["title"], "scope": ""}
               for a in db_module.get_legal_areas(conn)]
    items = [i for i in pool if i["code"] in item_codes] or pool
    whitelist = [s for s in db_module.get_active_sources(conn)
                if s["applies_to"] == "all"
                or any(i["code"] in s["applies_to"].split(",") for i in items)]
    runmanager.start_run(run_type, country, region or None, cycle_year, items,
                         whitelist, actor)
    return RedirectResponse(with_flash(nxt, ok="Research started in the background."),
                            status_code=303)


@router.post("/{run_id}/dismiss")
def dismiss(run_id: int, request: Request, country: str = Form(""), region: str = Form(""),
           actor: str = Depends(current_actor)):
    runmanager.dismiss(run_id)
    return templates.TemplateResponse(request, "partials/run_banner.html",
                                      {"runs": _scoped_runs(country, region),
                                       "scope_country": country, "scope_region": region})


@router.post("/import/{filename}")
def import_batch_route(filename: str, request: Request,
                       nxt: str = Form("/risk", alias="next"),
                       conn=Depends(get_conn), actor: str = Depends(current_actor)):
    path = researcher.RESEARCH_DIR / filename
    try:
        summary = importer.import_batch(conn, path, actor)
        ok = f"Imported {summary['evidence']} records."
        if summary["gov_whitelisted"]:
            ok += f" {summary['gov_whitelisted']} government/ministry source(s) auto-trusted."
        return RedirectResponse(with_flash(nxt, ok=ok), status_code=303)
    except Exception as err:
        return RedirectResponse(with_flash(nxt, error=f"Import failed: {err}"),
                                status_code=303)
