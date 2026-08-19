"""Generic, country-agnostic detection of government/ministry sources.

Deliberately not a per-country curated domain list — as more countries are
added to the assessment scope, a hand-maintained list becomes upkeep load.
Instead this matches broad domain conventions used by government bodies
worldwide, plus a text fallback for official portals that don't happen to
sit on a government-style TLD.
"""

import re
from urllib.parse import urlparse

# .gov / .gov.<cc> (US, MY, UK, IN, SG, PH, ...), .go.<cc> (ID, JP, KR, TH, ...),
# .gouv.<cc> (FR and francophone administrations), .gob.<cc> (ES/LatAm).
_GOV_HOST_RE = re.compile(
    r"(^|\.)(gov|go|gouv|gob)(\.[a-z]{2,3})?$", re.IGNORECASE)

_GOV_KEYWORDS = (
    "ministry", "minister", "kementerian", "kementrian",
    "department of", "attorney general", "attorney-general",
    "government of", "gazette",
)


def host_of(url: str) -> str:
    if not url:
        return ""
    if "//" not in url:
        url = "//" + url
    return (urlparse(url).hostname or "").lower()


def is_government_source(source_name: str | None, url: str | None) -> bool:
    """True when a citation looks like an official government/ministry
    source, by domain convention or by name — independent of country."""
    host = host_of(url or "")
    if host:
        labels = host.split(".")
        # Check every suffix starting point, e.g. "mpob.gov.my" ->
        # "gov.my", "my" as trailing label groups.
        for i in range(len(labels)):
            if _GOV_HOST_RE.match(".".join(labels[i:])):
                return True
    text = (source_name or "").lower()
    return any(kw in text for kw in _GOV_KEYWORDS)
