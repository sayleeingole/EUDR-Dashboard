from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

import hmac

from ..auth import ACCESS_PASSWORD, COOKIE_NAME, MAX_AGE, sign_actor
from ..templates_env import templates

router = APIRouter()


@router.get("/login")
def login_form(request: Request, next: str = "/overview"):
    return templates.TemplateResponse(
        request, "views/login.html",
        {"next": next, "error": None, "needs_password": bool(ACCESS_PASSWORD)})


@router.post("/login")
def login_submit(request: Request, name: str = Form(...), next: str = Form("/overview"),
                 password: str = Form("")):
    name = name.strip()
    ctx = {"next": next, "needs_password": bool(ACCESS_PASSWORD)}
    if not name:
        return templates.TemplateResponse(
            request, "views/login.html", {**ctx, "error": "Enter your name."})
    if ACCESS_PASSWORD and not hmac.compare_digest(password, ACCESS_PASSWORD):
        return templates.TemplateResponse(
            request, "views/login.html", {**ctx, "error": "Incorrect access password."})
    resp = RedirectResponse(url=next or "/overview", status_code=303)
    resp.set_cookie(COOKIE_NAME, sign_actor(name), max_age=MAX_AGE,
                    httponly=True, samesite="lax")
    return resp


@router.post("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp
