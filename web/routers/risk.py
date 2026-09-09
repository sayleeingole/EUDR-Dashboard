import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from core import db as db_module
from core import importer, researcher
from core import rules as rules_engine
from core.source_type import (RIGHTS_SENSITIVE_SCOPES, SOURCE_TYPE_LABELS,
                              independent_count, source_mix, source_mix_segments)

from ..common import base_context, pending_for_section, split_pending, with_flash
from ..deps import current_actor, get_conn
from ..templates_env import templates

router = APIRouter(prefix="/risk")

SCALES = {"benchmark": ["low", "standard", "high"],
          "risk": ["negligible", "not_negligible"]}


def _scale_for(section):
    return SCALES.get(section["rating_scale"], SCALES["risk"])


def build_card(conn, cycle, sel_country, region_id, s, sec_pending):
    code = s["code"]
    counts = db_module.evidence_counts(conn, cycle["id"], sel_country["id"], region_id, code)
    approved_n = counts.get("approved", 0)
    current = db_module.current_assessment(conn, cycle["id"], sel_country["id"], region_id, code)
    approved_ev = db_module.approved_evidence(conn, cycle["id"], sel_country["id"], region_id, code)
    section_rules = rules_engine.rating_rules(conn, code)

    checked_rules = []
    if current and current["rule_trace"]:
        try:
            checked_rules = [m["rule_code"] for m in
                             json.loads(current["rule_trace"]).get("met_rules", [])]
        except (ValueError, TypeError):
            checked_rules = []
    met = [r for r in section_rules if r["rule_code"] in checked_rules]
    suggested = rules_engine.suggest(s["rating_scale"], met)
    trace = rules_engine.build_trace(met, len(approved_ev))

    scale = _scale_for(s)
    if current and current["confirmed_rating"] in scale:
        confirmed_default = current["confirmed_rating"]
    elif suggested in scale:
        confirmed_default = suggested
    elif approved_n == 0:
        # Nothing approved yet — "negligible"/scale[0] is a real default, not a guess.
        confirmed_default = scale[0]
    else:
        # Evidence is approved but no rule has been ticked yet — don't
        # silently pre-select scale[0] as if it were a system suggestion.
        confirmed_default = None

    draft_row = importer.latest_draft(conn, cycle["id"], sel_country["id"], region_id, code)
    prefill = current["narrative"] if current and current["narrative"] else ""
    prefill_note = None
    if not prefill and draft_row:
        prefill = draft_row["text"]
        prefill_note = (f"Pre-filled from research draft ({draft_row['batch_file']}) — "
                        "edit freely; only what you sign counts.")

    history = []
    if current and current["status"] == "signed":
        history = db_module.assessment_history(conn, cycle["id"], sel_country["id"],
                                                region_id, code)

    mix = source_mix(approved_ev)
    mix_segments = source_mix_segments(mix)
    lopsided = (code in RIGHTS_SENSITIVE_SCOPES and approved_n > 0
               and independent_count(mix) == 0)

    return {
        "s": s, "code": code, "approved_n": approved_n, "current": current,
        "sec_pending": sec_pending, "approved_ev": approved_ev,
        "section_rules": section_rules, "checked_rules": checked_rules,
        "suggested": suggested, "trace": trace, "scale": scale,
        "confirmed_default": confirmed_default, "prefill": prefill,
        "prefill_note": prefill_note, "history": history,
        "cycle_id": cycle["id"], "country_id": sel_country["id"],
        "region_id": region_id,
        "source_mix": mix_segments, "source_mix_lopsided": lopsided,
    }


@router.get("")
def risk_view(request: Request, country: str | None = None, region: str | None = None,
             conn=Depends(get_conn), actor: str = Depends(current_actor)):
    ctx = base_context(conn, request, actor, country, region, "risk")
    ctx["base"] = "risk"
    cycle, sel_country = ctx["cycle"], ctx["sel_country"]
    ctx["claude_ok"] = researcher.claude_available()
    ctx["sections"] = db_module.get_sections(conn)
    ctx["areas"] = db_module.get_legal_areas(conn)
    if not cycle or not sel_country:
        ctx.update({"cards": [], "risk_pending_count": 0, "sources_list": [],
                    "pending_batches": [], "research_counts": {}})
        return templates.TemplateResponse(request, "views/risk.html", ctx)
    ctx["pending_batches"] = researcher.pending_batches(sel_country["name"], run_type="risk")
    ctx["research_counts"] = db_module.evidence_counts_by_code(
        conn, cycle["id"], sel_country["id"], ctx["region_id"])

    pending_all = db_module.pending_evidence(conn, cycle["id"], sel_country["id"])
    risk_pending, _legal_pending = split_pending(pending_all)
    cards = [build_card(conn, cycle, sel_country, ctx["region_id"], s,
                        pending_for_section(risk_pending, s["code"]))
            for s in ctx["sections"]]
    ctx.update({
        "cards": cards, "risk_pending_count": len(risk_pending),
        "sources_list": db_module.get_active_sources(conn),
    })
    return templates.TemplateResponse(request, "views/risk.html", ctx)


