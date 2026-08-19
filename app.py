"""EUDR Palm Risk Assessment Dashboard.
Run with:  streamlit run app.py
"""

import getpass
import json

import streamlit as st

from core import (checklist as checklist_engine, db, exporter, importer,
                  researcher, runmanager, rules as rules_engine)

st.set_page_config(page_title="EUDR country risk assessment", page_icon="🌿",
                   layout="wide")

RATING_DOT = {"low": "🟢", "medium": "🟡", "high": "🔴",
              "standard": "🟠", "supportive": "🟢", "neutral": "🟡", "weak": "🔴"}
REJECT_REASONS = ["Not relevant (country/region/commodity)",
                  "Outdated data / wrong vintage",
                  "Duplicate",
                  "Source misread / claim not supported by source",
                  "Other (specify)"]


@st.cache_resource
def _conn():
    return db.init_db(actor=getpass.getuser())


conn = _conn()

# ---------------- sidebar ----------------
if "operator" not in st.session_state:
    st.session_state.operator = getpass.getuser()

with st.sidebar:
    st.markdown("### EUDR country risk assessment")
    st.caption("KLK Emmerich GmbH")
    operator = st.text_input("Operator", value=st.session_state.operator,
                             help="Recorded on every decision and sign-off.")
    st.session_state.operator = operator

    cycle = db.get_open_cycle(conn)
    if cycle:
        st.markdown(f"**Cycle:** {cycle['year']} (open)")
    else:
        st.markdown("**Cycle:** none open")
        st.error("No cycle is open. Open one below before assessing.")

    with st.expander("Cycle manager"):
        all_cycles = db.get_cycles(conn)
        st.caption(" · ".join(f"{c['year']} ({c['status']})" for c in all_cycles)
                   or "No cycles yet.")

        st.markdown("**Open new cycle**")
        next_year = (max((c["year"] for c in all_cycles), default=cycle["year"]
                         if cycle else 2025) + 1)
        new_year = st.number_input("Year", value=next_year, step=1,
                                   key="new_cycle_year")
        if st.button("Open cycle", key="open_cycle_btn"):
            try:
                db.open_cycle(conn, int(new_year), operator)
                st.rerun()
            except ValueError as err:
                st.error(str(err))

        if cycle:
            st.markdown("**Close current cycle**")
            st.caption(f"Freezes {cycle['year']} — signed data stays "
                       "queryable, no further drafts or signing against it.")
            if st.button(f"Close cycle {cycle['year']}", key="close_cycle_btn"):
                try:
                    db.close_cycle(conn, cycle["id"], operator)
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))

        closed_cycles = [c for c in all_cycles if c["status"] == "closed"]
        if closed_cycles and cycle:
            st.markdown("**Roll forward into current cycle**")
            rf_from_year = st.selectbox(
                "From cycle", [c["year"] for c in closed_cycles],
                key="rf_from_year")
            rf_from = next(c for c in closed_cycles if c["year"] == rf_from_year)
            if st.button(f"Roll forward {rf_from['year']} → {cycle['year']}",
                        key="rollforward_btn"):
                try:
                    result = db.rollforward(conn, rf_from["id"], cycle["id"],
                                            operator)
                    st.toast(f"Rolled forward: {result['evidence']} evidence, "
                             f"{result['assessments']} assessments to "
                             f"reverify, {result['requirements']} legal "
                             "requirements to reconfirm.")
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))

        if len(all_cycles) >= 2:
            st.markdown("**Year-over-year delta**")
            yoy_years = [c["year"] for c in all_cycles]
            c1, c2 = st.columns(2)
            yoy_a = c1.selectbox("Cycle A", yoy_years, index=1
                                 if len(yoy_years) > 1 else 0, key="yoy_a")
            yoy_b = c2.selectbox("Cycle B (newer)", yoy_years, index=0,
                                 key="yoy_b")
            if st.button("Show delta", key="yoy_btn"):
                cyc_a = next(c for c in all_cycles if c["year"] == yoy_a)
                cyc_b = next(c for c in all_cycles if c["year"] == yoy_b)
                delta = db.year_over_year_delta(conn, cyc_b["id"], cyc_a["id"])
                if not delta:
                    st.caption("No comparable assessments in either cycle.")
                for d in delta:
                    if d["change"] == "same":
                        continue
                    label = f"{d['country']}"
                    if d["region"]:
                        label += f" — {d['region']}"
                    label += f" · {d['section_code']}"
                    if d["change"] == "new":
                        st.markdown(f"🆕 {label}: **{d['curr_rating']}**")
                    elif d["change"] == "dropped":
                        st.markdown(f"⬜ {label}: dropped "
                                   f"(was **{d['prev_rating']}**)")
                    else:
                        st.markdown(f"🔁 {label}: **{d['prev_rating']}** → "
                                   f"**{d['curr_rating']}**")
    st.divider()

    if not cycle:
        st.stop()

    countries = db.get_countries(conn)
    country_names = [c["name"] for c in countries]
    sel_country_name = st.radio("Producing country", country_names, key="country")
    sel_country = next(c for c in countries if c["name"] == sel_country_name)

    regions = db.get_regions(conn, sel_country["id"])
    region_options = ["Country level"] + [r["name"] for r in regions]
    sel_region_name = st.selectbox("Assessment level", region_options, key="region")
    sel_region = None
    if sel_region_name != "Country level":
        sel_region = next(r for r in regions if r["name"] == sel_region_name)

    with st.expander("Add country / region"):
        new_country = st.text_input("New country name", key="nc_name")
        new_iso = st.text_input("ISO3 code", key="nc_iso", max_chars=3)
        if st.button("Add country") and new_country and new_iso:
            db.add_country(conn, new_country.strip(), new_iso.strip().upper(),
                           operator)
            st.rerun()
        new_region = st.text_input(f"New region in {sel_country_name}",
                                   key="nr_name")
        if st.button("Add region") and new_region:
            db.add_region(conn, sel_country["id"], new_region.strip(), operator)
            st.rerun()

