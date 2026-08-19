"""Helpers shared across routers: the header/scope-bar context every view
needs, redirect-with-flash-message, and evidence-queue splitting."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core import db as db_module

from .deps import scope_context


def with_flash(url: str, **kwargs) -> str:
    parts = urlsplit(str(url))
    q = dict(parse_qsl(parts.query))
    q.update({k: v for k, v in kwargs.items() if v is not None})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


def base_context(conn, request, actor, country, region, active_view):
    """Everything base.html / scope_bar.html need, plus whatever the caller
    layers on top for the specific view."""
    cycle = db_module.get_open_cycle(conn)
    all_cycles = db_module.get_cycles(conn)
    closed_cycles = [c for c in all_cycles if c["status"] == "closed"]
    next_cycle_year = (max((c["year"] for c in all_cycles), default=cycle["year"]
                           if cycle else 2025) + 1)
    scope = scope_context(conn, country, region)
    pending_count = 0
    legal_total = legal_refined = 0
    if cycle and scope["sel_country"]:
        pending_count = len(db_module.pending_evidence(conn, cycle["id"],
                                                        scope["sel_country"]["id"]))
        legal_reqs = db_module.get_requirements(conn, cycle["id"], scope["sel_country"]["id"])
        legal_total = len(legal_reqs)
        legal_refined = sum(1 for r in legal_reqs if r["relevance"] != "candidate")
    return {
        "request": request, "actor": actor, "active_view": active_view,
        "cycle": cycle, "all_cycles": all_cycles, "closed_cycles": closed_cycles,
        "next_cycle_year": next_cycle_year, "pending_count": pending_count,
        "legal_total": legal_total, "legal_refined": legal_refined,
        **scope,
    }


def split_pending(pending_all):
    risk = [e for e in pending_all if e["section_code"].startswith("S")]
    legal = [e for e in pending_all if e["section_code"].startswith("A")]
    return risk, legal


def pending_for_section(rows, code):
    return [e for e in rows if e["section_code"] == code]
