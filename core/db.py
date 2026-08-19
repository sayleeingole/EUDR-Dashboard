"""SQLite access layer. Append-only conventions: no UPDATE/DELETE on evidence
content, decisions, sign-off versions, rules, or audit events — only the narrow
status transitions implemented here."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .source_type import classify_source

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "eudr.sqlite"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SEEDS_DIR = BASE_DIR / "data" / "seeds"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def audit(conn, event_type, entity, entity_id=None, country=None, section_code=None,
          before=None, after=None, reason=None, actor="system"):
    conn.execute(
        "INSERT INTO audit_log (event_type, entity, entity_id, country, section_code,"
        " before_state, after_state, reason, actor, at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (event_type, entity, str(entity_id) if entity_id is not None else None,
         country, section_code,
         json.dumps(before, ensure_ascii=False) if isinstance(before, (dict, list)) else before,
         json.dumps(after, ensure_ascii=False) if isinstance(after, (dict, list)) else after,
         reason, actor, now()),
    )


def _load_seed(name):
    return json.loads((SEEDS_DIR / name).read_text(encoding="utf-8"))


def _migrate(conn):
    """Additive column migrations for existing DBs — schema.sql's CREATE TABLE
    IF NOT EXISTS only applies to fresh databases."""
    ev_cols = {r["name"] for r in conn.execute("PRAGMA table_info(evidence)")}
    for col in ("confidence", "significance", "req_type", "authority",
               "verification_docs", "applicability", "supply_chain_node",
               "is_mandatory", "alt_document", "mandatory_condition",
               "source_type", "publisher"):
        if col not in ev_cols:
            conn.execute(f"ALTER TABLE evidence ADD COLUMN {col} TEXT")

    req_cols = {r["name"] for r in conn.execute("PRAGMA table_info(legal_requirements)")}
    for col in ("req_type", "authority", "reference_law", "applicability",
               "supply_chain_node", "is_mandatory", "alt_document",
               "mandatory_condition"):
        if col not in req_cols:
            conn.execute(f"ALTER TABLE legal_requirements ADD COLUMN {col} TEXT")

    ci_cols = {r["name"] for r in conn.execute("PRAGMA table_info(checklist_items)")}
    for col in ("notes", "notes_by", "notes_at", "is_mandatory",
               "mandatory_condition", "reference_law", "alt_group"):
        if col not in ci_cols:
            conn.execute(f"ALTER TABLE checklist_items ADD COLUMN {col} TEXT")


def init_db(actor="system"):
    """Create schema and seed reference data (idempotent)."""
    conn = get_conn()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _migrate(conn)

    if conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0] == 0:
        for s in _load_seed("sections.json"):
            conn.execute(
                "INSERT INTO sections (code, article_refs, title, min_scope, rating_scale)"
                " VALUES (?,?,?,?,?)",
                (s["code"], s["article_refs"], s["title"], s["min_scope"], s["rating_scale"]),
            )
        audit(conn, "seed", "sections", after="10 sections seeded", actor=actor)

    if conn.execute("SELECT COUNT(*) FROM legal_areas").fetchone()[0] == 0:
        for a in _load_seed("legal_areas.json"):
            conn.execute("INSERT INTO legal_areas (code, title) VALUES (?,?)",
                         (a["code"], a["title"]))
        audit(conn, "seed", "legal_areas", after="A1-A7 seeded", actor=actor)

    if conn.execute("SELECT COUNT(*) FROM countries").fetchone()[0] == 0:
        for c in _load_seed("countries.json"):
            cur = conn.execute("INSERT INTO countries (name, iso3) VALUES (?,?)",
                               (c["name"], c["iso3"]))
            for r in c["regions"]:
                conn.execute("INSERT INTO regions (country_id, name) VALUES (?,?)",
                             (cur.lastrowid, r))
        audit(conn, "seed", "countries", after="Malaysia + Indonesia seeded", actor=actor)

    if conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0:
        for s in _load_seed("sources.json"):
            conn.execute(
                "INSERT INTO sources (name, publisher, url_pattern, applies_to, status,"
                " added_by, added_at, reason) VALUES (?,?,?,?,'active',?,?,?)",
                (s["name"], s.get("publisher"), s.get("url_pattern"),
                 s.get("applies_to", "all"), actor, now(), "seed whitelist"),
            )
        audit(conn, "seed", "sources", after="source whitelist seeded", actor=actor)

    if conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 0:
        for r in _load_seed("rules.json"):
            conn.execute(
                "INSERT INTO rules (rule_code, version, rule_type, section_code,"
                " condition_text, trigger_rating, suggested_rating, measures, documents,"
                " rationale, status, created_by, created_at)"
                " VALUES (?,1,?,?,?,?,?,?,?,?,'active',?,?)",
                (r["rule_code"], r["rule_type"], r["section_code"], r["condition_text"],
                 r.get("trigger_rating"), r.get("suggested_rating"),
                 json.dumps(r.get("measures"), ensure_ascii=False) if r.get("measures") else None,
                 json.dumps(r.get("documents"), ensure_ascii=False) if r.get("documents") else None,
                 r.get("rationale"), actor, now()),
            )
        audit(conn, "seed", "rules", after="default rule library seeded", actor=actor)

    if conn.execute("SELECT COUNT(*) FROM assessment_cycles").fetchone()[0] == 0:
        year = datetime.now().year
        conn.execute(
            "INSERT INTO assessment_cycles (year, status, opened_by, opened_at)"
            " VALUES (?,'open',?,?)", (year, actor, now()))
        audit(conn, "cycle_opened", "assessment_cycles", entity_id=year, actor=actor)

    conn.commit()
    return conn


# ---------- reference queries ----------

def get_open_cycle(conn):
    return conn.execute(
        "SELECT * FROM assessment_cycles WHERE status='open' ORDER BY year DESC LIMIT 1"
    ).fetchone()


def get_cycles(conn):
    return conn.execute(
        "SELECT * FROM assessment_cycles ORDER BY year DESC"
    ).fetchall()


# ---------- cycle lifecycle ----------

def open_cycle(conn, year, actor):
    """Open a new yearly cycle. Only one cycle may be open at a time."""
    existing_open = get_open_cycle(conn)
    if existing_open:
        raise ValueError(
            f"Cycle {existing_open['year']} is still open — close it before "
            "opening a new one.")
    if conn.execute("SELECT id FROM assessment_cycles WHERE year=?",
                    (year,)).fetchone():
        raise ValueError(f"Cycle {year} already exists.")
    cur = conn.execute(
        "INSERT INTO assessment_cycles (year, status, opened_by, opened_at)"
        " VALUES (?,'open',?,?)", (year, actor, now()))
    audit(conn, "cycle_opened", "assessment_cycles", entity_id=cur.lastrowid,
          after={"year": year}, actor=actor)
    conn.commit()
    return cur.lastrowid


def close_cycle(conn, cycle_id, actor):
    """Freeze a cycle. Signed assessments and approved evidence are already
    immutable; this just blocks further drafts/signing against it."""
    cyc = conn.execute("SELECT * FROM assessment_cycles WHERE id=?",
                       (cycle_id,)).fetchone()
    if cyc is None or cyc["status"] != "open":
        raise ValueError("Only an open cycle can be closed.")
    conn.execute(
        "UPDATE assessment_cycles SET status='closed', closed_by=?,"
        " closed_at=? WHERE id=?", (actor, now(), cycle_id))
    audit(conn, "cycle_closed", "assessment_cycles", entity_id=cycle_id,
          after={"year": cyc["year"]}, actor=actor)
    conn.commit()


def rollforward(conn, from_cycle_id, to_cycle_id, actor):
    """Carry approved evidence, signed assessments, and relevant legal
    requirements from one cycle into the next. Assessments land as
    'to_reverify' (must be re-signed); legal requirements land as
    'candidate' (must be reconfirmed) — nothing new counts as decided until
    a human re-confirms it in the new cycle."""
    if from_cycle_id == to_cycle_id:
        raise ValueError("Source and target cycle must differ.")
    from_cyc = conn.execute("SELECT * FROM assessment_cycles WHERE id=?",
                            (from_cycle_id,)).fetchone()
    to_cyc = conn.execute("SELECT * FROM assessment_cycles WHERE id=?",
                          (to_cycle_id,)).fetchone()
    if from_cyc is None or to_cyc is None:
        raise ValueError("Unknown cycle.")
    if to_cyc["status"] != "open":
        raise ValueError("Target cycle must be open.")

    # 1. approved evidence — carried as already-approved, flagged for traceability
    id_map = {}
    ev_rows = conn.execute(
        "SELECT * FROM evidence WHERE cycle_id=? AND status='approved'",
        (from_cycle_id,)).fetchall()
    for e in ev_rows:
        cur = conn.execute(
            "INSERT INTO evidence (cycle_id, country_id, region_id, section_code,"
            " claim, value, source_id, source_name, url, published, retrieved,"
            " origin, batch_file, notes, status, flag, supersedes_id, created_by,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'approved',"
            " 'rolled-forward', NULL, ?, ?)",
            (to_cycle_id, e["country_id"], e["region_id"], e["section_code"],
             e["claim"], e["value"], e["source_id"], e["source_name"], e["url"],
             e["published"], e["retrieved"], e["origin"], e["batch_file"],
             e["notes"], actor, now()))
        id_map[e["id"]] = cur.lastrowid

    # 2. latest signed assessment per scope -> new to_reverify draft, version 1
    scopes = conn.execute(
        "SELECT DISTINCT country_id, region_id, section_code FROM assessments"
        " WHERE cycle_id=?", (from_cycle_id,)).fetchall()
    assessments_copied = 0
    for s in scopes:
        a = current_assessment(conn, from_cycle_id, s["country_id"],
                               s["region_id"], s["section_code"])
        if a is None or a["status"] != "signed":
            continue
        old_ids = json.loads(a["evidence_ids"]) if a["evidence_ids"] else []
        new_ids = [id_map[i] for i in old_ids if i in id_map]
        conn.execute(
            "INSERT INTO assessments (cycle_id, country_id, region_id,"
            " section_code, version, suggested_rating, rule_trace,"
            " confirmed_rating, override_reason, narrative, evidence_ids,"
            " status) VALUES (?,?,?,?,1,?,?,?,?,?,?,'to_reverify')",
            (to_cycle_id, s["country_id"], s["region_id"], s["section_code"],
             a["suggested_rating"], a["rule_trace"], a["confirmed_rating"],
             a["override_reason"], a["narrative"], json.dumps(new_ids)))
        assessments_copied += 1

    # 3. relevant legal requirements -> candidate (must be reconfirmed)
    reqs = conn.execute(
        "SELECT * FROM legal_requirements WHERE cycle_id=? AND relevance='relevant'",
        (from_cycle_id,)).fetchall()
    for r in reqs:
        conn.execute(
            "INSERT INTO legal_requirements (cycle_id, country_id, region_scope,"
            " area_code, instrument_id, requirement, provision, relevance,"
            " relevance_reason, verification_docs, reference_law, created_by,"
            " created_at)"
            " VALUES (?,?,?,?,?,?,?,'candidate',?,NULL,?,?,?)",
            (to_cycle_id, r["country_id"], r["region_scope"], r["area_code"],
             r["instrument_id"], r["requirement"], r["provision"],
             f"Rolled forward from cycle {from_cyc['year']} — reverify for"
             f" {to_cyc['year']}.", r["reference_law"], actor, now()))

    # 4. narrative drafts — carry the latest draft per scope forward too, else
    #    it stays stamped with the old cycle_id and silently disappears from
    #    view the moment its evidence's cycle moves on (latest_draft() filters
    #    strictly by cycle_id).
    scopes_with_evidence = {(e["country_id"], e["region_id"], e["section_code"])
                            for e in ev_rows}
    drafts_copied = 0
    for country_id, region_id, section_code in scopes_with_evidence:
        draft = conn.execute(
            "SELECT * FROM narrative_drafts WHERE cycle_id=? AND country_id=?"
            " AND section_code=? AND (region_id IS ? OR region_id=?)"
            " ORDER BY id DESC LIMIT 1",
            (from_cycle_id, country_id, section_code, region_id,
             region_id or -1)).fetchone()
        if draft is None:
            continue
        conn.execute(
            "INSERT INTO narrative_drafts (cycle_id, country_id, region_id,"
            " section_code, text, sources, batch_file, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (to_cycle_id, country_id, region_id, section_code, draft["text"],
             draft["sources"], draft["batch_file"], now()))
        drafts_copied += 1

    audit(conn, "cycle_rolled_forward", "assessment_cycles", entity_id=to_cycle_id,
          after={"from_year": from_cyc["year"], "to_year": to_cyc["year"],
                 "evidence": len(id_map), "assessments": assessments_copied,
                 "requirements": len(reqs), "narrative_drafts": drafts_copied},
          actor=actor)
    conn.commit()
    return {"evidence": len(id_map), "assessments": assessments_copied,
            "requirements": len(reqs), "narrative_drafts": drafts_copied}


def _scope_ratings(conn, cycle_id):
    """Latest confirmed rating per (country, region, section) for a cycle,
    considering only assessments a human has actually decided on."""
    rows = conn.execute(
        "SELECT DISTINCT country_id, region_id, section_code FROM assessments"
        " WHERE cycle_id=?", (cycle_id,)).fetchall()
    result = {}
    for r in rows:
        a = current_assessment(conn, cycle_id, r["country_id"], r["region_id"],
                               r["section_code"])
        if a and a["status"] in ("signed", "to_reverify"):
            result[(r["country_id"], r["region_id"], r["section_code"])] = \
                a["confirmed_rating"]
    return result


def year_over_year_delta(conn, cycle_id, prev_cycle_id):
    """What changed rating, what's new, what was dropped between two cycles."""
    cur = _scope_ratings(conn, cycle_id)
    prev = _scope_ratings(conn, prev_cycle_id)
    out = []
    for scope in set(cur) | set(prev):
        country_id, region_id, section_code = scope
        country = conn.execute("SELECT name FROM countries WHERE id=?",
                               (country_id,)).fetchone()
        region = conn.execute("SELECT name FROM regions WHERE id=?",
                              (region_id,)).fetchone() if region_id else None
        prev_r, cur_r = prev.get(scope), cur.get(scope)
        if prev_r is None and cur_r is not None:
            change = "new"
        elif prev_r is not None and cur_r is None:
            change = "dropped"
        elif prev_r != cur_r:
            change = "changed"
        else:
            change = "same"
        out.append({
            "country": country["name"] if country else None,
            "region": region["name"] if region else None,
            "section_code": section_code,
            "prev_rating": prev_r,
            "curr_rating": cur_r,
            "change": change,
        })
    out.sort(key=lambda d: (d["country"] or "", d["region"] or "", d["section_code"]))
    return out


