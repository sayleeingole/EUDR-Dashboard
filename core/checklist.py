"""Article 9 checklist generation (Sector 3). Never hand-assembled: merges the
legality baseline (relevant legal requirements' verification documents) with
risk add-ons (mitigation rules triggered by signed section ratings). Every item
carries its justification; generations are versioned and auditable."""

import json
import uuid

from . import db
from .rules import RISK_ORDER, SUPPORT_ORDER, mitigation_rules

# Universal Art. 9 items — requested for every country regardless of risk.
UNIVERSAL_ITEMS = [
    ("Geolocation of all plots (polygons for plots > 4 ha)",
     "Art. 9(1)(d) — geolocation with production date ranges"),
    ("Supplier and supply chain identification down to plot level",
     "Art. 9(1)(e),(f) — full chain identification"),
    ("Quantities per plot / product",
     "Art. 9(1)(c) — quantity reconciliation"),
    ("Deforestation-free declaration (cutoff 31 Dec 2020)",
     "Art. 9(1)(g) — verifiable deforestation-free information"),
]


def _meets_trigger(rating_scale, rating, trigger):
    order = SUPPORT_ORDER if rating_scale == "support" else RISK_ORDER
    if rating not in order or trigger not in order:
        return False
    return order.index(rating) >= order.index(trigger)


def latest_signed(conn, cycle_id, country_id, region_id, section_code):
    """Region-level signed assessment, falling back to country level."""
    a = db.current_assessment(conn, cycle_id, country_id, region_id,
                              section_code)
    if a and a["status"] == "signed":
        return a, "region" if region_id else "country"
    if region_id:
        a = db.current_assessment(conn, cycle_id, country_id, None,
                                  section_code)
        if a and a["status"] == "signed":
            return a, "country (inherited)"
    return None, None


def completeness(conn, cycle_id, country_id, region_id, region_name):
    """Returns (is_complete, gaps). Complete = all 10 sections signed (region or
    inherited country level) and at least one refined requirement overall."""
    gaps = []
    for s in db.get_sections(conn):
        a, _lvl = latest_signed(conn, cycle_id, country_id, region_id, s["code"])
        if a is None:
            gaps.append(f"section {s['code']} ({s['title']}) not signed")
    reqs = db.get_requirements(conn, cycle_id, country_id)
    refined = [r for r in reqs if r["relevance"] != "candidate"]
    if not refined:
        gaps.append("no legal requirements refined yet")
    return (not gaps), gaps


def _short_legal_ref(r):
    """The checklist's remark for a legal-baseline item is just a citation —
    law name and issuing authority, nothing else. Not the full requirement
    paragraph (which can run to several hundred words of copied law text);
    that stays on the Legal requirements page. None if neither is on file."""
    law = (r["reference_law"] or "").strip()
    authority = (r["authority"] or "").strip()
    if law and authority:
        return f"{law} ({authority})"
    return law or authority or None