@router.post("/evidence")
def add_manual_evidence(
        request: Request, section_code: str = Form(...), claim: str = Form(""),
        value: str = Form(""), source_choice: str = Form("__new__"),
        source_free: str = Form(""), url: str = Form(""), published: str = Form(""),
        retrieved: str = Form(""), notes: str = Form(""),
        confidence: str = Form(""), significance: str = Form(""),
        req_type: str = Form(""), authority: str = Form(""),
        verification_docs: str = Form(""),
        cycle_id: int = Form(...), country_id: int = Form(...),
        region_id: str = Form(""), nxt: str = Form("/risk", alias="next"),
        conn=Depends(get_conn), actor: str = Depends(current_actor)):
    if not claim.strip() or not retrieved.strip():
        return RedirectResponse(
            with_flash(nxt, error="Claim and retrieval date are required."),
            status_code=303)
    region_id_val = int(region_id) if region_id else None
    sources_list = db_module.get_active_sources(conn)
    if source_choice != "__new__":
        source_id = int(source_choice)
        source_name = next((s["name"] for s in sources_list if s["id"] == source_id),
                           source_free.strip() or "unknown")
    else:
        source_id, source_name = None, (source_free.strip() or "unknown")
    db_module.add_evidence(
        conn, cycle_id=cycle_id, country_id=country_id, region_id=region_id_val,
        section_code=section_code, claim=claim.strip(), value=value.strip() or None,
        source_id=source_id, source_name=source_name, url=url.strip() or None,
        published=published.strip() or None, retrieved=retrieved.strip(),
        origin="manual", actor=actor, notes=notes.strip() or None,
        confidence=confidence.strip() or None, significance=significance.strip() or None,
        req_type=req_type.strip() or None, authority=authority.strip() or None,
        verification_docs=[d.strip() for d in verification_docs.split(",") if d.strip()] or None)
    return RedirectResponse(with_flash(nxt, ok="Submitted to review."), status_code=303)


@router.post("/{code}/recompute")
def recompute(code: str, request: Request, rule: list[str] = Form([]),
             cycle_id: int = Form(...), country_id: int = Form(...),
             region_id: str = Form(""), conn=Depends(get_conn),
             actor: str = Depends(current_actor)):
    region_id_val = int(region_id) if region_id else None
    s = next(x for x in db_module.get_sections(conn) if x["code"] == code)
    section_rules = rules_engine.rating_rules(conn, code)
    met = [r for r in section_rules if r["rule_code"] in rule]
    suggested = rules_engine.suggest(s["rating_scale"], met)
    approved_ev = db_module.approved_evidence(conn, cycle_id, country_id, region_id_val, code)
    trace = rules_engine.build_trace(met, len(approved_ev))
    return templates.TemplateResponse(
        request, "partials/suggested_block.html",
        {"code": code, "suggested": suggested, "trace": trace,
         "section_rules": section_rules, "approved_n": len(approved_ev)})


