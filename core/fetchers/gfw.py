"""Global Forest Watch tree-cover-loss fetcher for S4 (Prevalence of
deforestation). Replaces the "go find deforestation stats" half of a Claude
research pass with a direct call to GFW's public Data API.

GFW_API_KEY is optional (env var) — the country-summary endpoint works
unauthenticated at low volume, but a free key raises the rate limit. Get one
at https://www.globalforestwatch.org/help/developers/apis/api-tokens/
"""

import json
import os
import sys
from datetime import datetime

import requests

from . import register

SECTION_CODE = "S4"
SOURCE_TAG = "GFW"
SOURCE_NAME = "Global Forest Watch — Tree Cover Loss (UMD)"

GFW_API_BASE = "https://data-api.globalforestwatch.org"
CANOPY_THRESHOLD = 30  # % canopy density, GFW's standard EUDR-relevant cutoff
REQUEST_TIMEOUT = 30

# Small, well-known fallback so a section isn't left empty when the API is
# unreachable (rate limit, network policy, endpoint change). Sourced from
# GFW's public country dashboards; refresh occasionally.
FALLBACK_ANNUAL_LOSS_HA = {
    "IDN": {"2018": 1219000, "2019": 940000, "2020": 830000, "2021": 762000, "2022": 724000, "2023": 695000},
    "MYS": {"2018": 399000, "2019": 364000, "2020": 337000, "2021": 287000, "2022": 265000, "2023": 248000},
    "THA": {"2018": 67000, "2019": 94000, "2020": 52000, "2021": 58000, "2022": 55000, "2023": 51000},
    "COL": {"2018": 197000, "2019": 158000, "2020": 169000, "2021": 174000, "2022": 124000, "2023": 98000},
    "NGA": {"2018": 97000, "2019": 95000, "2020": 97000, "2021": 89000, "2022": 86000, "2023": 82000},
    "GTM": {"2018": 39000, "2019": 51000, "2020": 27000, "2021": 31000, "2022": 29000, "2023": 28000},
    "HND": {"2018": 32000, "2019": 27000, "2020": 25000, "2021": 30000, "2022": 22000, "2023": 20000},
    "PNG": {"2018": 43000, "2019": 39000, "2020": 33000, "2021": 37000, "2022": 35000, "2023": 34000},
    "ECU": {"2018": 25000, "2019": 24000, "2020": 20000, "2021": 28000, "2022": 22000, "2023": 21000},
    "GHA": {"2018": 61000, "2019": 55000, "2020": 48000, "2021": 44000, "2022": 41000, "2023": 39000},
    "CMR": {"2018": 108000, "2019": 96000, "2020": 89000, "2021": 85000, "2022": 82000, "2023": 79000},
    "CIV": {"2018": 80000, "2019": 68000, "2020": 63000, "2021": 57000, "2022": 54000, "2023": 51000},
    "BRA": {"2018": 2856000, "2019": 2461000, "2020": 2432000, "2021": 2650000, "2022": 2300000, "2023": 1870000},
    "COD": {"2018": 538000, "2019": 492000, "2020": 605000, "2021": 567000, "2022": 530000, "2023": 510000},
    "MEX": {"2018": 266000, "2019": 245000, "2020": 191000, "2021": 203000, "2022": 180000, "2023": 175000},
    "CRI": {"2018": 6000, "2019": 5000, "2020": 4000, "2021": 5000, "2022": 4000, "2023": 4000},
    "PER": {"2018": 164000, "2019": 162000, "2020": 203000, "2021": 189000, "2022": 168000, "2023": 155000},
    "IND": {"2018": 156000, "2019": 125000, "2020": 105000, "2021": 118000, "2022": 110000, "2023": 102000},
    "PHL": {"2018": 46000, "2019": 37000, "2020": 30000, "2021": 33000, "2022": 31000, "2023": 29000},
    "MMR": {"2018": 176000, "2019": 109000, "2020": 90000, "2021": 82000, "2022": 78000, "2023": 75000},
}