def get_countries(conn):
    return conn.execute("SELECT * FROM countries ORDER BY name").fetchall()


def get_regions(conn, country_id):
    return conn.execute(
        "SELECT * FROM regions WHERE country_id=? ORDER BY name", (country_id,)
    ).fetchall()


def get_sections(conn):
    return conn.execute("SELECT * FROM sections ORDER BY id").fetchall()


def get_legal_areas(conn):
    return conn.execute("SELECT * FROM legal_areas ORDER BY code").fetchall()


def get_active_sources(conn):
    return conn.execute(
        "SELECT * FROM sources WHERE status='active' ORDER BY name"
    ).fetchall()


# ---------- trusted sources (the "whitelist") ----------

def list_sources(conn):
    """Every source with how much evidence cites it — for the Trusted
    sources page. Evidence count is what makes a name-only entry worth
    keeping (or a domain worth attaching)."""
    return conn.execute(
        "SELECT s.*, COUNT(e.id) AS n_evidence,"
        " SUM(CASE WHEN e.status='approved' THEN 1 ELSE 0 END) AS n_approved"
        " FROM sources s LEFT JOIN evidence e ON e.source_id=s.id"
        " GROUP BY s.id ORDER BY s.status, LOWER(s.name)").fetchall()


def _clean_domain(url_pattern):
    """'https://www.walhi.or.id/x' -> 'walhi.or.id'; plain 'walhi.or.id' unchanged."""
    from .gov_sources import host_of
    v = (url_pattern or "").strip().lower()
    if not v:
        return None
    host = host_of(v) if ("/" in v or "//" in v) else v
    host = host or v
    if host.startswith("www."):
        host = host[4:]
    return host or None


