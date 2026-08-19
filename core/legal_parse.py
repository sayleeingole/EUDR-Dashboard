"""Best-effort, display-time parsing of legal_requirements rows created before
`req_type`/`authority`/`verification_docs` existed as structured fields (see
core/db.decide_evidence's A1-A7 promotion branch, and research/templates/legal.md).

Never writes back to the DB — a row with NULL structured fields is parsed fresh
on every request. Deliberately best-effort: these are old free-text blobs in
inconsistent formats, and getting a row wrong here costs nothing (the human
reviewer sees the source text either way and decides for themselves).
"""

import re

_TYPE_PREFIX_RE = re.compile(r"^([A-Z][A-Z /]{2,40})(?::|\s[—–-]\s)\s*(.*)$",
                             re.DOTALL)

_TYPE_KEYWORDS = (
    ("JURISPRUDENCE", "jurisprudence"),
    ("TREATY", "treaty"),
    ("POLICY", "policy"),
    ("INSTRUMENT", "instrument"),
    ("REQUIREMENT", "requirement"),
)

_AUTHORITY_RE = re.compile(
    r"\b(Ministry of [A-Z][a-zA-Z &]+|Department of [A-Z][a-zA-Z &]+|"
    r"Attorney[- ]General'?s? Chambers|MPOB|MPOCC|DOSM|DOSH|DOE|SUHAKAM|KLHK|BPS|"
    r"GAPKI|Komnas HAM|ISPO|JDIH)\b")

_DOC_MARKER_RE = re.compile(r"Verification documents?:\s*", re.IGNORECASE)
_DOC_STOP_RE = re.compile(r"\s*(?:Provision:|$)", re.IGNORECASE)


def _split_type(requirement: str):
    m = _TYPE_PREFIX_RE.match(requirement.strip())
    if not m:
        return "requirement", requirement.strip()
    raw, rest = m.group(1).upper(), m.group(2).strip()
    for keyword, req_type in _TYPE_KEYWORDS:
        if keyword in raw:
            return req_type, rest
    return "requirement", rest


def _split_docs(provision: str):
    if not provision:
        return provision or "", []
    m = _DOC_MARKER_RE.search(provision)
    if not m:
        return provision.strip(), []
    context = (provision[:m.start()] + provision[_doc_end(provision, m.end()):]).strip()
    doc_text = provision[m.end():_doc_end(provision, m.end())]
    docs = [d.strip().rstrip(".") for d in re.split(r"[;,]", doc_text) if d.strip()]
    return context, docs[:8]


def _doc_end(provision, start):
    stop = _DOC_STOP_RE.search(provision, start)
    return stop.start() if stop else len(provision)


def parse_legacy(requirement: str, provision: str):
    """Returns {req_type, explanation, context, authority, verification_docs}."""
    requirement = requirement or ""
    provision = provision or ""
    req_type, explanation = _split_type(requirement)
    context, docs = _split_docs(provision)
    authority_m = _AUTHORITY_RE.search(requirement + " " + provision)
    return {
        "req_type": req_type,
        "explanation": explanation,
        "context": context,
        "authority": authority_m.group(1) if authority_m else None,
        "verification_docs": docs,
    }