sections = db.get_sections(conn)
areas = db.get_legal_areas(conn)
region_id = sel_region["id"] if sel_region else None
scope_label = sel_country_name + (f" — {sel_region_name}" if sel_region else "")


# ---------------- shared renderers ----------------

def render_evidence_row(ev):
    """One pending evidence row: claim + source, approve / reject inline."""
    c_txt, c_ok, c_no = st.columns([8, 1, 1], vertical_alignment="center")
    with c_txt:
        flags = ""
        if ev["flag"] == "unlisted-source":
            flags = " · ⚠️ unlisted source"
        elif ev["flag"] == "possible-duplicate":
            flags = " · ⚠️ possible duplicate"
        region_note = f" · {ev['region_name']}" if ev["region_name"] else ""
        st.markdown(f"{ev['claim']}")
        src = ev["source_name"]
        if ev["url"]:
            src = f"[{ev['source_name']}]({ev['url']})"
        st.caption(f"{src} · retrieved {ev['retrieved']} · {ev['origin']}"
                   f"{region_note}{flags}"
                   + (f" · {ev['notes']}" if ev["notes"] else ""))
    if ev["flag"] == "unlisted-source":
        with c_ok.popover("⚠️"):
            st.markdown(f"**Source not whitelisted:** {ev['source_name']}")
            reason = st.text_input("Reason to approve this source",
                                   key=f"srcr{ev['id']}")
            if st.button("Approve source", key=f"srca{ev['id']}"):
                if reason.strip():
                    db.approve_source(conn, ev["id"], ev["section_code"],
                                      reason.strip(), operator)
                    st.rerun()
                else:
                    st.error("Reason required.")
        with c_no.popover("✗"):
            if st.button("Reject record (unlisted source)", key=f"srcx{ev['id']}"):
                db.decide_evidence(conn, ev["id"], "rejected",
                                   "unlisted source rejected", operator)
                st.rerun()
    else:
        if c_ok.button("✓", key=f"ap{ev['id']}", help="Approve"):
            db.decide_evidence(conn, ev["id"], "approved", None, operator)
            st.rerun()
        with c_no.popover("✗"):
            choice = st.selectbox("Reason", REJECT_REASONS, key=f"rr{ev['id']}")
            other = ""
            if choice == "Other (specify)":
                other = st.text_input("Specify", key=f"rro{ev['id']}")
            if st.button("Confirm rejection", key=f"rj{ev['id']}"):
                reason = other.strip() if choice == "Other (specify)" else choice
                if reason:
                    db.decide_evidence(conn, ev["id"], "rejected", reason,
                                       operator)
                    st.rerun()
                else:
                    st.error("Specify the reason.")