def add_source(conn, name, url_pattern, applies_to, actor, publisher=None, reason=None):
    """Add a trusted source directly (Settings), by name and/or domain. A
    domain makes every future article from that website trusted, which is
    the whole point — name-only entries only match one article title."""
    name = (name or "").strip()
    domain = _clean_domain(url_pattern)
    if not name and not domain:
        raise ValueError("Give at least a name or a website domain.")
    if not name:
        name = domain
    applies_to = (applies_to or "all").strip() or "all"
    dup = conn.execute(
        "SELECT id, name FROM sources WHERE status='active' AND"
        " (LOWER(name)=LOWER(?) OR (url_pattern IS NOT NULL AND url_pattern=?))",
        (name, domain)).fetchone()
    if dup:
        raise ValueError(f"Already trusted: {dup['name']}.")
    cur = conn.execute(
        "INSERT INTO sources (name, publisher, url_pattern, applies_to, status,"
        " added_by, added_at, reason) VALUES (?,?,?,?,'active',?,?,?)",
        (name, (publisher or "").strip() or None, domain, applies_to, actor, now(),
         (reason or "").strip() or None))
    source_id = cur.lastrowid
    # Any pending records from this website/name are unblocked immediately.
    unblocked = _unflag_matching(conn, source_id, name, domain)
    audit(conn, "source_added", "sources", entity_id=source_id,
          after={"name": name, "url_pattern": domain, "applies_to": applies_to,
                 "unblocked_records": unblocked, "via": "settings"},
          reason=reason, actor=actor)
    conn.commit()
    return source_id


def _unflag_matching(conn, source_id, name, domain):
    """Clear the unlisted-source flag on pending records citing this name or
    website. Returns the ids touched."""
    rows = conn.execute(
        "SELECT id, source_name, url FROM evidence WHERE flag='unlisted-source'"
        " AND status='pending'").fetchall()
    hit = []
    name_l = (name or "").lower()
    for r in rows:
        sn = (r["source_name"] or "").lower()
        by_name = bool(name_l) and (sn == name_l or name_l in sn or sn in name_l)
        by_dom = bool(domain) and domain in (r["url"] or "").lower()
        if by_name or by_dom:
            conn.execute("UPDATE evidence SET flag=NULL, source_id=? WHERE id=?",
                         (source_id, r["id"]))
            hit.append(r["id"])
    return hit


def set_source_status(conn, source_id, status, reason, actor):
    """Retire (stop trusting) or reactivate a source. Retiring does not touch
    evidence already approved — that was a human decision at the time and
    stays in the audit trail; it only affects future imports."""
    if status not in ("active", "retired"):
        raise ValueError("Status must be active or retired.")
    src = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if src is None:
        raise ValueError("Unknown source.")
    if src["status"] == status:
        return
    if status == "retired" and not (reason and reason.strip()):
        raise ValueError("Retiring a source needs a reason.")
    conn.execute("UPDATE sources SET status=? WHERE id=?", (status, source_id))
    audit(conn, "source_retired" if status == "retired" else "source_reactivated",
          "sources", entity_id=source_id,
          before={"name": src["name"], "status": src["status"]},
          after={"status": status}, reason=reason, actor=actor)
    conn.commit()


