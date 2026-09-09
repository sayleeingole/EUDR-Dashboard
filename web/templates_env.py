import json
from pathlib import Path

from fastapi.templating import Jinja2Templates

from core.source_type import SOURCE_TYPE_LABELS, SOURCE_TYPES

from .citations import linkify_citations

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Section/legal-area codes (S1-S10, A1-A7) are meaningless on their own —
# every place one is shown bare in the UI should carry its title too. These
# are seeded once at db init and never edited afterward (core/db.py:_migrate
# has no UPDATE for sections/legal_areas), so a static load at import time is
# safe and avoids a DB round-trip just to label a code.
_SEEDS_DIR = BASE_DIR / "data" / "seeds"


def _code_titles():
    titles = {}
    for name in ("sections.json", "legal_areas.json"):
        for row in json.loads((_SEEDS_DIR / name).read_text(encoding="utf-8")):
            titles[row["code"]] = row["title"]
    return titles


CODE_TITLES = _code_titles()


def code_label(code):
    """'S3' -> 'S3 · Indigenous peoples & customary tenure'. Unknown or empty
    codes pass through unchanged rather than erroring."""
    if not code:
        return ""
    title = CODE_TITLES.get(code)
    return f"{code} · {title}" if title else code

REJECT_REASONS = ["Not relevant (country/region/commodity)",
                  "Outdated data / wrong vintage",
                  "Duplicate",
                  "Source misread / claim not supported by source",
                  "Other (specify)"]

# Every rating scale (risk, benchmark) maps onto one 3-step visual tone so a
# single pill component (templates/_macros.html:rating_pill) can render all
# of them — never color alone, text label always carries the actual scale
# term (08 §4.5). Risk (S2-S10) is binary negligible/not_negligible; benchmark
# (S1) is the EU's own low/standard/high classification.
RATING_TONE = {"negligible": "low", "low": "low",
               "standard": "medium",
               "not_negligible": "high", "high": "high"}

def static_url(path):
    """`/static/app.js` -> `/static/app.js?v=<mtime>` so browsers pick up a
    changed CSS/JS file immediately instead of serving a stale cached copy."""
    f = BASE_DIR / "static" / path.lstrip("/")
    try:
        stamp = int(f.stat().st_mtime)
    except OSError:
        stamp = 0
    return f"/static/{path.lstrip('/')}?v={stamp}"


templates.env.globals["static_url"] = static_url
templates.env.globals["REJECT_REASONS"] = REJECT_REASONS
templates.env.globals["SOURCE_TYPE_LABELS"] = SOURCE_TYPE_LABELS
templates.env.globals["SOURCE_TYPES"] = SOURCE_TYPES
templates.env.filters["code_label"] = code_label
templates.env.globals["RATING_TONE"] = RATING_TONE
templates.env.filters["linkify_citations"] = linkify_citations
