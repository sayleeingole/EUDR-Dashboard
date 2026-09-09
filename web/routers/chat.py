"""Floating chat widget — context comes from whatever's currently open in
the right-hand pane (a legal requirement or an evidence record), passed in
by the client (static/app.js reads it off the pane's data-* attributes).
The widget itself is context-agnostic: it just needs a label + text block
to hand to core.chatbot, so adding a third pane type later only means
extending _context() below, not touching the templates or JS."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from core import chatbot
from ..deps import current_actor, get_conn
from ..templates_env import templates

router = APIRouter(prefix="/chat")


def _context(conn, context_type, context_id):
    """Returns (label, text) for the prompt, or (None, None) if not found."""
    if context_type == "evidence":
        row = conn.execute("SELECT * FROM evidence WHERE id=?", (context_id,)).fetchone()
        if row is None:
            return None, None
        lines = [f"Section: {row['section_code']}", f"Claim: {row['claim']}"]
        if row["source_name"]:
            lines.append(f"Source: {row['source_name']}")
        if row["publisher"]:
            lines.append(f"Publisher: {row['publisher']}")
        if row["url"]:
            lines.append(f"URL: {row['url']}")
        if row["notes"]:
            lines.append(f"Reviewer notes on this record: {row['notes']}")
        return row["claim"][:80], "\n".join(lines)

    if context_type == "requirement":
        row = conn.execute("SELECT * FROM legal_requirements WHERE id=?",
                           (context_id,)).fetchone()
        if row is None:
            return None, None
        lines = [f"Legal area: {row['area_code']}",
                f"Reference law: {row['reference_law'] or '(untitled)'}",
                f"What the law says: {row['requirement']}"]
        if row["provision"]:
            lines.append(f"Provision/context: {row['provision']}")
        if row["authority"]:
            lines.append(f"Issuing authority: {row['authority']}")
        if row["applicability"]:
            lines.append(f"Applies to: {row['applicability']}")
        if row["is_mandatory"]:
            cond = f" ({row['mandatory_condition']})" if row["mandatory_condition"] else ""
            lines.append(f"Mandatory: {row['is_mandatory']}{cond}")
        label = row["reference_law"] or (row["requirement"] or "")[:80]
        return label, "\n".join(lines)

    return None, None


def _key(context_type, context_id):
    return f"{context_type}:{context_id}"


@router.post("/ask")
def ask(request: Request, context_type: str = Form(...), context_id: int = Form(...),
       question: str = Form(...), conn=Depends(get_conn),
       actor: str = Depends(current_actor)):
    label, text = _context(conn, context_type, context_id)
    if label is None:
        raise HTTPException(status_code=404)
    key = _key(context_type, context_id)
    try:
        chatbot.ask(key, label, text, question, actor)
    except ValueError:
        pass  # surfaced via chat.error below — no question lost, nothing to retry blindly
    return templates.TemplateResponse(request, "partials/chat_widget_body.html", {
        "request": request, "chat": chatbot.state(key), "context_label": label,
        "context_type": context_type, "context_id": context_id,
    })


@router.get("/status")
def status(request: Request, context_type: str, context_id: int,
          conn=Depends(get_conn), actor: str = Depends(current_actor)):
    label, _ = _context(conn, context_type, context_id)
    if label is None:
        raise HTTPException(status_code=404)
    key = _key(context_type, context_id)
    return templates.TemplateResponse(request, "partials/chat_widget_body.html", {
        "request": request, "chat": chatbot.state(key), "context_label": label,
        "context_type": context_type, "context_id": context_id,
    })


@router.post("/clear")
def clear(request: Request, context_type: str = Form(...), context_id: int = Form(...),
         conn=Depends(get_conn), actor: str = Depends(current_actor)):
    label, _ = _context(conn, context_type, context_id)
    if label is None:
        raise HTTPException(status_code=404)
    chatbot.clear(_key(context_type, context_id))
    return templates.TemplateResponse(request, "partials/chat_widget_body.html", {
        "request": request, "chat": chatbot.state(_key(context_type, context_id)),
        "context_label": label, "context_type": context_type, "context_id": context_id,
    })
