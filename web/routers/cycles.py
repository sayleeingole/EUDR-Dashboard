from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from core import db as db_module

from ..common import base_context, with_flash
from ..deps import current_actor, get_conn
from ..templates_env import templates

router = APIRouter(prefix="/cycles")


@router.post("/open")
def open_cycle(request: Request, year: int = Form(...), next: str = Form("/risk"),
              conn=Depends(get_conn), actor: str = Depends(current_actor)):
    try:
        db_module.open_cycle(conn, year, actor)
    except ValueError as err:
        return RedirectResponse(with_flash(next, error=str(err)), status_code=303)
    return RedirectResponse(next, status_code=303)


@router.post("/close")
def close_cycle(request: Request, cycle_id: int = Form(...), next: str = Form("/risk"),
                conn=Depends(get_conn), actor: str = Depends(current_actor)):
    try:
        db_module.close_cycle(conn, cycle_id, actor)
    except ValueError as err:
        return RedirectResponse(with_flash(next, error=str(err)), status_code=303)
    return RedirectResponse(next, status_code=303)


@router.post("/rollforward")
def rollforward(request: Request, from_cycle_id: int = Form(...),
                to_cycle_id: int = Form(...), next: str = Form("/risk"),
                conn=Depends(get_conn), actor: str = Depends(current_actor)):
    try:
        result = db_module.rollforward(conn, from_cycle_id, to_cycle_id, actor)
    except ValueError as err:
        return RedirectResponse(with_flash(next, error=str(err)), status_code=303)
    ok = (f"Rolled forward: {result['evidence']} evidence, "
          f"{result['assessments']} assessments to reverify, "
          f"{result['requirements']} legal requirements to reconfirm, "
          f"{result['narrative_drafts']} narrative drafts.")
    return RedirectResponse(with_flash(next, ok=ok), status_code=303)


@router.post("/country")
def add_country(request: Request, name: str = Form(""), iso3: str = Form(""),
                regions: str = Form(""), next: str = Form("/risk"), conn=Depends(get_conn),
                actor: str = Depends(current_actor)):
    if name.strip() and iso3.strip():
        country_id = db_module.add_country(conn, name.strip(), iso3.strip().upper(), actor)
        for region_name in regions.split(","):
            region_name = region_name.strip()
            if region_name:
                db_module.add_region(conn, country_id, region_name, actor)
    return RedirectResponse(next, status_code=303)


@router.post("/region")
def add_region(request: Request, country_id: int = Form(...), name: str = Form(""),
               next: str = Form("/risk"), conn=Depends(get_conn),
               actor: str = Depends(current_actor)):
    if name.strip():
        db_module.add_region(conn, country_id, name.strip(), actor)
    return RedirectResponse(next, status_code=303)


@router.get("/delta")
def delta(request: Request, a: int, b: int, conn=Depends(get_conn),
          actor: str = Depends(current_actor)):
    cyc_a = next((c for c in db_module.get_cycles(conn) if c["year"] == a), None)
    cyc_b = next((c for c in db_module.get_cycles(conn) if c["year"] == b), None)
    rows = []
    if cyc_a and cyc_b:
        rows = db_module.year_over_year_delta(conn, cyc_b["id"], cyc_a["id"])
    ctx = base_context(conn, request, actor, request.query_params.get("country"),
                       request.query_params.get("region"), "risk")
    ctx.update({"delta_rows": rows, "year_a": a, "year_b": b})
    return templates.TemplateResponse(request, "views/delta.html", ctx)
