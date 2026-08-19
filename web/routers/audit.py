from fastapi import APIRouter, Depends, Request

from core import db as db_module

from ..common import base_context
from ..deps import current_actor, get_conn
from ..templates_env import templates

router = APIRouter(prefix="/audit")


@router.get("")
def audit_view(request: Request, f_country: str = "All", f_event: str = "All",
              conn=Depends(get_conn), actor: str = Depends(current_actor)):
    ctx = base_context(conn, request, actor, None, None, "audit")
    country_names = [c["name"] for c in ctx["countries"]]
    events = sorted({r["event_type"] for r in db_module.audit_rows(conn, limit=1000)})
    rows = db_module.audit_rows(
        conn, limit=500, country=None if f_country == "All" else f_country,
        event_type=None if f_event == "All" else f_event)
    ctx.update({
        "country_names": country_names, "events": events, "rows": rows,
        "f_country": f_country, "f_event": f_event,
    })
    return templates.TemplateResponse(request, "views/audit.html", ctx)