@router.post("/{code}/draft-narrative")
def draft_narrative(code: str, request: Request, cycle_id: int = Form(...),
                    country_id: int = Form(...), region_id: str = Form(""),
                    nxt: str = Form("/risk", alias="next"),
                    conn=Depends(get_conn), actor: str = Depends(current_actor)):
    """Generate a narrative draft from the evidence already approved for this
    section — for when the research run's narrative pass produced nothing,
    or the evidence came from fetchers / manual entry / older batches that
    never had a draft. Writes to narrative_drafts so the card pre-fills it;
    nothing is signed."""
    region_id_val = int(region_id) if region_id else None
    if not researcher.claude_available():
        return RedirectResponse(with_flash(
            nxt, error="Claude Code CLI not found — cannot draft. Write the "
                       "narrative manually or install Claude Code."), status_code=303)
    approved_ev = db_module.approved_evidence(conn, cycle_id, country_id, region_id_val, code)
    if not approved_ev:
        return RedirectResponse(with_flash(
            nxt, error="No approved evidence for this section yet — approve "
                       "evidence in the queue first."), status_code=303)

    sections = db_module.get_sections(conn)
    areas = db_module.get_legal_areas(conn)
    sec = next((s for s in sections if s["code"] == code), None)
    if sec is not None:
        run_type = "risk"
        item = {"code": code, "title": sec["title"], "scope": sec["min_scope"]}
    else:
        area = next((a for a in areas if a["code"] == code), None)
        if area is None:
            return RedirectResponse(with_flash(nxt, error=f"Unknown section {code}."),
                                    status_code=303)
        run_type = "legal"
        item = {"code": code, "title": area["title"], "scope": ""}

    cycle = conn.execute("SELECT * FROM assessment_cycles WHERE id=?",
                         (cycle_id,)).fetchone()
    country = conn.execute("SELECT * FROM countries WHERE id=?",
                           (country_id,)).fetchone()
    region_name = None
    if region_id_val:
        r = conn.execute("SELECT name FROM regions WHERE id=?",
                         (region_id_val,)).fetchone()
        region_name = r["name"] if r else None

    ev_records = [{
        "section": e["section_code"], "claim": e["claim"], "value": e["value"],
        "source_name": e["source_name"], "publisher": None, "url": e["url"],
        "retrieved": e["retrieved"],
    } for e in approved_ev]

    try:
        drafts = researcher.draft_narrative(
            run_type, country["name"], region_name, cycle["year"], [item],
            ev_records, timeout_s=600)
    except Exception as err:
        return RedirectResponse(with_flash(nxt, error=f"Drafting failed: {err}"),
                                status_code=303)
    draft = next((d for d in drafts if d["section"] == code), None)
    if draft is None:
        return RedirectResponse(with_flash(
            nxt, error="Claude returned no draft for this section — try again."),
            status_code=303)
    importer.store_draft(conn, cycle_id, country_id, region_id_val, code,
                         draft["text"], sources=draft.get("sources"),
                         actor=actor, country_name=country["name"])
    return RedirectResponse(with_flash(
        f"{nxt.split('#')[0]}#section-{code}",
        ok=f"Narrative draft generated for {code} from {len(approved_ev)} approved "
           "evidence records — review and edit before signing."), status_code=303)


@router.post("/{code}/save")
def save_section(
        code: str, request: Request, nxt: str = Form("/risk", alias="next"),
        version: int = Form(0), cycle_id: int = Form(...), country_id: int = Form(...),
        region_id: str = Form(""), suggested_rating: str = Form(""),
        rule_trace: str = Form(""), confirmed: str = Form(...),
        override_reason: str = Form(""), narrative: str = Form(""),
        op: str = Form(...), conn=Depends(get_conn),
        actor: str = Depends(current_actor)):
    region_id_val = int(region_id) if region_id else None
    cur = db_module.current_assessment(conn, cycle_id, country_id, region_id_val, code)
    if op == "sign" and cur and cur["version"] != version:
        return RedirectResponse(with_flash(
            nxt, error=(f"{cur['signed_by'] or 'someone'} signed v{cur['version']} while "
                       "you were editing — review their conclusion before signing.")),
            status_code=303)
    kwargs = dict(cycle_id=cycle_id, country_id=country_id, region_id=region_id_val,
                 section_code=code, suggested_rating=suggested_rating or None,
                 rule_trace=rule_trace, confirmed_rating=confirmed,
                 override_reason=override_reason.strip() or None,
                 narrative=narrative, actor=actor)
    try:
        if op == "sign":
            _, v = db_module.sign_assessment(conn, **kwargs)
            ok = f"Signed v{v}."
        else:
            db_module.save_draft(conn, **kwargs)
            ok = "Draft saved."
    except ValueError as err:
        return RedirectResponse(with_flash(nxt, error=str(err)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok=ok), status_code=303)


@router.post("/{code}/reopen")
def reopen_section(code: str, request: Request, assessment_id: int = Form(...),
                   reason: str = Form(...), nxt: str = Form("/risk", alias="next"),
                   conn=Depends(get_conn), actor: str = Depends(current_actor)):
    try:
        db_module.reopen_assessment(conn, assessment_id, reason, actor)
    except ValueError as err:
        return RedirectResponse(with_flash(nxt, error=str(err)), status_code=303)
    return RedirectResponse(with_flash(nxt, ok="Reopened."), status_code=303)


@router.post("/consolidate-all")
def consolidate_all(request: Request, cycle_id: int = Form(...),
                    country_id: int = Form(...), region_id: str = Form(""),
                    nxt: str = Form("/risk", alias="next"),
                    conn=Depends(get_conn), actor: str = Depends(current_actor)):
    region_id_val = int(region_id) if region_id else None
    sections_hit = 0
    duplicates_total = 0
    for s in db_module.get_sections(conn):
        counts = db_module.evidence_counts(conn, cycle_id, country_id, region_id_val, s["code"])
        if counts.get("approved", 0) <= 1:
            continue
        n = db_module.consolidate_duplicates(conn, cycle_id, country_id, s["code"], actor)
        if n:
            sections_hit += 1
            duplicates_total += n
    if duplicates_total:
        msg = f"{duplicates_total} duplicate(s) superseded across {sections_hit} section(s)."
    else:
        msg = "No duplicates found."
    return RedirectResponse(with_flash(nxt, ok=msg), status_code=303)
