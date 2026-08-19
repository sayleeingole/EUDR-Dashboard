"""World Bank Worldwide Governance Indicators fetcher for S5 (Governance
concerns). The World Bank API is a plain, reliable JSON endpoint — no key
needed — so this one doesn't carry a static fallback table the way GFW/ILO
do; it simply contributes nothing if the API is unreachable, and Claude's
research pass covers the section as it always has.
"""

import sys
from datetime import datetime

import requests

from . import register

SECTION_CODE = "S5"
SOURCE_TAG = "WGI"
SOURCE_NAME = "World Bank — Worldwide Governance Indicators"

WB_API_BASE = "https://api.worldbank.org/v2"
REQUEST_TIMEOUT = 30

# S5's min_scope calls out corruption and regulatory quality by name; rule
# of law and government effectiveness are the other two WGI dimensions most
# relevant to "palm sector regulation quality".
INDICATORS = {
    "GOV_WGI_CC.EST": ("Control of Corruption", "high"),
    "GOV_WGI_RQ.EST": ("Regulatory Quality", "medium"),
    "GOV_WGI_RL.EST": ("Rule of Law", "medium"),
    "GOV_WGI_GE.EST": ("Government Effectiveness", "medium"),
}


def _fetch_indicator(iso3, indicator_id):
    """Returns {year: value} for one country/indicator, most recent years
    first, or {} on any failure."""
    url = f"{WB_API_BASE}/country/{iso3}/indicator/{indicator_id}"
    params = {"format": "json", "per_page": 20, "date": "2015:2025"}
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT,
                            headers={"Accept": "application/json"})
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
            return {}
        return {row["date"]: row["value"] for row in payload[1]
               if row.get("value") is not None}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return {}


def build_evidence(iso3, country_name):
    retrieved = datetime.now().strftime("%Y-%m-%d")
    url = f"https://databank.worldbank.org/source/worldwide-governance-indicators"
    evidence = []
    for indicator_id, (label, significance) in INDICATORS.items():
        series = _fetch_indicator(iso3, indicator_id)
        if not series:
            continue
        latest_year = max(series, key=int)
        latest_value = series[latest_year]
        evidence.append({
            "section": SECTION_CODE,
            "claim": (f"{country_name}'s World Bank {label} estimate for "
                      f"{latest_year} was {latest_value:.2f} (governance "
                      "estimate in standard normal units, approx. -2.5 "
                      "weak to +2.5 strong)."),
            "value": f"{latest_value:.2f} ({latest_year})",
            "source_name": SOURCE_NAME,
            "publisher": "World Bank",
            "url": url, "published": None, "retrieved": retrieved,
            "confidence": "high", "significance": significance,
            "notes": f"WGI indicator {indicator_id}. Live World Bank API query.",
        })
    return evidence


register(sys.modules[__name__])