def pending_for_section(pending_rows, code):
    return [e for e in pending_rows if e["section_code"] == code]


def render_section_card(s, pending_rows):
    code = s["code"]
    counts = db.evidence_counts(conn, cycle["id"], sel_country["id"], region_id,
                                code)
    approved_n = counts.get("approved", 0)
    current = db.current_assessment(conn, cycle["id"], sel_country["id"],
                                    region_id, code)
    sec_pending = pending_for_section(pending_rows, code)
    ws_key = f"{code}_{sel_country['id']}_{region_id or 0}"

    with st.container(border=True):
        # header row
        h1, h2 = st.columns([7, 3], vertical_alignment="center")
        h1.markdown(f"#### {s['title']}  \n"
                    f"<small>Art. {s['article_refs']} · {approved_n} approved · "
                    f"{len(sec_pending)} pending</small>", unsafe_allow_html=True)
        if current and current["status"] == "signed":
            r = current["confirmed_rating"]
            h2.markdown(f"### {RATING_DOT.get(r, '⚪')} {r}")
            h2.caption(f"signed v{current['version']} · {current['signed_by']} · "
                       f"{current['signed_at'][:10]}")
        elif current and current["status"] == "to_reverify":
            r = current["confirmed_rating"]
            h2.markdown(f"### 🔁 {RATING_DOT.get(r, '⚪')} {r} (to reverify)")
            h2.caption("rolled forward — re-sign to confirm for this cycle")
        else:
            h2.markdown("### ⚪ not signed")

        # signed conclusion stays on the card
        if current and current["status"] == "signed":
            st.markdown(current["narrative"])
            if current["override_reason"]:
                st.caption(f"Override reason: {current['override_reason']}")

        if approved_n > 1:
            with h2.popover("🧹", help="Consolidate duplicate approved evidence"):
                st.caption("Fuzzy-matches approved records in this section; "
                           "duplicates become 'superseded' (kept in history, "
                           "never deleted).")
                if st.button("Consolidate duplicates", key=f"dd{ws_key}"):
                    n = db.consolidate_duplicates(conn, cycle["id"],
                                                  sel_country["id"], code,
                                                  operator)
                    st.toast(f"{n} duplicate(s) superseded.")
                    st.rerun()

        # pending evidence inline
        if sec_pending:
            st.markdown("**Evidence to review**")
            for ev in sec_pending:
                render_evidence_row(ev)

        # workspace under the card
        if current and current["status"] == "signed":
            with st.expander("History · reopen"):
                for h in db.assessment_history(conn, cycle["id"],
                                               sel_country["id"], region_id,
                                               code):
                    st.markdown(f"- v{h['version']} · {h['confirmed_rating']} · "
                                f"{h['signed_by']} · {h['signed_at']}")
                reopen_reason = st.text_input("Reason to reopen",
                                              key=f"ro{ws_key}")
                if st.button("Reopen (creates new version)", key=f"rob{ws_key}"):
                    if reopen_reason.strip():
                        db.reopen_assessment(conn, current["id"],
                                             reopen_reason.strip(), operator)
                        st.rerun()
                    else:
                        st.error("Reopening requires a reason.")
            return

    # draft workspace (expander directly under the card)
        with st.expander("Assess & sign"):
            approved_ev = db.approved_evidence(conn, cycle["id"],
                                               sel_country["id"], region_id,
                                               code)
            if approved_ev:
                with st.popover(f"Approved evidence ({len(approved_ev)})"):
                    for e in approved_ev:
                        st.markdown(f"- **#{e['id']}** {e['claim']}")
                        st.caption(f"{e['source_name']} · {e['retrieved']}")
            else:
                st.caption("No approved evidence yet — a rating without evidence "
                           "must be justified as 'insufficient basis'.")

            section_rules = rules_engine.rating_rules(conn, code)
            met = []
            for r in section_rules:
                if st.checkbox(f"[{r['rule_code']}] {r['condition_text']} → "
                               f"**{r['suggested_rating']}**",
                               key=f"rule_{r['rule_code']}_{ws_key}",
                               help=r["rationale"]):
                    met.append(r)
            suggested = rules_engine.suggest(s["rating_scale"], met)
            trace = rules_engine.build_trace(met, len(approved_ev))
            if section_rules:
                st.caption(f"Suggested: **{suggested or '— insufficient basis'}**")

            if s["rating_scale"] == "support":
                scale = ["supportive", "neutral", "weak"]
            elif s["rating_scale"] == "benchmark":
                scale = ["low", "standard", "high"]
            else:
                scale = ["low", "medium", "high"]
            default_idx = scale.index(current["confirmed_rating"]) \
                if current and current["confirmed_rating"] in scale \
                else (scale.index(suggested) if suggested in scale else 0)
            confirmed = st.radio("Confirmed rating", scale, index=default_idx,
                                 horizontal=True, key=f"conf{ws_key}")
            override_reason = None
            if suggested and confirmed != suggested:
                override_reason = st.text_input(
                    "Override reason (required)", key=f"ovr{ws_key}")

            draft_row = importer.latest_draft(conn, cycle["id"],
                                              sel_country["id"], region_id, code)
            prefill = current["narrative"] if current and current["narrative"] \
                else ""
            if not prefill and draft_row:
                prefill = draft_row["text"]
                st.caption("Pre-filled from research draft "
                           f"({draft_row['batch_file']}) — edit freely; only "
                           "what you sign counts.")
            narr_key = f"narr{ws_key}"
            # Widget state persists across reruns and would shadow a prefill
            # that arrived later (e.g. a research draft) — seed it explicitly.
            if prefill and not st.session_state.get(narr_key):
                st.session_state[narr_key] = prefill
            narrative = st.text_area("Narrative conclusion", height=200,
                                     key=narr_key)

            b1, b2, _ = st.columns([1, 1, 3])
            if b1.button("Save draft", key=f"sd{ws_key}"):
                db.save_draft(conn, cycle_id=cycle["id"],
                              country_id=sel_country["id"], region_id=region_id,
                              section_code=code, suggested_rating=suggested,
                              rule_trace=trace, confirmed_rating=confirmed,
                              override_reason=override_reason,
                              narrative=narrative, actor=operator)
                st.toast("Draft saved.")
            if b2.button("✍️ Sign", key=f"sg{ws_key}", type="primary"):
                try:
                    _, v = db.sign_assessment(
                        conn, cycle_id=cycle["id"],
                        country_id=sel_country["id"], region_id=region_id,
                        section_code=code, suggested_rating=suggested,
                        rule_trace=trace, confirmed_rating=confirmed,
                        override_reason=override_reason, narrative=narrative,
                        actor=operator)
                    st.toast(f"Signed v{v}.")
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))


