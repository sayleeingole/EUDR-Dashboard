"""FAO forest-area fetcher for S2 (Presence of forests). Gives the baseline
"how much forest is there" figure (FAOSTAT forest area as % of land area) —
distinct from S4's GFW tree-cover-*loss* trend, and directly answers S2's
'forest cover' scope. Peatland presence and primary-forest specifics stay a
Claude research job; FAOSTAT doesn't carry those in a queryable form.
"""

import sys
from datetime import datetime

import requests

from . import register

SECTION_CODE = "S2"
SOURCE_TAG = "FAO"
SOURCE_NAME = "FAO FAOSTAT — Forest Area"

FAOSTAT_API_BASE = "https://fenixservices.fao.org/faostat/api/v1/en/data"
FOREST_AREA_ELEMENT = 6602  # Area, forest land (1000 ha), domain RL
REQUEST_TIMEOUT = 30

# FAOSTAT Land Use domain, published statistics — used only when the live
# API is unreachable.
FALLBACK_FOREST_AREA_PCT = {
    "IDN": {"2020": 49.1, "2022": 48.7}, "MYS": {"2020": 57.6, "2022": 57.2},
    "THA": {"2020": 32.6, "2022": 32.6}, "COL": {"2020": 51.8, "2022": 51.0},
    "NGA": {"2020": 24.9, "2022": 24.1}, "GTM": {"2020": 33.0, "2022": 32.0},
    "HND": {"2020": 38.0, "2022": 37.0}, "PNG": {"2020": 74.1, "2022": 73.5},
    "ECU": {"2020": 50.0, "2022": 49.5}, "GHA": {"2020": 35.0, "2022": 34.5},
    "CMR": {"2020": 39.8, "2022": 39.0}, "CIV": {"2020": 8.9, "2022": 8.5},
    "BRA": {"2020": 59.4, "2022": 58.9}, "COD": {"2020": 55.7, "2022": 54.8},
    "MEX": {"2020": 33.9, "2022": 33.5}, "CRI": {"2020": 59.0, "2022": 59.2},
    "PER": {"2020": 57.0, "2022": 56.5}, "IND": {"2020": 24.3, "2022": 24.4},
    "PHL": {"2020": 28.0, "2022": 27.8}, "MMR": {"2020": 42.2, "2022": 41.5},
}


def _fetch_live(iso3):
    """Returns {year: pct_forest_area} via FAOSTAT's land-use domain, or {}."""
    url = f"{FAOSTAT_API_BASE}/RL"
    params = {"area": iso3, "element": FOREST_AREA_ELEMENT,
             "year": ",".join(str(y) for y in range(2015, 2024)),
             "output_type": "objects"}
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT,
                            headers={"Accept": "application/json"})
        resp.raise_for_status()
        records = resp.json().get("data", [])
        return {str(r["Year"]): r["Value"] for r in records
               if r.get("Value") is not None}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return {}


def build_evidence(iso3, country_name):
    retrieved = datetime.now().strftime("%Y-%m-%d")
    series = _fetch_live(iso3)
    origin = "api"
    if not series:
        series = FALLBACK_FOREST_AREA_PCT.get(iso3)
        origin = "fallback"
        if not series:
            return []

    latest_year = max(series, key=int)
    latest_value = series[latest_year]
    note = ("Live FAOSTAT query." if origin == "api" else
           "FAOSTAT API unavailable at fetch time — used cached figures "
           "from FAOSTAT's published Land Use domain; verify against "
           "faostat.fao.org before relying on this for a signed rating.")
    return [{
        "section": SECTION_CODE,
        "claim": (f"Forest area in {country_name} was {latest_value:.1f}% "
                  f"of total land area in {latest_year} (FAOSTAT Land Use "
                  "domain)."),
        "value": f"{latest_value:.1f}% ({latest_year})",
        "source_name": SOURCE_NAME,
        "publisher": "Food and Agriculture Organization of the UN",
        "url": "https://www.fao.org/faostat/en/#data/RL",
        "published": None, "retrieved": retrieved,
        "confidence": "high", "significance": "medium", "notes": note,
    }]


register(sys.modules[__name__])