def set_source_domain(conn, source_id, url_pattern, actor):
    """Attach a website domain to a name-only entry (or change it), so the
    trust follows the website rather than one article title."""
    src = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if src is None:
        raise ValueError("Unknown source.")
    domain = _clean_domain(url_pattern)
    if not domain:
        raise ValueError("Enter a website domain, e.g. walhi.or.id.")
    conn.execute("UPDATE sources SET url_pattern=? WHERE id=?", (domain, source_id))
    unblocked = _unflag_matching(conn, source_id, None, domain) if src["status"] == "active" else []
    audit(conn, "source_domain_set", "sources", entity_id=source_id,
          before={"name": src["name"], "url_pattern": src["url_pattern"]},
          after={"url_pattern": domain, "unblocked_records": unblocked}, actor=actor)
    conn.commit()
    return domain


def set_checklist_item_notes(conn, item_id, notes, actor):
    """Reviewer's own short remark on one checklist line — separate from the
    system-generated justification, editable, not part of the audited chain."""
    item = conn.execute("SELECT * FROM checklist_items WHERE id=?", (item_id,)).fetchone()
    if item is None:
        raise ValueError("Unknown checklist item.")
    notes = (notes or "").strip() or None
    conn.execute(
        "UPDATE checklist_items SET notes=?, notes_by=?, notes_at=? WHERE id=?",
        (notes, actor, now(), item_id))
    audit(conn, "checklist_item_note_saved", "checklist_items", entity_id=item_id,
          before={"notes": item["notes"]}, after={"notes": notes}, actor=actor)
    conn.commit()


def exclude_checklist_document(conn, country_id, region_id, document_name, actor):
    """Permanently hide one document from a country's (or region's) checklist
    — applied at read time in checklist.latest_generation, so it stays hidden
    across future regenerations and exports until restored. Stored with its
    original casing (for display in the restore list); matching against
    generated items is done case-insensitively by the caller."""
    document_name = (document_name or "").strip()
    if not document_name:
        raise ValueError("No document name given.")
    cur = conn.execute(
        "INSERT INTO checklist_exclusions (country_id, region_id, document_name,"
        " status, excluded_by, excluded_at) VALUES (?,?,?,'excluded',?,?)",
        (country_id, region_id, document_name, actor, now()))
    audit(conn, "checklist_document_excluded", "checklist_exclusions",
          entity_id=cur.lastrowid, after={"document_name": document_name,
          "region_id": region_id}, actor=actor)
    conn.commit()