# ---------------- navigation (persistent across reruns) ----------------
pending_all = db.pending_evidence(conn, cycle["id"], sel_country["id"])
risk_pending = [e for e in pending_all if e["section_code"].startswith("S")]
legal_pending = [e for e in pending_all if e["section_code"].startswith("A")]

nav = st.radio("View",
               ["1 · Risk assessment", "2 · Legal requirements",
                "3 · Art. 9 checklist", "Audit trail"],
               horizontal=True, key="nav", label_visibility="collapsed")
st.divider()

# ---------------- view: risk assessment ----------------
if nav == "1 · Risk assessment":
    t1, t2 = st.columns([7, 3], vertical_alignment="center")
    t1.subheader(scope_label)
    t2.caption(f"Cycle {cycle['year']} · {len(risk_pending)} pending evidence")

    @st.fragment(run_every="5s")
    def research_status():
        for r in runmanager.runs():
            scope_txt = ",".join(r["scope"][:5]) + \
                ("…" if len(r["scope"]) > 5 else "")
            label = (f"{r['country']}"
                     + (f" · {r['region']}" if r["region"] else "")
                     + f" · {r['run_type']} · {scope_txt} · started "
                     f"{r['started']}")
            if r["status"] == "running":
                st.info(f"⏳ {label} — researching in the background; "
                        "keep working.")
            elif r["status"] == "completed":
                s_ = r["summary"]
                c1, c2 = st.columns([5, 1], vertical_alignment="center")
                c1.success(f"✅ {label} — {s_['evidence']} records ready for "
                           f"review ({s_['unlisted']} unlisted-source, "
                           f"{s_['duplicates']} possible duplicates, "
                           f"{s_['drafts']} drafts).")
                if c2.button("Show", key=f"ack{r['id']}"):
                    runmanager.dismiss(r["id"])
                    st.rerun(scope="app")
            else:
                c1, c2 = st.columns([5, 1], vertical_alignment="center")
                c1.error(f"❌ {label} — {r['error']}")
                if c2.button("Dismiss", key=f"dis{r['id']}"):
                    runmanager.dismiss(r["id"])
                    st.rerun(scope="app")

    research_status()

    with st.expander("🔎 Run research"):
        run_type = st.radio("Run type", ["risk", "legal"], horizontal=True,
                            format_func=lambda x: "Risk sections" if x == "risk"
                            else "Legal mapping (Art. 2(40))", key="runtype")
        if run_type == "risk":
            item_options = {f"{s['code']} · {s['title']}":
                            {"code": s["code"], "title": s["title"],
                             "scope": s["min_scope"]} for s in sections}
        else:
            item_options = {f"{a['code']} · {a['title']}":
                            {"code": a["code"], "title": a["title"], "scope": ""}
                            for a in areas}
        chosen = st.multiselect("Scope (empty = all)", list(item_options),
                                key="runscope")
        items = [item_options[c] for c in (chosen or list(item_options))]
        st.caption(f"{len(items)} item(s) · {scope_label} · cycle "
                   f"{cycle['year']} · runs in the background — keep working "
                   "while Claude researches.")
        if st.button("▶ Run research", type="primary"):
            whitelist = [s for s in db.get_active_sources(conn)
                         if s["applies_to"] == "all" or any(
                             i["code"] in s["applies_to"].split(",") for i in items)]
            runmanager.start_run(run_type, sel_country_name,
                                 sel_region["name"] if sel_region else None,
                                 cycle["year"], items, whitelist, operator)
            st.toast("Research started in the background.")
            st.rerun()

        waiting = researcher.pending_batches()
        if waiting:
            st.info(f"📥 {len(waiting)} batch file(s) awaiting import "
                    "(e.g. from a chat-based run).")
            for p in waiting:
                b1, b2 = st.columns([4, 1])
                b1.markdown(f"`{p.name}`")
                if b2.button("Import", key=f"imp_{p.name}"):
                    try:
                        s_ = importer.import_batch(conn, p, operator)
                        st.success(f"Imported {s_['evidence']} records.")
                        st.rerun()
                    except Exception as err:
                        st.error(f"Import failed: {err}")

    with st.expander("➕ Add evidence manually"):
        with st.form("manual_evidence", clear_on_submit=True):
            sec_options = {f"{s['code']} · {s['title']}": s["code"]
                           for s in sections}
            sec_options.update({f"{a['code']} · {a['title']} (legal)": a["code"]
                                for a in areas})
            sel_sec = st.selectbox("Section / legal area", list(sec_options))
            claim = st.text_area("Claim (one factual statement)")
            value = st.text_input("Value (optional)")
            sources_list = db.get_active_sources(conn)
            src_options = ["— new/unlisted source —"] + [s["name"]
                                                         for s in sources_list]
            src_choice = st.selectbox("Source", src_options)
            src_free = st.text_input("If new/unlisted: source name")
            url = st.text_input("URL")
            col1, col2 = st.columns(2)
            published = col1.text_input("Publication date")
            retrieved = col2.text_input("Retrieval date (YYYY-MM-DD)")
            notes = st.text_input("Notes")
            submitted = st.form_submit_button("Submit to review")
        if submitted:
            if not claim.strip() or not retrieved.strip():
                st.error("Claim and retrieval date are required.")
            else:
                if src_choice == "— new/unlisted source —":
                    source_id, source_name = None, (src_free.strip() or "unknown")
                else:
                    source_id = next(s["id"] for s in sources_list
                                     if s["name"] == src_choice)
                    source_name = src_choice
                db.add_evidence(
                    conn, cycle_id=cycle["id"], country_id=sel_country["id"],
                    region_id=region_id, section_code=sec_options[sel_sec],
                    claim=claim.strip(), value=value.strip() or None,
                    source_id=source_id, source_name=source_name,
                    url=url.strip() or None,
                    published=published.strip() or None,
                    retrieved=retrieved.strip(), origin="manual",
                    actor=operator, notes=notes.strip() or None)
                st.toast("Submitted to review.")
                st.rerun()

    for s in sections:
        render_section_card(s, risk_pending)

