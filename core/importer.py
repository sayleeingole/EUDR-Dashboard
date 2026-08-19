"""Imports validated research batches into the evidence queue as PENDING records.
Whitelist matching, duplicate flagging, and narrative draft storage happen here.
The import itself is an audited event; review happens in the queue."""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from . import db
from .gov_sources import host_of, is_government_source
from .source_type import classify_source, normalise_source_type
from .researcher import validate_batch, mark_imported

SIMILARITY_THRESHOLD = 0.72
RATING_SCALE = ("low", "medium", "high")
REQ_TYPES = ("instrument", "requirement", "jurisprudence", "treaty", "policy")
APPLICABILITY = ("plantation", "smallholder", "both")
MANDATORY = ("yes", "no", "conditional")
SUPPLY_CHAIN_NODES = ("business_partner", "mill", "refinery", "source")


def _rating(value):
    v = (value or "").strip().lower()
    return v if v in RATING_SCALE else None


def _req_type(value):
    v = (value or "").strip().lower()
    return v if v in REQ_TYPES else None


def _applicability(value):
    v = (value or "").strip().lower()
    return v if v in APPLICABILITY else None


def _is_mandatory(value):
    v = (value or "").strip().lower()
    return v if v in MANDATORY else None


def _supply_chain_node(value):
    """Batch supplies a list of node keys; store as the same comma-string
    format the refine form writes, keeping only recognized values."""
    if not value:
        return None
    nodes = [v.strip().lower() for v in value if v and v.strip().lower() in SUPPLY_CHAIN_NODES]
    return ",".join(nodes) if nodes else None


def _sig_numbers(text):
    """Distinctive numeric tokens (figures, percentages) — excludes bare years,
    which are too common to identify a fact."""
    nums = set()
    for m in re.findall(r"\d[\d,.]*%?", text):
        tok = m.rstrip(".").replace(",", "")
        if tok.endswith("%"):
            nums.add(tok)
            continue
        if re.fullmatch(r"(19|20)\d\d", tok):
            continue
        if len(tok.replace(".", "")) >= 3:
            nums.add(tok)
    return nums


def is_duplicate(claim_a, claim_b):
    """Same fact reworded: high text similarity OR >=2 shared distinctive
    figures (e.g. '258,800 ha' + '11%' appearing in both)."""
    a, b = claim_a.lower().strip(), claim_b.lower().strip()
    if a == b:
        return True
    if SequenceMatcher(None, a, b).ratio() >= SIMILARITY_THRESHOLD:
        return True
    return len(_sig_numbers(a) & _sig_numbers(b)) >= 2


def _match_source(sources, source_name, url):
    """Match by name (case-insensitive substring both ways) or URL pattern."""
    name_l = (source_name or "").lower().strip()
    url_l = (url or "").lower()
    for s in sources:
        s_name = s["name"].lower()
        if s_name == name_l or s_name in name_l or name_l in s_name:
            return s["id"]
        if s["url_pattern"] and s["url_pattern"].lower() in url_l:
            return s["id"]
    return None


def _auto_whitelist_gov_source(conn, sources, source_name, url, section_code, actor):
    """Auto-whitelist an official government/ministry citation with no human
    approval step. Mutates `sources` in place so later citations in the same
    batch match immediately instead of each triggering its own insert."""
    name = (source_name or "").strip() or "Unknown government source"
    host = host_of(url)
    cur = conn.execute(
        "INSERT INTO sources (name, publisher, url_pattern, applies_to, status,"
        " added_by, added_at, reason) VALUES (?,?,?,?,'active',?,?,?)",
        (name, None, host or None, section_code, actor, db.now(),
         "auto-whitelisted: government/ministry domain"))
    source_id = cur.lastrowid
    db.audit(conn, "source_added", "sources", entity_id=source_id,
             section_code=section_code,
             after={"name": name, "url_pattern": host, "applies_to": section_code,
                    "auto_whitelisted": True},
             reason="auto-whitelisted: government/ministry domain", actor=actor)
    sources.append({"id": source_id, "name": name, "url_pattern": host})
    return source_id