def restore_checklist_document(conn, exclusion_id, actor):
    row = conn.execute("SELECT * FROM checklist_exclusions WHERE id=?",
                       (exclusion_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown exclusion.")
    conn.execute(
        "UPDATE checklist_exclusions SET status='restored', restored_by=?,"
        " restored_at=? WHERE id=?", (actor, now(), exclusion_id))
    audit(conn, "checklist_document_restored", "checklist_exclusions",
          entity_id=exclusion_id, before={"document_name": row["document_name"]},
          actor=actor)
    conn.commit()


def get_checklist_exclusions(conn, country_id, region_id, status="excluded"):
    return conn.execute(
        "SELECT * FROM checklist_exclusions WHERE country_id=? AND region_id IS ?"
        " AND status=? ORDER BY excluded_at DESC",
        (country_id, region_id, status)).fetchall()


def rename_checklist_document(conn, country_id, region_id, original_name, new_name, actor):
    """Permanent display-name override for a generated checklist document,
    matched by name (case-insensitively) — applies wherever that document
    shows up for this country/region, across every future regeneration."""
    original_name = (original_name or "").strip()
    new_name = (new_name or "").strip()
    if not original_name or not new_name:
        raise ValueError("Missing document name.")
    if original_name.lower() == new_name.lower():
        return
    cur = conn.execute(
        "INSERT INTO checklist_renames (country_id, region_id, original_name,"
        " new_name, status, renamed_by, renamed_at) VALUES (?,?,?,?,'active',?,?)",
        (country_id, region_id, original_name, new_name, actor, now()))
    audit(conn, "checklist_document_renamed", "checklist_renames",
          entity_id=cur.lastrowid,
          before={"original_name": original_name}, after={"new_name": new_name}, actor=actor)
    conn.commit()


def revert_checklist_rename(conn, rename_id, actor):
    row = conn.execute("SELECT * FROM checklist_renames WHERE id=?", (rename_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown rename.")
    conn.execute(
        "UPDATE checklist_renames SET status='reverted', reverted_by=?,"
        " reverted_at=? WHERE id=?", (actor, now(), rename_id))
    audit(conn, "checklist_rename_reverted", "checklist_renames", entity_id=rename_id,
          before={"new_name": row["new_name"]}, after={"original_name": row["original_name"]},
          actor=actor)
    conn.commit()


def get_checklist_renames(conn, country_id, region_id, status="active"):
    return conn.execute(
        "SELECT * FROM checklist_renames WHERE country_id=? AND region_id IS ?"
        " AND status=? ORDER BY renamed_at DESC",
        (country_id, region_id, status)).fetchall()


def add_checklist_document(conn, country_id, region_id, document_name, grouping, note, actor):
    document_name = (document_name or "").strip()
    grouping = (grouping or "").strip()
    if not document_name:
        raise ValueError("Enter a document name.")
    if not grouping:
        raise ValueError("Choose which section this belongs under.")
    cur = conn.execute(
        "INSERT INTO checklist_additions (country_id, region_id, document_name,"
        " grouping, note, status, added_by, added_at) VALUES (?,?,?,?,?,'active',?,?)",
        (country_id, region_id, document_name, grouping, (note or "").strip() or None,
         actor, now()))
    audit(conn, "checklist_document_added", "checklist_additions", entity_id=cur.lastrowid,
          after={"document_name": document_name, "grouping": grouping}, actor=actor)
    conn.commit()
    return cur.lastrowid


def remove_checklist_addition(conn, addition_id, actor):
    row = conn.execute("SELECT * FROM checklist_additions WHERE id=?", (addition_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown addition.")
    conn.execute(
        "UPDATE checklist_additions SET status='removed', removed_by=?,"
        " removed_at=? WHERE id=?", (actor, now(), addition_id))
    audit(conn, "checklist_addition_removed", "checklist_additions", entity_id=addition_id,
          before={"document_name": row["document_name"]}, actor=actor)
    conn.commit()


def restore_checklist_addition(conn, addition_id, actor):
    row = conn.execute("SELECT * FROM checklist_additions WHERE id=?", (addition_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown addition.")
    conn.execute(
        "UPDATE checklist_additions SET status='active', removed_by=NULL,"
        " removed_at=NULL WHERE id=?", (addition_id,))
    audit(conn, "checklist_addition_restored", "checklist_additions", entity_id=addition_id,
          after={"document_name": row["document_name"]}, actor=actor)
    conn.commit()


def get_checklist_additions(conn, country_id, region_id, status="active"):
    return conn.execute(
        "SELECT * FROM checklist_additions WHERE country_id=? AND region_id IS ?"
        " AND status=? ORDER BY added_at", (country_id, region_id, status)).fetchall()


def set_checklist_addition_note(conn, addition_id, note, actor):
    row = conn.execute("SELECT * FROM checklist_additions WHERE id=?", (addition_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown addition.")
    note = (note or "").strip() or None
    conn.execute(
        "UPDATE checklist_additions SET note=?, note_by=?, note_at=? WHERE id=?",
        (note, actor, now(), addition_id))
    audit(conn, "checklist_addition_note_saved", "checklist_additions", entity_id=addition_id,
          before={"note": row["note"]}, after={"note": note}, actor=actor)
    conn.commit()


def add_country(conn, name, iso3, actor):
    cur = conn.execute("INSERT INTO countries (name, iso3) VALUES (?,?)", (name, iso3))
    audit(conn, "country_added", "countries", entity_id=cur.lastrowid,
          country=name, actor=actor)
    conn.commit()
    return cur.lastrowid


def add_region(conn, country_id, name, actor):
    country = conn.execute("SELECT name FROM countries WHERE id=?", (country_id,)).fetchone()
    cur = conn.execute("INSERT INTO regions (country_id, name) VALUES (?,?)",
                       (country_id, name))
    audit(conn, "region_added", "regions", entity_id=cur.lastrowid,
          country=country["name"], after=name, actor=actor)
    conn.commit()
    return cur.lastrowid


# ---------- evidence ----------

_RATING_SCALE = ("low", "medium", "high")
_REQ_TYPES = ("instrument", "requirement", "jurisprudence", "treaty", "policy")


_APPLICABILITY = ("plantation", "smallholder", "both")
_MANDATORY = ("yes", "no", "conditional")


def add_evidence(conn, *, cycle_id, country_id, region_id, section_code, claim,
                 value, source_id, source_name, url, published, retrieved,
                 origin, actor, batch_file=None, notes=None, supersedes_id=None,
                 confidence=None, significance=None, req_type=None, authority=None,
                 verification_docs=None, applicability=None, supply_chain_node=None,
                 is_mandatory=None, alt_document=None, mandatory_condition=None,
                 source_type=None, publisher=None):
    flag = None if source_id else "unlisted-source"
    confidence = confidence if confidence in _RATING_SCALE else None
    significance = significance if significance in _RATING_SCALE else None
    req_type = req_type if req_type in _REQ_TYPES else None
    authority = authority.strip() if authority and authority.strip() else None
    docs_json = (json.dumps(verification_docs, ensure_ascii=False)
                if verification_docs else None)
    applicability = applicability if applicability in _APPLICABILITY else None
    supply_chain_node = supply_chain_node.strip() if supply_chain_node and supply_chain_node.strip() else None
    is_mandatory = is_mandatory if is_mandatory in _MANDATORY else None
    alt_document = alt_document.strip() if alt_document and alt_document.strip() else None
    mandatory_condition = (mandatory_condition.strip()
                           if mandatory_condition and mandatory_condition.strip() else None)
    if source_type is None:
        source_type = classify_source(source_name, url)
    publisher = publisher.strip() if publisher and publisher.strip() else None
    country = conn.execute("SELECT name FROM countries WHERE id=?", (country_id,)).fetchone()
    cur = conn.execute(
        "INSERT INTO evidence (cycle_id, country_id, region_id, section_code, claim,"
        " value, source_id, source_name, publisher, url, published, retrieved, origin, batch_file,"
        " notes, status, flag, confidence, significance, req_type, authority,"
        " verification_docs, applicability, supply_chain_node, is_mandatory,"
        " alt_document, mandatory_condition, source_type, supersedes_id, created_by,"
        " created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cycle_id, country_id, region_id, section_code, claim, value, source_id,
         source_name, publisher, url, published, retrieved, origin, batch_file, notes, flag,
         confidence, significance, req_type, authority, docs_json, applicability,
         supply_chain_node, is_mandatory, alt_document, mandatory_condition,
         source_type, supersedes_id, actor, now()),
    )
    audit(conn, "evidence_added", "evidence", entity_id=cur.lastrowid,
          country=country["name"], section_code=section_code,
          after={"claim": claim, "source": source_name, "origin": origin,
                 "flag": flag}, actor=actor)
    conn.commit()
    return cur.lastrowid


def decide_evidence(conn, evidence_id, decision, reason, actor):
    ev = conn.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    if ev is None or ev["status"] != "pending":
        raise ValueError("Only pending evidence can be decided.")
    if decision == "approved" and ev["flag"] == "unlisted-source":
        raise ValueError("Unlisted source: approve or reject the source first.")
    if decision == "rejected" and not (reason and reason.strip()):
        raise ValueError("Rejection requires a reason.")
    conn.execute("UPDATE evidence SET status=? WHERE id=?", (decision, evidence_id))
    if decision == "approved" and ev["supersedes_id"]:
        conn.execute("UPDATE evidence SET status='superseded' WHERE id=?",
                     (ev["supersedes_id"],))
        audit(conn, "evidence_superseded", "evidence", entity_id=ev["supersedes_id"],
              section_code=ev["section_code"],
              reason=f"superseded by evidence #{evidence_id}", actor=actor)
    conn.execute(
        "INSERT INTO evidence_decisions (evidence_id, decision, reason, decided_by,"
        " decided_at) VALUES (?,?,?,?,?)",
        (evidence_id, decision, reason, actor, now()))
    # Approved legal-area evidence (A1..A7) becomes a candidate requirement.
    if decision == "approved" and ev["section_code"].startswith("A"):
        region_scope = None
        if ev["region_id"]:
            rg = conn.execute("SELECT name FROM regions WHERE id=?",
                              (ev["region_id"],)).fetchone()
            region_scope = rg["name"] if rg else None
        conn.execute(
            "INSERT INTO legal_requirements (cycle_id, country_id, region_scope,"
            " area_code, requirement, provision, relevance, req_type, authority,"
            " verification_docs, reference_law, applicability, supply_chain_node,"
            " is_mandatory, alt_document, mandatory_condition, created_by, created_at)"
            " VALUES (?,?,?,?,?,?,'candidate',?,?,?,?,?,?,?,?,?,?,?)",
            (ev["cycle_id"], ev["country_id"], region_scope, ev["section_code"],
             ev["claim"], ev["notes"], ev["req_type"], ev["authority"],
             ev["verification_docs"], ev["source_name"], ev["applicability"],
             ev["supply_chain_node"], ev["is_mandatory"], ev["alt_document"],
             ev["mandatory_condition"], actor, now()))
    country = conn.execute("SELECT name FROM countries WHERE id=?",
                           (ev["country_id"],)).fetchone()
    audit(conn, f"evidence_{decision}", "evidence", entity_id=evidence_id,
          country=country["name"], section_code=ev["section_code"],
          before=ev["claim"][:200], reason=reason, actor=actor)
    conn.commit()


UNDO_WINDOW_S = 60


def undo_decision(conn, evidence_id, actor):
    """Reverse an evidence approve/reject within a short window, before any
    later action could plausibly depend on it. Used by the evidence queue's
    undo affordance (docs/08 §4.3) so a stray click doesn't silently write an
    unwanted decision to the audit trail. The original decision row is left
    in place (status flips back, nothing deleted) so the trail stays
    append-only — the undo itself is a new audited event."""
    ev = conn.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    if ev is None or ev["status"] not in ("approved", "rejected"):
        raise ValueError("Only a just-decided record can be undone.")
    last_decision = conn.execute(
        "SELECT * FROM evidence_decisions WHERE evidence_id=? ORDER BY id DESC LIMIT 1",
        (evidence_id,)).fetchone()
    if last_decision is None:
        raise ValueError("No decision to undo.")
    decided_at = datetime.fromisoformat(last_decision["decided_at"])
    if (datetime.now() - decided_at).total_seconds() > UNDO_WINDOW_S:
        raise ValueError("Undo window has expired — decide again if this was wrong.")
    conn.execute("UPDATE evidence SET status='pending' WHERE id=?", (evidence_id,))
    country = conn.execute("SELECT name FROM countries WHERE id=?",
                           (ev["country_id"],)).fetchone()
    audit(conn, "evidence_decision_undone", "evidence", entity_id=evidence_id,
          country=country["name"], section_code=ev["section_code"],
          before=last_decision["decision"], actor=actor)
    conn.commit()


def approve_source(conn, evidence_id, applies_to, reason, actor, trust_scope="article"):
    """Two-step control: approve the SOURCE of an unlisted-source record.
    `trust_scope`: 'article' (default) trusts only this exact citation by
    name — the lower-risk choice, and the historical default behaviour.
    'website' trusts the whole domain the record was retrieved from, so
    every future article from that site is pre-trusted too — a reviewer
    picks this deliberately for a site they're confident in; it is not the
    safe default (e.g. a platform hosting many unrelated authors shouldn't
    be blanket-trusted just because one of its articles checked out)."""
    from .gov_sources import host_of
    ev = conn.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    if ev is None or ev["flag"] != "unlisted-source":
        raise ValueError("Record is not flagged unlisted-source.")
    domain = host_of(ev["url"]) if (trust_scope == "website" and ev["url"]) else None
    cur = conn.execute(
        "INSERT INTO sources (name, publisher, url_pattern, applies_to, status,"
        " added_by, added_at, reason) VALUES (?,?,?,?,'active',?,?,?)",
        (ev["source_name"], None, domain, applies_to or ev["section_code"],
         actor, now(), reason))
    source_id = cur.lastrowid
    unblocked = _unflag_matching(conn, source_id, ev["source_name"], domain)
    audit(conn, "source_added", "sources", entity_id=source_id,
          after={"name": ev["source_name"], "url_pattern": domain,
                 "applies_to": applies_to, "trust_scope": trust_scope,
                 "unblocked_records": unblocked},
          reason=reason, actor=actor)
    conn.commit()
    return source_id


def pending_evidence(conn, cycle_id, country_id=None):
    q = ("SELECT e.*, c.name AS country_name, r.name AS region_name FROM evidence e"
         " JOIN countries c ON c.id=e.country_id"
         " LEFT JOIN regions r ON r.id=e.region_id"
         " WHERE e.status='pending' AND e.cycle_id=?")
    params = [cycle_id]
    if country_id:
        q += " AND e.country_id=?"
        params.append(country_id)
    return conn.execute(q + " ORDER BY e.id", params).fetchall()


def evidence_counts_by_code(conn, cycle_id, country_id, region_id):
    """Evidence record count per section/legal-area code, for this country
    (or region) and cycle — one query, used to show "already researched"
    indicators next to a scope checklist instead of one query per row."""
    rows = conn.execute(
        "SELECT section_code, COUNT(*) AS n FROM evidence WHERE cycle_id=?"
        " AND country_id=? AND (region_id IS ? OR region_id=?)"
        " GROUP BY section_code",
        (cycle_id, country_id, region_id, region_id or -1)).fetchall()
    return {r["section_code"]: r["n"] for r in rows}


def evidence_counts(conn, cycle_id, country_id, region_id, section_code):
    """Counts scoped to country level (region NULL) or a specific region."""
    q = ("SELECT status, COUNT(*) AS n FROM evidence WHERE cycle_id=? AND country_id=?"
         " AND section_code=? AND (region_id IS ? OR region_id=?) GROUP BY status")
    rows = conn.execute(q, (cycle_id, country_id, section_code,
                            region_id, region_id or -1)).fetchall()
    return {r["status"]: r["n"] for r in rows}


def approved_evidence(conn, cycle_id, country_id, region_id, section_code):
    q = ("SELECT * FROM evidence WHERE cycle_id=? AND country_id=? AND section_code=?"
         " AND status='approved' AND (region_id IS ? OR region_id=?) ORDER BY id")
    return conn.execute(q, (cycle_id, country_id, section_code,
                            region_id, region_id or -1)).fetchall()


# ---------- assessments ----------

def current_assessment(conn, cycle_id, country_id, region_id, section_code):
    q = ("SELECT * FROM assessments WHERE cycle_id=? AND country_id=? AND section_code=?"
         " AND (region_id IS ? OR region_id=?) ORDER BY version DESC LIMIT 1")
    return conn.execute(q, (cycle_id, country_id, section_code,
                            region_id, region_id or -1)).fetchone()


def assessment_history(conn, cycle_id, country_id, region_id, section_code):
    q = ("SELECT * FROM assessments WHERE cycle_id=? AND country_id=? AND section_code=?"
         " AND (region_id IS ? OR region_id=?) AND status='signed'"
         " ORDER BY version DESC")
    return conn.execute(q, (cycle_id, country_id, section_code,
                            region_id, region_id or -1)).fetchall()


def save_draft(conn, *, cycle_id, country_id, region_id, section_code,
               suggested_rating, rule_trace, confirmed_rating, override_reason,
               narrative, actor):
    """One editable draft row per scope; signing freezes it as a version."""
    cur = current_assessment(conn, cycle_id, country_id, region_id, section_code)
    if cur and cur["status"] == "draft":
        conn.execute(
            "UPDATE assessments SET suggested_rating=?, rule_trace=?,"
            " confirmed_rating=?, override_reason=?, narrative=? WHERE id=?",
            (suggested_rating, rule_trace, confirmed_rating, override_reason,
             narrative, cur["id"]))
        draft_id = cur["id"]
    else:
        version = (cur["version"] + 1) if cur else 1
        c = conn.execute(
            "INSERT INTO assessments (cycle_id, country_id, region_id, section_code,"
            " version, suggested_rating, rule_trace, confirmed_rating,"
            " override_reason, narrative, status)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,'draft')",
            (cycle_id, country_id, region_id, section_code, version,
             suggested_rating, rule_trace, confirmed_rating, override_reason,
             narrative))
        draft_id = c.lastrowid
    country = conn.execute("SELECT name FROM countries WHERE id=?",
                           (country_id,)).fetchone()
    audit(conn, "assessment_draft_saved", "assessments", entity_id=draft_id,
          country=country["name"], section_code=section_code,
          after={"confirmed_rating": confirmed_rating}, actor=actor)
    conn.commit()
    return draft_id


def sign_assessment(conn, *, cycle_id, country_id, region_id, section_code,
                    suggested_rating, rule_trace, confirmed_rating,
                    override_reason, narrative, actor):
    """Freeze the draft as a signed version with its evidence set."""
    if not confirmed_rating:
        raise ValueError("A confirmed rating is required to sign.")
    if not (narrative and narrative.strip()):
        raise ValueError("A narrative conclusion is required to sign.")
    if suggested_rating and confirmed_rating != suggested_rating \
            and not (override_reason and override_reason.strip()):
        raise ValueError("Overriding the suggested rating requires a reason.")
    ev = approved_evidence(conn, cycle_id, country_id, region_id, section_code)
    evidence_ids = json.dumps([e["id"] for e in ev])
    cur = current_assessment(conn, cycle_id, country_id, region_id, section_code)
    if cur and cur["status"] == "draft":
        conn.execute(
            "UPDATE assessments SET suggested_rating=?, rule_trace=?,"
            " confirmed_rating=?, override_reason=?, narrative=?, evidence_ids=?,"
            " status='signed', signed_by=?, signed_at=? WHERE id=?",
            (suggested_rating, rule_trace, confirmed_rating, override_reason,
             narrative, evidence_ids, actor, now(), cur["id"]))
        signed_id, version = cur["id"], cur["version"]
    else:
        version = (cur["version"] + 1) if cur else 1
        c = conn.execute(
            "INSERT INTO assessments (cycle_id, country_id, region_id, section_code,"
            " version, suggested_rating, rule_trace, confirmed_rating,"
            " override_reason, narrative, evidence_ids, status, signed_by, signed_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,'signed',?,?)",
            (cycle_id, country_id, region_id, section_code, version,
             suggested_rating, rule_trace, confirmed_rating, override_reason,
             narrative, evidence_ids, actor, now()))
        signed_id = c.lastrowid
    country = conn.execute("SELECT name FROM countries WHERE id=?",
                           (country_id,)).fetchone()
    audit(conn, "assessment_signed", "assessments", entity_id=signed_id,
          country=country["name"], section_code=section_code,
          after={"version": version, "suggested": suggested_rating,
                 "confirmed": confirmed_rating,
                 "override_reason": override_reason,
                 "evidence_count": len(ev)},
          actor=actor)
    conn.commit()
    return signed_id, version


def reopen_assessment(conn, assessment_id, reason, actor):
    """Signed versions stay frozen; reopening creates a new draft version."""
    if not (reason and reason.strip()):
        raise ValueError("Reopening requires a reason.")
    cur = conn.execute("SELECT * FROM assessments WHERE id=?",
                       (assessment_id,)).fetchone()
    if cur is None or cur["status"] != "signed":
        raise ValueError("Only signed assessments can be reopened.")
    c = conn.execute(
        "INSERT INTO assessments (cycle_id, country_id, region_id, section_code,"
        " version, suggested_rating, rule_trace, confirmed_rating, override_reason,"
        " narrative, status)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,'draft')",
        (cur["cycle_id"], cur["country_id"], cur["region_id"], cur["section_code"],
         cur["version"] + 1, cur["suggested_rating"], cur["rule_trace"],
         cur["confirmed_rating"], cur["override_reason"], cur["narrative"]))
    country = conn.execute("SELECT name FROM countries WHERE id=?",
                           (cur["country_id"],)).fetchone()
    audit(conn, "assessment_reopened", "assessments", entity_id=assessment_id,
          country=country["name"], section_code=cur["section_code"],
          reason=reason, actor=actor)
    conn.commit()
    return c.lastrowid


def consolidate_duplicates(conn, cycle_id, country_id, section_code, actor):
    """Fuzzy-dedup approved evidence for one section: the earliest record of a
    duplicate group is kept; later ones become 'superseded' (audited, never
    deleted). Returns number of records superseded."""
    from .importer import is_duplicate
    rows = conn.execute(
        "SELECT * FROM evidence WHERE cycle_id=? AND country_id=?"
        " AND section_code=? AND status='approved' ORDER BY id",
        (cycle_id, country_id, section_code)).fetchall()
    superseded = 0
    kept = []
    for ev in rows:
        match = next((k for k in kept if is_duplicate(ev["claim"], k["claim"])),
                     None)
        if match is None:
            kept.append(ev)
            continue
        conn.execute("UPDATE evidence SET status='superseded',"
                     " supersedes_id=? WHERE id=?", (match["id"], ev["id"]))
        audit(conn, "evidence_superseded", "evidence", entity_id=ev["id"],
              section_code=section_code,
              reason=f"duplicate consolidation — kept #{match['id']}",
              actor=actor)
        superseded += 1
    if superseded:
        conn.commit()
    return superseded


# ---------- legal requirements ----------

def get_requirements(conn, cycle_id, country_id, relevance=None):
    q = ("SELECT * FROM legal_requirements WHERE cycle_id=? AND country_id=?")
    params = [cycle_id, country_id]
    if relevance:
        q += " AND relevance=?"
        params.append(relevance)
    return conn.execute(q + " ORDER BY area_code, id", params).fetchall()


def reopen_requirement(conn, req_id, reason, actor):
    """Undo a relevant/not_relevant decision, back to candidate, so it can be
    re-accepted or re-rejected. Unlike evidence's undo_decision this has no
    time window — legal review corrections can surface long after the fact.
    Previous authority/verification_docs are kept as a prefill, not cleared,
    so the reviewer isn't retyping from scratch."""
    if not (reason and reason.strip()):
        raise ValueError("Reopening requires a reason.")
    req = conn.execute("SELECT * FROM legal_requirements WHERE id=?",
                       (req_id,)).fetchone()
    if req is None:
        raise ValueError("Unknown requirement.")
    if req["relevance"] not in ("relevant", "not_relevant"):
        raise ValueError("Only a decided requirement can be reopened.")
    conn.execute(
        "UPDATE legal_requirements SET relevance='candidate', relevance_reason=NULL,"
        " decided_by=NULL, decided_at=NULL WHERE id=?", (req_id,))
    country = conn.execute("SELECT name FROM countries WHERE id=?",
                           (req["country_id"],)).fetchone()
    audit(conn, "requirement_reopened", "legal_requirements", entity_id=req_id,
          country=country["name"], section_code=req["area_code"],
          before={"relevance": req["relevance"], "reason": req["relevance_reason"],
                  "decided_by": req["decided_by"]},
          reason=reason, actor=actor)
    conn.commit()


def move_requirement_area(conn, req_id, new_area_code, actor):
    """Re-file a legal requirement under a different area (e.g. a law
    approved under A1 that actually belongs under A6/FPIC). Updates both the
    requirement (what /legal shows and groups by) and its originating
    evidence record (what future research runs compare new findings
    against for duplicate detection) — moving only the requirement would
    leave the evidence stuck under the old area, so a later research run
    scoped to the new area would never recognise the same law as a repeat."""
    req = conn.execute("SELECT * FROM legal_requirements WHERE id=?",
                       (req_id,)).fetchone()
    if req is None:
        raise ValueError("Unknown requirement.")
    area = conn.execute("SELECT code FROM legal_areas WHERE code=?",
                        (new_area_code,)).fetchone()
    if area is None:
        raise ValueError("Unknown area.")
    old_area_code = req["area_code"]
    if new_area_code == old_area_code:
        return
    conn.execute("UPDATE legal_requirements SET area_code=? WHERE id=?",
                (new_area_code, req_id))
    # Best-effort match back to the evidence this was promoted from — same
    # claim text, country, cycle, still filed under the old area. There is
    # no stored evidence_id link (the promotion copies fields, not an FK),
    # so this is a heuristic match, not a guarantee.
    moved_evidence = conn.execute(
        "SELECT id FROM evidence WHERE country_id=? AND cycle_id=? AND"
        " section_code=? AND claim=? AND status='approved'",
        (req["country_id"], req["cycle_id"], old_area_code, req["requirement"])
    ).fetchall()
    for row in moved_evidence:
        conn.execute("UPDATE evidence SET section_code=? WHERE id=?",
                     (new_area_code, row["id"]))
    country = conn.execute("SELECT name FROM countries WHERE id=?",
                           (req["country_id"],)).fetchone()
    audit(conn, "requirement_area_moved", "legal_requirements", entity_id=req_id,
          country=country["name"], section_code=new_area_code,
          before={"area_code": old_area_code},
          after={"area_code": new_area_code,
                "evidence_moved": [r["id"] for r in moved_evidence]},
          actor=actor)
    conn.commit()


def refine_requirement(conn, req_id, relevance, reason, verification_docs, actor,
                       authority=None, reference_law=None, applicability=None,
                       supply_chain_node=None, is_mandatory=None, alt_document=None,
                       mandatory_condition=None):
    if relevance not in ("relevant", "not_relevant"):
        raise ValueError("Relevance must be relevant or not_relevant.")
    if relevance == "relevant" and not verification_docs:
        raise ValueError("A relevant requirement needs at least one "
                         "verification document.")
    if applicability and applicability not in ("plantation", "smallholder", "both"):
        raise ValueError("Applicability must be plantation, smallholder or both.")
    if is_mandatory and is_mandatory not in ("yes", "no", "conditional"):
        raise ValueError("Mandatory must be yes, no or conditional.")
    req = conn.execute("SELECT * FROM legal_requirements WHERE id=?",
                       (req_id,)).fetchone()
    if req is None:
        raise ValueError("Unknown requirement.")
    if authority and authority.strip():
        conn.execute("UPDATE legal_requirements SET authority=? WHERE id=?",
                     (authority.strip(), req_id))
    field_updates, field_params = [], []
    for col, val in (("reference_law", reference_law), ("applicability", applicability),
                     ("supply_chain_node", supply_chain_node),
                     ("is_mandatory", is_mandatory), ("alt_document", alt_document),
                     ("mandatory_condition", mandatory_condition)):
        if val and val.strip():
            field_updates.append(f"{col}=?")
            field_params.append(val.strip())
    if field_updates:
        conn.execute(f"UPDATE legal_requirements SET {', '.join(field_updates)} WHERE id=?",
                     (*field_params, req_id))
    conn.execute(
        "UPDATE legal_requirements SET relevance=?, relevance_reason=?,"
        " verification_docs=?, decided_by=?, decided_at=? WHERE id=?",
        (relevance, (reason or "").strip() or None,
         json.dumps(verification_docs, ensure_ascii=False)
         if verification_docs else None,
         actor, now(), req_id))
    country = conn.execute("SELECT name FROM countries WHERE id=?",
                           (req["country_id"],)).fetchone()
    audit(conn, "requirement_refined", "legal_requirements", entity_id=req_id,
          country=country["name"], section_code=req["area_code"],
          before=req["relevance"],
          after={"relevance": relevance, "docs": verification_docs},
          reason=reason, actor=actor)
    conn.commit()


def audit_rows(conn, limit=500, country=None, event_type=None):
    q = "SELECT * FROM audit_log"
    cond, params = [], []
    if country:
        cond.append("country=?")
        params.append(country)
    if event_type:
        cond.append("event_type=?")
        params.append(event_type)
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(q, params).fetchall()
