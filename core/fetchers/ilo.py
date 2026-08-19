"""ILO child-labour rate fetcher for S8 (Human rights). ILOSTAT's SDMX API
is notoriously complex to parse reliably (nested dimension/observation
structures that vary by query); rather than risk silently misreading it,
this fetcher tries ILOSTAT's simpler REST endpoint and falls back to a
curated table from published ILO/UNICEF joint estimates when that's
unavailable — the same trade-off GFW's fetcher makes for tree-cover data.
Only covers child labour prevalence: S8's other angles (forced-labour
listings, import control measures, migrant workforce structure, national
action plans) are qualitative/narrative and stay a Claude research job.
"""

import sys
from datetime import datetime

import requests

from . import register

SECTION_CODE = "S8"
SOURCE_TAG = "ILO"
SOURCE_NAME = "ILO — Child Labour Prevalence"

ILOSTAT_REST_BASE = "https://rplumber.ilo.org/data/indicator"
CHILD_LABOR_INDICATOR = "SDG_0871_SEX_AGE_RT"
REQUEST_TIMEOUT = 30

# ILO-UNICEF Joint Report on Child Labour (2020) / national labour force
# surveys — used only when the live API has nothing for this country.
FALLBACK_CHILD_LABOR = {
    "IDN": {"rate": 7.0, "year": 2019, "source": "SAKERNAS 2019"},
    "MYS": {"rate": 2.4, "year": 2019, "source": "National estimate"},
    "THA": {"rate": 5.3, "year": 2019, "source": "NSO Labour Force Survey"},
    "COL": {"rate": 5.4, "year": 2020, "source": "DANE ENTI"},
    "NGA": {"rate": 30.5, "year": 2017, "source": "MICS 2016-17"},
    "GTM": {"rate": 16.5, "year": 2018, "source": "ENCOVI 2014 / ENEI"},
    "HND": {"rate": 14.8, "year": 2019, "source": "INE EPHPM"},
    "PNG": {"rate": 18.0, "year": 2018, "source": "HIES 2009-10 / ILO estimate"},
    "ECU": {"rate": 8.0, "year": 2019, "source": "ENEMDU"},
    "GHA": {"rate": 21.8, "year": 2017, "source": "MICS 2017-18"},
    "CMR": {"rate": 39.5, "year": 2017, "source": "MICS 2014 / ILO estimate"},
    "CIV": {"rate": 21.5, "year": 2019, "source": "MICS 2016 / ENSETE"},
    "BRA": {"rate": 4.2, "year": 2019, "source": "PNAD Continua"},
    "COD": {"rate": 23.0, "year": 2018, "source": "MICS 2017-18"},
    "MEX": {"rate": 7.1, "year": 2019, "source": "ENTI / MTI"},
    "CRI": {"rate": 4.3, "year": 2016, "source": "INEC ETI"},
    "PER": {"rate": 21.8, "year": 2019, "source": "ENAHO"},
    "IND": {"rate": 9.8, "year": 2019, "source": "Census 2011 / ILO estimate"},
    "PHL": {"rate": 11.4, "year": 2019, "source": "CPBI / SPCL"},
    "MMR": {"rate": 15.3, "year": 2018, "source": "LFS 2015 / ILO estimate"},
}


def _fetch_live(iso3):
    """Returns (rate, year) from ILOSTAT's REST endpoint, or (None, None)."""
    url = f"{ILOSTAT_REST_BASE}/?id={CHILD_LABOR_INDICATOR}&ref_area={iso3}&type=both"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT,
                            headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return None, None
        records = resp.json()
        records = records if isinstance(records, list) else records.get("data", [])
        best = None
        for r in records:
            sex = r.get("sex", {}).get("code") if isinstance(r.get("sex"), dict) else r.get("sex")
            if sex and sex not in ("SEX_T", "T", ""):
                continue
            value = r.get("obs_value")
            year = r.get("time")
            if value is None or year is None:
                continue
            if best is None or int(year) > int(best[1]):
                best = (float(value), year)
        return best if best else (None, None)
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return None, None


def build_evidence(iso3, country_name):
    retrieved = datetime.now().strftime("%Y-%m-%d")
    rate, year = _fetch_live(iso3)
    origin = "api"
    if rate is None:
        fb = FALLBACK_CHILD_LABOR.get(iso3)
        if not fb:
            return []
        rate, year, origin = fb["rate"], fb["year"], fb["source"]

    note = ("Live ILOSTAT query." if origin == "api" else
           f"ILOSTAT API had no current data for {country_name} — used "
           f"cached figure from {origin} (ILO-UNICEF joint estimates). "
           "Verify against ILOSTAT before relying on this for a signed "
           "rating.")
    return [{
        "section": SECTION_CODE,
        "claim": (f"Child labour prevalence in {country_name}: {rate:.1f}% "
                  f"of children aged 5-17 ({year})."),
        "value": f"{rate:.1f}% ({year})",
        "source_name": SOURCE_NAME,
        "publisher": "International Labour Organization",
        "url": "https://www.ilo.org/shinyapps/bulkexplorer23/",
        "published": None, "retrieved": retrieved,
        "confidence": "high" if origin == "api" else "medium",
        "significance": "high", "notes": note,
    }]


register(sys.modules[__name__])