def generate(conn, cycle_id, country_id, region_id, region_name, actor):
    """Create a new checklist generation; returns (generation_id, items,
    is_final, gaps)."""
    sections = {s["code"]: s for s in db.get_sections(conn)}
    areas = {a["code"]: a for a in db.get_legal_areas(conn)}
    is_complete, gaps = completeness(conn, cycle_id, country_id, region_id,
                                     region_name)

    merged = {}  # normalized doc name -> item dict

    # Most conservative wins when the same document is pulled in by more than
    # one requirement: 'yes' > 'conditional' > 'no' > unknown.
    _MANDATORY_RANK = {"yes": 3, "conditional": 2, "no": 1}

    def add_item(doc, description, stream, justification, escalation=None,
                 grouping=None, is_mandatory=None, mandatory_condition=None,
                 reference_law=None, alt_group=None):
        key = doc.lower().strip()
        if key in merged:
            it = merged[key]
            if justification:
                it["justification"].append(justification)
            if stream != it["stream"]:
                it["stream"] = "merged"
            if escalation and not it["escalation"]:
                it["escalation"] = escalation
            if _MANDATORY_RANK.get(is_mandatory, 0) > \
                    _MANDATORY_RANK.get(it["is_mandatory"], 0):
                it["is_mandatory"] = is_mandatory
                it["mandatory_condition"] = mandatory_condition
            if reference_law and not it["reference_law"]:
                it["reference_law"] = reference_law
            # A document pulled in by more than one requirement isn't a clean
            # member of a single alternatives cluster anymore — keep it standalone.
            if it["alt_group"] != alt_group:
                it["alt_group"] = None
        else:
            merged[key] = {"doc": doc.strip(), "description": description,
                           "stream": stream,
                           "justification": [justification] if justification else [],
                           "escalation": escalation, "grouping": grouping,
                           "is_mandatory": is_mandatory,
                           "mandatory_condition": mandatory_condition,
                           "reference_law": reference_law,
                           "alt_group": alt_group}

    # universal Art. 9 items (baseline stream) — always mandatory, regardless
    # of country: they come straight from the regulation text, not a requirement.
    for doc, desc in UNIVERSAL_ITEMS:
        add_item(doc, desc, "legality-baseline", "EUDR Art. 9 universal "
                 "information requirement", grouping="Universal (Art. 9)",
                 is_mandatory="yes", reference_law="EUDR Art. 9")

    # stream 1 — legality baseline from relevant requirements
    for r in db.get_requirements(conn, cycle_id, country_id,
                                 relevance="relevant"):
        if region_name and r["region_scope"] and \
                r["region_scope"] != region_name:
            continue
        if not region_name and r["region_scope"]:
            continue
        if not r["verification_docs"]:
            continue
        law = (r["reference_law"] or "").strip() or None
        docs = json.loads(r["verification_docs"])
        # More than one document under the same requirement means the law
        # accepts any ONE of them as proof — not that all are separately
        # required — so cluster them instead of listing as independent items.
        alt_group = f"req{r['id']}" if len(docs) > 1 else None
        for doc in docs:
            area = areas.get(r["area_code"])
            area_label = f"Area {r['area_code']} · {area['title']}" if area \
                else f"Area {r['area_code']}"
            add_item(doc, None, "legality-baseline",
                     _short_legal_ref(r), grouping=area_label,
                     is_mandatory=r["is_mandatory"],
                     mandatory_condition=r["mandatory_condition"],
                     reference_law=law, alt_group=alt_group)

    # stream 2 — risk add-ons from signed ratings x mitigation rules
    section_ratings = {}
    for code, s in sections.items():
        a, level = latest_signed(conn, cycle_id, country_id, region_id, code)
        if a:
            section_ratings[code] = (a["confirmed_rating"], a["version"], level)
    for rule in mitigation_rules(conn):
        code = rule["section_code"]
        if code not in section_ratings:
            continue
        rating, version, level = section_ratings[code]
        scale = sections[code]["rating_scale"]
        if not _meets_trigger(scale, rating, rule["trigger_rating"]):
            continue
        escalation = "proof-level" if rating == "high" else None
        for doc in json.loads(rule["documents"] or "[]"):
            add_item(doc, None, "risk-addon",
                     f"Section {code} rated '{rating}' (signed v{version}, "
                     f"{level}) — rule {rule['rule_code']}: "
                     f"{rule['condition_text']}",
                     escalation=escalation,
                     grouping=f"Risk {code} · {sections[code]['title']}")

    generation_id = uuid.uuid4().hex[:12]
    country = conn.execute("SELECT name FROM countries WHERE id=?",
                           (country_id,)).fetchone()
    for it in merged.values():
        conn.execute(
            "INSERT INTO checklist_items (cycle_id, country_id, region_id,"
            " generation_id, document_name, description, stream, justification,"
            " escalation, grouping, stale, generated_by, generated_at,"
            " is_mandatory, mandatory_condition, reference_law, alt_group)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?)",
            (cycle_id, country_id, region_id, generation_id, it["doc"],
             it["description"], it["stream"],
             json.dumps(it["justification"], ensure_ascii=False),
             it["escalation"], it["grouping"], actor, db.now(),
             it["is_mandatory"], it["mandatory_condition"], it["reference_law"],
             it["alt_group"]))
    db.audit(conn, "checklist_generated", "checklist_items",
             entity_id=generation_id, country=country["name"],
             after={"items": len(merged), "final": is_complete,
                    "gaps": gaps[:10]}, actor=actor)
    conn.commit()
    return generation_id, list(merged.values()), is_complete, gaps


