"""Shared FastAPI dependencies: one DB connection per request (08 §2.3 — not
a global cached connection), and the operator-identity seam (08 §2.1 / 08a
§1.3)."""

from fastapi import Request

from core import db as db_module

from .auth import NotAuthenticated, read_actor


def get_conn():
    conn = db_module.get_conn()
    try:
        yield conn
    finally:
        conn.close()


def current_actor(request: Request) -> str:
    actor = read_actor(request)
    if not actor:
        raise NotAuthenticated()
    return actor


def scope_context(conn, country: str | None, region: str | None):
    """Resolve the country/region scope shared by every view, mirroring the
    old sidebar's country radio + region select."""
    countries = db_module.get_countries(conn)
    if not countries:
        return {
            "countries": [], "sel_country": None, "regions": [],
            "sel_region": None, "region_id": None, "scope_label": "",
        }
    sel_country = next((c for c in countries if c["name"] == country),
                       countries[0])
    regions = db_module.get_regions(conn, sel_country["id"])
    sel_region = None
    if region:
        sel_region = next((r for r in regions if r["name"] == region), None)
    scope_label = sel_country["name"]
    if sel_region:
        scope_label += f" — {sel_region['name']}"
    return {
        "countries": countries, "sel_country": sel_country,
        "regions": regions, "sel_region": sel_region,
        "region_id": sel_region["id"] if sel_region else None,
        "scope_label": scope_label,
    }