# ---------------- view: legal requirements ----------------
elif nav == "2 · Legal requirements":
    st.subheader(f"Legal requirements — {sel_country_name}")
    st.caption("Approved legal-area evidence becomes candidate requirements; "
               "refine each to relevant / not relevant and link verification "
               "documents. Relevant requirements form the Art. 9(1)(h) "
               "legality baseline.")

    all_reqs = db.get_requirements(conn, cycle["id"], sel_country["id"])
    n_cand = sum(1 for r in all_reqs if r["relevance"] == "candidate")
    n_rel = sum(1 for r in all_reqs if r["relevance"] == "relevant")
    st.markdown(f"**{len(all_reqs)}** requirements · **{n_cand}** to refine · "
                f"**{n_rel}** relevant (baseline) · "
                f"**{len(legal_pending)}** evidence pending review")

    for a in areas:
        area_pending = pending_for_section(legal_pending, a["code"])
        area_reqs = [r for r in all_reqs if r["area_code"] == a["code"]]
        if not area_pending and not area_reqs:
            continue
        with st.container(border=True):
            st.markdown(f"#### {a['code']} — {a['title']}")
            if area_pending:
                st.markdown("**Evidence to review**")
                for ev in area_pending:
                    render_evidence_row(ev)
            for r in area_reqs:
                scope_note = f" · {r['region_scope']}" if r["region_scope"] else ""
                icon = {"candidate": "🕓", "relevant": "✅",
                        "not_relevant": "🚫"}[r["relevance"]]
                st.markdown(f"{icon} **#{r['id']}**{scope_note} "
                            f"{r['requirement']}")
                if r["relevance"] == "candidate":
                    with st.popover("Refine"):
                        docs_in = st.text_input(
                            "Verification documents (comma-separated)",
                            value=r["provision"] or "", key=f"vd{r['id']}")
                        reason_in = st.text_input("Reason", key=f"rre{r['id']}")
                        c1, c2 = st.columns(2)
                        if c1.button("Relevant", key=f"mr{r['id']}"):
                            try:
                                docs = [d.strip() for d in docs_in.split(",")
                                        if d.strip()]
                                db.refine_requirement(conn, r["id"], "relevant",
                                                      reason_in, docs, operator)
                                st.rerun()
                            except ValueError as err:
                                st.error(str(err))
                        if c2.button("Not relevant", key=f"mn{r['id']}"):
                            try:
                                db.refine_requirement(conn, r["id"],
                                                      "not_relevant", reason_in,
                                                      None, operator)
                                st.rerun()
                            except ValueError as err:
                                st.error(str(err))
                else:
                    if r["verification_docs"]:
                        st.caption("Documents: "
                                   + " · ".join(json.loads(
                                       r["verification_docs"]))
                                   + f" — {r['relevance_reason']} "
                                   f"({r['decided_by']}, {r['decided_at'][:10]})")
                    elif r["relevance_reason"]:
                        st.caption(f"{r['relevance_reason']} "
                                   f"({r['decided_by']}, {r['decided_at'][:10]})")

    if n_rel:
        with st.container(border=True):
            st.markdown("#### Legality baseline preview")
            seen = {}
            for r in all_reqs:
                if r["relevance"] == "relevant" and r["verification_docs"]:
                    for d in json.loads(r["verification_docs"]):
                        seen.setdefault(d, []).append(
                            f"{r['area_code']}#{r['id']}")
            for doc, refs in sorted(seen.items()):
                st.markdown(f"- **{doc}** — from {', '.join(refs)}")