def import_batch(conn, path: Path, actor):
    """Returns summary dict. Batch must already be schema-valid."""
    batch = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_batch(batch)
    if errors:
        raise ValueError("Batch failed validation: " + "; ".join(errors[:10]))
    meta = batch["meta"]

    country = conn.execute("SELECT * FROM countries WHERE name=?",
                           (meta["country"],)).fetchone()
    if country is None:
        raise ValueError(f"Unknown country '{meta['country']}' — add it in the "
                         "sidebar first.")
    region_id = None
    if meta.get("region"):
        region = conn.execute(
            "SELECT * FROM regions WHERE country_id=? AND name=?",
            (country["id"], meta["region"])).fetchone()
        if region is None:
            raise ValueError(f"Unknown region '{meta['region']}' for "
                             f"{meta['country']} — add it in the sidebar first.")
        region_id = region["id"]

    cycle = conn.execute("SELECT * FROM assessment_cycles WHERE year=?",
                         (meta["cycle"],)).fetchone()
    if cycle is None or cycle["status"] != "open":
        raise ValueError(f"Cycle {meta['cycle']} is not open.")

    sources = db.get_active_sources(conn)
    # Existing claims per section (pending + approved) for fuzzy dedup —
    # includes records from THIS batch as they are added, so intra-batch
    # duplicates are caught too.
    existing = {}
    for row in conn.execute(
            "SELECT section_code, claim FROM evidence WHERE cycle_id=?"
            " AND country_id=? AND status IN ('pending','approved')",
            (cycle["id"], country["id"])):
        existing.setdefault(row["section_code"], []).append(row["claim"])

    imported, unlisted, dup_flagged, gov_whitelisted = 0, 0, 0, 0
    for e in batch["evidence"]:
        source_id = _match_source(sources, e.get("source_name"), e.get("url"))
        if source_id is None and is_government_source(e.get("source_name"), e.get("url")):
            source_id = _auto_whitelist_gov_source(
                conn, sources, e.get("source_name"), e.get("url"), e["section"], actor)
            gov_whitelisted += 1
        claim = e["claim"].strip()
        ev_id = db.add_evidence(
            conn, cycle_id=cycle["id"], country_id=country["id"],
            region_id=region_id, section_code=e["section"],
            claim=claim, value=(e.get("value") or None),
            source_id=source_id, source_name=e["source_name"],
            publisher=(e.get("publisher") or "").strip() or None,
            url=e.get("url"), published=e.get("published"),
            retrieved=e["retrieved"], origin="claude_research",
            actor=actor, batch_file=path.name, notes=e.get("notes"),
            confidence=_rating(e.get("confidence")),
            significance=_rating(e.get("significance")),
            req_type=_req_type(e.get("req_type")),
            authority=(e.get("authority") or "").strip() or None,
            verification_docs=(e.get("verification_docs") or None),
            applicability=_applicability(e.get("applicability")),
            supply_chain_node=_supply_chain_node(e.get("supply_chain_node")),
            is_mandatory=_is_mandatory(e.get("is_mandatory")),
            alt_document=(e.get("alt_document") or "").strip() or None,
            mandatory_condition=(e.get("mandatory_condition") or "").strip() or None,
            source_type=(normalise_source_type(e.get("source_type"))
                         or classify_source(e.get("source_name"), e.get("url"), e.get("publisher"))))
        if source_id is None:
            unlisted += 1
        if any(is_duplicate(claim, prior)
               for prior in existing.get(e["section"], [])):
            conn.execute(
                "UPDATE evidence SET flag=COALESCE(flag,'possible-duplicate')"
                " WHERE id=?", (ev_id,))
            dup_flagged += 1
        existing.setdefault(e["section"], []).append(claim)
        imported += 1

    drafts = 0
    for nd in batch.get("narrative_drafts", []) or []:
        conn.execute(
            "INSERT INTO narrative_drafts (cycle_id, country_id, region_id,"
            " section_code, text, sources, batch_file, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (cycle["id"], country["id"], region_id, nd["section"], nd["text"],
             json.dumps(nd.get("sources", []), ensure_ascii=False),
             path.name, db.now()))
        drafts += 1

    no_findings = batch.get("no_findings", []) or []
    db.audit(conn, "batch_imported", "research_batch", entity_id=path.name,
             country=country["name"],
             after={"evidence": imported, "unlisted_source": unlisted,
                    "possible_duplicates": dup_flagged,
                    "gov_auto_whitelisted": gov_whitelisted,
                    "narrative_drafts": drafts,
                    "no_findings": len(no_findings)},
             actor=actor)
    conn.commit()
    mark_imported(path)
    return {"evidence": imported, "unlisted": unlisted, "duplicates": dup_flagged,
            "gov_whitelisted": gov_whitelisted, "drafts": drafts,
            "no_findings": no_findings}


def store_draft(conn, cycle_id, country_id, region_id, section_code, text,
                sources=None, batch_file="on-demand", actor=None, country_name=None):
    """Save a narrative draft generated outside a research batch (e.g. the
    'Generate narrative draft' button on a section card)."""
    conn.execute(
        "INSERT INTO narrative_drafts (cycle_id, country_id, region_id,"
        " section_code, text, sources, batch_file, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (cycle_id, country_id, region_id, section_code, text,
         json.dumps(sources or [], ensure_ascii=False), batch_file, db.now()))
    db.audit(conn, "narrative_drafted", "narrative_draft", entity_id=section_code,
             country=country_name, section_code=section_code,
             after={"chars": len(text), "batch_file": batch_file},
             actor=actor or "system")
    conn.commit()


def latest_draft(conn, cycle_id, country_id, region_id, section_code):
    q = ("SELECT * FROM narrative_drafts WHERE cycle_id=? AND country_id=?"
         " AND section_code=? AND (region_id IS ? OR region_id=?)"
         " ORDER BY id DESC LIMIT 1")
    return conn.execute(q, (cycle_id, country_id, section_code,
                            region_id, region_id or -1)).fetchone()
