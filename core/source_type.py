"""Best-effort classification of a citation into a source *type*, so the
evidence base can show its mix (official vs civil society vs academic vs
media ...) per section and flag lopsided coverage.

The researcher is asked to set `source_type` itself; this module is the
fallback for records where it didn't (older batches, manual entries), and it
is deliberately conservative — anything it can't place lands in `other`
rather than being guessed into a category. The human can always change it.
"""

from .gov_sources import host_of, is_government_source

SOURCE_TYPES = ("official", "intergovernmental", "academic", "civil_society",
                "media", "industry", "other")

SOURCE_TYPE_LABELS = {
    "official": "Official / government",
    "intergovernmental": "Intergovernmental (UN, EU, FAO…)",
    "academic": "Academic / research",
    "civil_society": "Civil society / NGO",
    "media": "Media / journalism",
    "industry": "Industry / certification body",
    "other": "Other / unclassified",
}

# Types that count as "independent of state and industry" for the
# lopsided-coverage check on rights-sensitive sections.
INDEPENDENT_TYPES = ("civil_society", "academic", "media")

# Sections/legal areas where relying solely on official or industry sources
# is a real gap, not just a stylistic preference — land tenure, human/labour
# rights, indigenous consent, and "substantiated concerns" are exactly the
# topics where the people affected, not the state or the sector, are often
# the ones documenting what's actually happening.
RIGHTS_SENSITIVE_SCOPES = ("S3", "S8", "S9", "A1", "A3", "A5", "A6")


def source_mix(evidence_rows):
    """{source_type: count} over a list of evidence rows (sqlite3.Row with a
    source_type column) — used to show the evidence mix on a section card."""
    mix = {}
    for r in evidence_rows:
        t = r["source_type"] or "other"
        mix[t] = mix.get(t, 0) + 1
    return mix


def independent_count(mix):
    return sum(mix.get(t, 0) for t in INDEPENDENT_TYPES)


def source_mix_segments(mix):
    """Present source types only, in the fixed SOURCE_TYPES order (never
    sorted by count) so a type always gets the same position and color
    everywhere it appears — the point of a categorical palette. Each segment
    carries its CSS color variable name so the template just reads it."""
    total = sum(mix.values())
    if not total:
        return []
    return [
        {"type": t, "label": SOURCE_TYPE_LABELS[t], "count": mix[t],
         "pct": round(100 * mix[t] / total), "css_var": f"--st-{t}"}
        for t in SOURCE_TYPES if mix.get(t)
    ]

_INTERGOV_HINTS = (
    "un.org", "ohchr", "ilo.org", "fao.org", "unicef", "iom.int", "worldbank",
    "europa.eu", "eur-lex", "oecd", "undp", "unep", "unesco", "wto.org",
    "united nations", "european union", "european commission", "world bank",
    "international labour organization", "food and agriculture organization",
)
_OFFICIAL_EXTRA_HINTS = (
    "suhakam", "komnas ham", "human rights commission", "komnas perempuan",
    "ombudsman", "statistics", "badan pusat statistik", "central bank",
    "bank negara", "bank indonesia", "parliament", "dewan", "court",
    "mahkamah", "supreme court", "constitutional court",
)
_ACADEMIC_HINTS = (
    ".edu", ".ac.", "efi.int", "cifor", "cgiar", "researchgate", "sciencedirect", "springer",
    "wiley", "tandfonline", "nature.com", "jstor", "doi.org", "ssrn", "mdpi",
    "journal", "university", "universitas", "universiti", "institute for",
    "research institute", "working paper",
)
_CIVIL_HINTS = (
    "walhi", "sawit watch", "sawitwatch", "aman.or.id", "kpa.or.id",
    "forestpeoples", "forest peoples", "ran.org", "rainforest action",
    "mightyearth", "mighty earth", "globalwitness", "global witness",
    "eia-international", "environmental investigation agency", "greenpeace",
    "amnesty", "hrw.org", "human rights watch", "iwgia", "civicus",
    "transparency.org", "transparency international", "chainreactionresearch",
    "chain reaction research", "trase.earth", "auriga", "tuk indonesia",
    "elsam", "kaoem", "wwf", "wri.org", "world resources institute",
    "globalforestwatch", "friends of the earth", "foe.org", "oxfam",
    "solidaridad", "verite", "verité", "earthsight", "madre", "grain.org",
    "ngo", "foundation", "coalition", "network", "watch",
)
_MEDIA_HINTS = (
    "mongabay", "reuters", "bloomberg", "guardian", "bbc", "nytimes", "ft.com",
    "aljazeera", "kompas", "tempo.co", "thejakartapost", "jakarta post",
    "thestar.com.my", "malaysiakini", "malay mail", "detik", "cnnindonesia",
    "hukumonline", "antaranews", "news", "berita", "post", "times", "daily",
    "tribune", "herald", "magazine",
)
_INDUSTRY_HINTS = (
    "rspo", "mspo", "ispo", "gapki", "mpoc", "mpob", "palmoil", "sawit",
    "certification", "council", "association", "assoc.", "federation",
    "chamber of commerce", "company", "group", "plc", "berhad", "tbk",
    "sustainability report", "annual report",
)


def classify_source(source_name, url, publisher=None):
    """Return one of SOURCE_TYPES for a citation. Order matters: government
    check first (it's the most reliable signal), then intergovernmental,
    academic, civil society, media, industry, else other."""
    host = host_of(url or "")
    text = " ".join(x for x in (source_name, publisher, host) if x).lower()

    if is_government_source(source_name, url) or any(h in text for h in _OFFICIAL_EXTRA_HINTS):
        # MPOB/MPOC sit on gov domains but are industry-facing bodies; keep
        # them official — that's what they legally are. National human-rights
        # commissions, statistics offices and courts are state institutions too.
        return "official"
    if any(h in text for h in _INTERGOV_HINTS):
        return "intergovernmental"
    if any(h in text for h in _ACADEMIC_HINTS):
        return "academic"
    if any(h in text for h in _CIVIL_HINTS):
        return "civil_society"
    if any(h in text for h in _MEDIA_HINTS):
        return "media"
    if any(h in text for h in _INDUSTRY_HINTS):
        return "industry"
    return "other"


def normalise_source_type(value):
    """Accept the researcher's value only if it is one of ours."""
    v = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {"government": "official", "ngo": "civil_society",
               "civil-society": "civil_society", "civilsociety": "civil_society",
               "press": "media", "journalism": "media", "research": "academic",
               "un": "intergovernmental", "international_organisation": "intergovernmental",
               "international_organization": "intergovernmental",
               "certification": "industry", "company": "industry"}
    v = aliases.get(v, v)
    return v if v in SOURCE_TYPES else None
