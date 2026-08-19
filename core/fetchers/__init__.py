"""Non-LLM evidence fetchers: pull quantitative facts straight from a public
data API instead of spending a Claude research pass on them. Each fetcher
module registers itself against a section code; runmanager.py calls the
matching fetcher automatically for every research run that touches that
section — there is no separate manual step. A fetcher's output is a batch
dict shaped exactly like a `claude -p` research batch (see
research/schema.json), imported through the same importer.import_batch()
path, so it lands as ordinary 'pending' evidence: a human still reviews and
signs off on it, same as anything else.

A fetcher module must define:
    SECTION_CODE  — the section it supplies evidence for, e.g. "S4"
    SOURCE_TAG    — short slug for filenames/template_version, e.g. "GFW"
    SOURCE_NAME   — human-readable source name, for no_findings records
    build_evidence(iso3, country_name) -> list[dict]  — evidence records
        matching research/schema.json's evidence item shape, or [] if
        nothing could be obtained (live API down and no fallback data for
        that country) — never raises for a "no data" case.
"""

import json
from datetime import datetime

from .. import researcher

REGISTRY = {}


def register(module):
    REGISTRY[module.SECTION_CODE] = module
    return module


def build_batch(module, iso3, country_name, region, cycle_year):
    evidence = module.build_evidence(iso3, country_name)
    return {
        "meta": {
            "country": country_name,
            "region": region,
            "cycle": cycle_year,
            "scope": [module.SECTION_CODE],
            "run_type": "risk",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "template_version": f"{module.SOURCE_TAG.lower()}-fetcher-v1",
        },
        "evidence": evidence,
        "narrative_drafts": [],
        "no_findings": [] if evidence else [{
            "section": module.SECTION_CODE,
            "searched_for": module.SOURCE_NAME,
            "where_searched": [module.SOURCE_NAME],
        }],
    }


def fetch_and_import(conn, module, iso3, country_name, region, cycle_year, actor):
    """Fetches, validates, writes, and immediately imports a batch for one
    section from one public data source. Returns the importer summary dict,
    or None if the source had nothing to offer for this country (caller
    should fall back to Claude research alone for that section)."""
    from .. import importer as importer_module

    batch = build_batch(module, iso3, country_name, region, cycle_year)
    if not batch["evidence"]:
        return None
    errors = researcher.validate_batch(batch)
    if errors:
        raise ValueError(f"{module.SOURCE_TAG} batch failed validation: " +
                         "; ".join(errors[:10]))
    region_tag = f"_{region.replace(' ', '')}" if region else ""
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = (researcher.RESEARCH_DIR /
            f"{country_name.replace(' ', '')}{region_tag}_risk_"
            f"{module.SECTION_CODE}-{module.SOURCE_TAG}_{stamp}.json")
    path.write_text(json.dumps(batch, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return importer_module.import_batch(conn, path, actor)


# Import submodules for their register() side effect.
from . import fao, gfw, ilo, wgi  # noqa: E402,F401
