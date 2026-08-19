"""Best-effort linkification of inline citations in signed narratives.

Narratives are free text (e.g. "...(GFW, 2026)...") with no structured
pointer back to the evidence record they came from. This matches each
parenthetical citation against the section's approved evidence by acronym
expansion, token overlap, and year, and links it to that evidence's URL
when the match is confident enough. Unmatched citations (e.g. a source
that was cited but never captured as evidence) are left as plain text —
a false link would be worse than no link.
"""

import re

from markupsafe import Markup, escape

# Acronyms commonly used in shorthand citations, mapped to phrases/domains
# that should appear in the matching evidence's source name or URL.
_ACRONYM_KEYWORDS = {
    "gfw": ["global forest watch", "globalnaturewatch", "gfr.wri.org"],
    "umd": ["university of maryland", "globalnaturewatch", "gfr.wri.org", "glad"],
    "glad": ["glad", "globalnaturewatch", "gfr.wri.org"],
    "wri": ["world resources institute", "gfr.wri.org"],
    "jrc": ["joint research centre", "jrc.ec.europa.eu", "forest-observatory.ec.europa.eu"],
    "fao": ["food and agriculture organization", "fao.org"],
    "nusantara atlas": ["nusantara-atlas", "nusantaratlas"],
    "efi": ["european forest institute", "efi.int"],
}

_CITATION_RE = re.compile(r"\(([^()]{2,80})\)")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_MATCH_THRESHOLD = 2


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _score(citation_norm: str, tokens: set, evidence) -> int:
    source_norm = _normalize(evidence["source_name"] or "")
    url = (evidence["url"] or "").lower()
    score = len(tokens & set(source_norm.split()))
    for acro, keywords in _ACRONYM_KEYWORDS.items():
        if f" {acro} " in f" {citation_norm} " and any(
            kw in source_norm or kw in url for kw in keywords
        ):
            score += 2
    retrieved = evidence["retrieved"] or ""
    for year in _YEAR_RE.findall(citation_norm):
        if year in source_norm or year in url or year in retrieved:
            score += 1
    return score


def _best_match(citation_text: str, approved_ev):
    citation_norm = _normalize(citation_text)
    tokens = set(citation_norm.split())
    best, best_score = None, 0
    for evidence in approved_ev:
        if not evidence["url"]:
            continue
        score = _score(citation_norm, tokens, evidence)
        if score > best_score:
            best, best_score = evidence, score
    return best if best_score >= _MATCH_THRESHOLD else None


def linkify_citations(narrative, approved_ev):
    """Wrap `(citation)` spans in the narrative with a link to the matching
    approved evidence's URL, where a confident match exists."""
    if not narrative:
        return narrative
    parts = []
    last_end = 0
    for m in _CITATION_RE.finditer(narrative):
        evidence = _best_match(m.group(1), approved_ev or [])
        if evidence:
            parts.append(escape(narrative[last_end:m.start()]))
            parts.append(Markup(
                '(<a href="{url}" target="_blank" rel="noopener">{text}</a>)'
            ).format(url=escape(evidence["url"]), text=escape(m.group(1))))
        else:
            parts.append(escape(narrative[last_end:m.end()]))
        last_end = m.end()
    parts.append(escape(narrative[last_end:]))
    return Markup("").join(parts)