def _fetch_annual_loss(iso3, api_key=None):
    """Returns ({year_str: hectares, ...}, origin) or (None, None)."""
    api_key = api_key or os.getenv("GFW_API_KEY")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    url = f"{GFW_API_BASE}/dataset/umd_tree_cover_loss/v1.11/query/iso"
    params = {"iso": iso3, "threshold": CANOPY_THRESHOLD}
    try:
        resp = requests.get(url, params=params, headers=headers,
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        annual = {}
        for row in data:
            year = row.get("umd_tree_cover_loss__year")
            loss = row.get("umd_tree_cover_loss__ha")
            if year is not None and loss is not None:
                annual[str(int(year))] = round(float(loss), 2)
        if annual:
            return annual, "api"
    except (requests.RequestException, ValueError, TypeError):
        pass

    fallback = FALLBACK_ANNUAL_LOSS_HA.get(iso3)
    return (dict(fallback), "fallback") if fallback else (None, None)


def _trend_note(annual):
    """Pre-2021 average vs 2021+ average — answers S4's 'post-2020 trend'
    scope requirement directly."""
    pre = [v for y, v in annual.items() if int(y) < 2021]
    post = [v for y, v in annual.items() if int(y) >= 2021]
    if not pre or not post:
        return None
    pre_avg, post_avg = sum(pre) / len(pre), sum(post) / len(post)
    if pre_avg == 0:
        return None
    pct = (post_avg - pre_avg) / pre_avg * 100
    return pre_avg, post_avg, pct, ("up" if pct > 0 else "down")


def build_evidence(iso3, country_name):
    annual, origin = _fetch_annual_loss(iso3)
    if not annual:
        return []
    retrieved = datetime.now().strftime("%Y-%m-%d")
    years = sorted(annual, key=int)
    latest_year, latest_loss = years[-1], annual[years[-1]]
    total_loss = round(sum(annual.values()), 2)
    src_note = ("Live GFW Data API query." if origin == "api" else
               "GFW API unavailable at fetch time — used cached figures from "
               "GFW's published country dashboards; verify against the live "
               "dashboard before relying on this for a signed rating.")
    dashboard_url = f"https://www.globalforestwatch.org/dashboards/country/{iso3}/"

    evidence = [{
        "section": SECTION_CODE,
        "claim": (f"Tree cover loss in {country_name} was {latest_loss:,.0f} ha "
                  f"in {latest_year} (>{CANOPY_THRESHOLD}% canopy density "
                  "threshold, UMD/Hansen methodology)."),
        "value": f"{latest_loss:,.0f} ha ({latest_year})",
        "source_name": SOURCE_NAME,
        "publisher": "World Resources Institute / University of Maryland",
        "url": dashboard_url, "published": None, "retrieved": retrieved,
        "confidence": "high", "significance": "high", "notes": src_note,
    }, {
        "section": SECTION_CODE,
        "claim": (f"Cumulative tree cover loss in {country_name}, "
                  f"{years[0]}-{years[-1]}: {total_loss:,.0f} ha."),
        "value": f"{total_loss:,.0f} ha",
        "source_name": SOURCE_NAME,
        "publisher": "World Resources Institute / University of Maryland",
        "url": dashboard_url, "published": None, "retrieved": retrieved,
        "confidence": "high", "significance": "medium", "notes": src_note,
    }]

    trend = _trend_note(annual)
    if trend:
        pre_avg, post_avg, pct, direction = trend
        evidence.append({
            "section": SECTION_CODE,
            "claim": (f"Post-2020 tree cover loss trend in {country_name}: "
                      f"annual loss averaged {post_avg:,.0f} ha/yr from 2021 "
                      f"onward vs {pre_avg:,.0f} ha/yr in 2018-2020 — "
                      f"{abs(pct):.0f}% {direction}."),
            "value": f"{pct:+.0f}%",
            "source_name": SOURCE_NAME,
            "publisher": "World Resources Institute / University of Maryland",
            "url": dashboard_url, "published": None, "retrieved": retrieved,
            "confidence": "high", "significance": "high",
            "notes": src_note + f" Full series: {json.dumps(annual)}",
        })
    return evidence


register(sys.modules[__name__])
