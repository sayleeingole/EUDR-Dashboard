"""Settings page: cycle administration + country/region management. A few
times a year, not a daily action — deliberately off the main assessment path
(08 §4.1). Write logic stays in web/routers/cycles.py; this router only
assembles the page."""

from fastapi import APIRouter, Depends, Request

from ..common import base_context
from ..deps import current_actor, get_conn
from ..templates_env import templates

router = APIRouter(prefix="/settings")


@router.get("")
def settings_view(request: Request, conn=Depends(get_conn),
                  actor: str = Depends(current_actor)):
    ctx = base_context(conn, request, actor, None, None, "settings")
    return templates.TemplateResponse(request, "views/settings.html", ctx)