# ---------------- view: checklist & exports ----------------
elif nav == "3 · Art. 9 checklist":
    st.subheader(f"Article 9 checklist — {scope_label}")
    st.caption("Generated, never hand-assembled: legality baseline (relevant "
               "legal requirements) + risk add-ons (mitigation rules triggered "
               "by signed ratings). Every item states why it is requested.")

    is_complete, gaps = checklist_engine.completeness(
        conn, cycle["id"], sel_country["id"], region_id, sel_region_name
        if sel_region else None)
    if not is_complete:
        st.warning("Assessment incomplete — a generated checklist will be "
                   "marked DRAFT. Gaps: " + "; ".join(gaps[:6])
                   + ("…" if len(gaps) > 6 else ""))

    gen_row, gen_items = checklist_engine.latest_generation(
        conn, cycle["id"], sel_country["id"], region_id)
    stale = checklist_engine.is_stale(conn, gen_row, cycle["id"],
                                      sel_country["id"])

    c1, c2 = st.columns([1, 4], vertical_alignment="center")
    if c1.button("⚙️ Generate checklist", type="primary"):
        gid, items_, final_, gaps_ = checklist_engine.generate(
            conn, cycle["id"], sel_country["id"], region_id,
            sel_region["name"] if sel_region else None, operator)
        st.toast(f"Generated {len(items_)} items "
                 f"({'final' if final_ else 'DRAFT'}).")
        st.rerun()
    if gen_row:
        note = f"Latest generation {gen_row['generation_id']} · " \
               f"{gen_row['at']} · {gen_row['generated_by']}"
        if stale:
            c2.error(f"{note} — ⚠️ STALE: ratings or requirements changed "
                     "since generation. Regenerate.")
        else:
            c2.caption(note)

    if gen_items:
        current_group = None
        for it in gen_items:
            if it["grouping"] != current_group:
                current_group = it["grouping"]
                st.markdown(f"#### {current_group or 'Other'}")
            stream_tag = {"legality-baseline": "🏛️ baseline",
                          "risk-addon": "⚠️ risk add-on",
                          "merged": "🏛️⚠️ both"}[it["stream"]]
            esc = f" · **{it['escalation']}**" if it["escalation"] else ""
            st.markdown(f"- **{it['document_name']}** · {stream_tag}{esc}")
            with st.expander("Why is this requested?"):
                for j in json.loads(it["justification"]):
                    st.markdown(f"- {j}")

    st.divider()
    st.markdown("### Exports")
    st.caption("Files land in the exports folder with systematic names "
               "(KLK_EUDR_<country>_<region>_<cycle>_<type>_<date>) and every "
               "export is logged in the audit trail.")
    e1, e2, e3, e4 = st.columns(4)
    if e1.button("📄 Risk report (docx)"):
        path, final_ = exporter.risk_report_docx(conn, cycle, sel_country,
                                                 sel_region, operator)
        st.success(f"{'Final' if final_ else 'DRAFT'} report: `{path.name}`")
    if e2.button("📋 Checklist (docx)"):
        if gen_row:
            path = exporter.checklist_docx(conn, cycle, sel_country, sel_region,
                                           gen_row, gen_items, operator)
            st.success(f"Exported: `{path.name}`")
        else:
            st.error("Generate a checklist first.")
    if e3.button("📊 Checklist (xlsx)"):
        if gen_row:
            path = exporter.checklist_xlsx(conn, cycle, sel_country, sel_region,
                                           gen_row, gen_items, operator)
            st.success(f"Exported: `{path.name}`")
        else:
            st.error("Generate a checklist first.")
    if e4.button("🧾 Audit extract (xlsx)"):
        path = exporter.audit_xlsx(conn, cycle["year"], sel_country_name,
                                   operator)
        st.success(f"Exported: `{path.name}`")

# ---------------- view: audit trail ----------------
else:
    st.subheader("Audit trail")
    c1, c2 = st.columns(2)
    f_country = c1.selectbox("Country", ["All"] + country_names)
    events = sorted({r["event_type"] for r in db.audit_rows(conn, limit=1000)})
    f_event = c2.selectbox("Event type", ["All"] + events)
    rows = db.audit_rows(conn, limit=500,
                         country=None if f_country == "All" else f_country,
                         event_type=None if f_event == "All" else f_event)
    if rows:
        st.dataframe(
            [{"at": r["at"], "actor": r["actor"], "event": r["event_type"],
              "entity": f"{r['entity']}#{r['entity_id'] or ''}",
              "country": r["country"] or "", "section": r["section_code"] or "",
              "detail": (r["after_state"] or r["before_state"] or "")[:120],
              "reason": r["reason"] or ""} for r in rows],
            use_container_width=True, height=420)
    else:
        st.info("No audit events match the filter.")