def latest_generation(conn, cycle_id, country_id, region_id):
    row = conn.execute(
        "SELECT generation_id, MAX(generated_at) AS at, generated_by"
        " FROM checklist_items WHERE cycle_id=? AND country_id=?"
        " AND (region_id IS ? OR region_id=?) GROUP BY generation_id"
        " ORDER BY at DESC LIMIT 1",
        (cycle_id, country_id, region_id, region_id or -1)).fetchone()
    if row is None:
        return None, []
    raw_items = conn.execute(
        "SELECT * FROM checklist_items WHERE generation_id=?"
        " ORDER BY grouping, reference_law IS NULL, reference_law,"
        " alt_group IS NULL, alt_group, document_name",
        (row["generation_id"],)).fetchall()

    excluded = {r["document_name"].strip().lower() for r in
               db.get_checklist_exclusions(conn, country_id, region_id)}
    renames = {r["original_name"].strip().lower(): r["new_name"] for r in
              db.get_checklist_renames(conn, country_id, region_id)}

    items = []
    for it in raw_items:
        key = it["document_name"].strip().lower()
        if key in excluded:
            continue
        d = dict(it)
        if key in renames:
            d["document_name"] = renames[key]
        d["kind"] = "generated"
        items.append(d)

    for a in db.get_checklist_additions(conn, country_id, region_id):
        items.append({
            "id": None, "addition_id": a["id"], "kind": "manual",
            "document_name": a["document_name"], "description": None,
            "stream": "manual", "justification": json.dumps([a["note"]] if a["note"] else []),
            "escalation": None, "grouping": a["grouping"], "stale": 0,
            "generation_id": row["generation_id"],
            "generated_by": a["added_by"], "generated_at": a["added_at"],
            "notes": None, "notes_by": None, "notes_at": None,
            "is_mandatory": None, "mandatory_condition": None, "reference_law": None,
            "alt_group": None,
        })
    return row, items


def supplier_minimum_items(items):
    """Filter a generated checklist down to the bare minimum for a supplier
    whose supply chain is otherwise clean: docs that are unconditionally
    mandatory, plus risk add-ons (these are only ever present because a
    section's signed rating actually triggered them — never speculative, so
    there's nothing to drop there). 'conditional'/'no' baseline items are
    dropped — those only apply in situations this supplier may not be in, and
    listing them anyway is exactly the overwhelm this view exists to avoid.
    Manual additions are always kept — the operator added them deliberately."""
    return [it for it in items
            if it.get("stream") in ("risk-addon", "merged", "manual")
            or it.get("is_mandatory") == "yes"]


def is_stale(conn, generation_row, cycle_id, country_id):
    """Stale if any sign-off or requirement refinement happened after
    generation."""
    if generation_row is None:
        return False
    t = generation_row["at"]
    n1 = conn.execute(
        "SELECT COUNT(*) FROM assessments WHERE cycle_id=? AND country_id=?"
        " AND status='signed' AND signed_at>?", (cycle_id, country_id, t)
    ).fetchone()[0]
    n2 = conn.execute(
        "SELECT COUNT(*) FROM legal_requirements WHERE cycle_id=?"
        " AND country_id=? AND decided_at>?", (cycle_id, country_id, t)
    ).fetchone()[0]
    return (n1 + n2) > 0
