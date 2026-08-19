"""In-app research runner: builds the prompt from a template, invokes Claude Code
headlessly (`claude -p`) with the operator's existing login, and writes the
validated batch file to research/. No API key involved; nothing counts until the
batch is imported to the queue and human-approved.

Each run is two `claude -p` passes:
  1. Evidence gathering (WebSearch/WebFetch allowed) — Opus on a first-time run for
     a scope, Sonnet on a rerun (existing claims present), since a rerun is mostly
     incremental delta-finding and doesn't need the heavier model.
  2. Narrative drafting from the evidence just gathered — always Sonnet, no tools:
     it's pure writing from material already on hand, not a research task.
"""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RESEARCH_DIR = BASE_DIR / "research"
TEMPLATES_DIR = RESEARCH_DIR / "templates"
IMPORTED_DIR = RESEARCH_DIR / "imported"

EVIDENCE_SCHEMA_EXCERPT = """{
  "meta": {"country": "...", "region": "... or null", "cycle": 2026,
           "scope": ["S4"], "run_type": "risk|legal",
           "generated_at": "ISO timestamp", "template_version": "..."},
  "evidence": [
    {"section": "S4", "claim": "one factual statement", "value": "quantitative value or null",
     "source_name": "...", "publisher": "...", "url": "...",
     "source_type": "official|intergovernmental|academic|civil_society|media|industry|other — who produced it, NOT how reliable it is",
     "published": "date or unknown", "retrieved": "YYYY-MM-DD",
     "confidence": "low|medium|high", "significance": "low|medium|high",
     "req_type": "instrument|requirement|jurisprudence|treaty|policy (legal areas A1-A7 only, else null)",
     "authority": "issuing/administering body, e.g. 'MPOB' (legal areas only, else null)",
     "verification_docs": ["doc a supplier would produce as proof, e.g. 'EIA approval letter'"],
     "applicability": "plantation|smallholder|both (legal areas only, else null)",
     "supply_chain_node": ["business_partner|mill|refinery|source, whichever the law applies to (legal areas only, else null)"],
     "is_mandatory": "yes|no|conditional (legal areas only, else null)",
     "alt_document": "alternative document the law explicitly accepts in place of the primary one, else null (legal areas only)",
     "mandatory_condition": "when is_mandatory is 'conditional', the condition the law states (e.g. 'only above 25 ha'), else null (legal areas only)",
     "notes": "caveats or null"}
  ],
  "no_findings": [
    {"section": "S4", "searched_for": "...", "where_searched": ["..."]}
  ]
}"""

NARRATIVE_SCHEMA_EXCERPT = """{
  "meta": {"country": "...", "region": "... or null", "cycle": 2026,
           "scope": ["S4"], "run_type": "risk|legal",
           "generated_at": "ISO timestamp", "template_version": "..."},
  "narrative_drafts": [
    {"section": "S4", "text": "analytical prose with inline references ...",
     "sources": ["..."]}
  ]
}"""


def claude_available():
    return shutil.which("claude") is not None


def build_prompt(run_type, country, region, cycle_year, items, whitelist_rows,
                 existing_claims=None):
    """items: list of dicts with code/title/scope (sections or legal areas).
    existing_claims: {section_code: [claims]} already recorded — the run must
    not re-report them."""
    template = (TEMPLATES_DIR / f"{run_type}.md").read_text(encoding="utf-8")
    scopes = "\n".join(
        f"- {i['code']} — {i['title']}: {i.get('scope', '')}" for i in items)
    whitelist = "\n".join(
        f"- {s['name']}" + (f" ({s['publisher']})" if s["publisher"] else "")
        + (f" — {s['url_pattern']}" if s["url_pattern"] else "")
        for s in whitelist_rows)
    prompt_extra = ""
    if existing_claims and any(existing_claims.values()):
        lines = []
        for code, claims in existing_claims.items():
            for c in claims:
                lines.append(f"- [{code}] {c}")
        prompt_extra = (
            "\n\n## Already recorded — DO NOT re-report\n"
            "The following claims are already in the evidence base for this "
            "scope. Do not repeat them or restate them in different words; "
            "only report NEW information (new facts, newer data vintages, "
            "corrections, or genuinely different aspects). If nothing new "
            "exists for a section, say so via no_findings.\n"
            + "\n".join(lines))
    return template.format(
        country=country,
        region=region or "entire country",
        region_json=json.dumps(region),
        cycle=cycle_year,
        sections=", ".join(i["code"] for i in items),
        section_scopes=scopes,
        whitelist=whitelist or "- (none listed — use recognised primary sources)",
        schema_excerpt=EVIDENCE_SCHEMA_EXCERPT,
    ) + prompt_extra


def build_narrative_prompt(run_type, country, region, cycle_year, items,
                           evidence_records, existing_claims=None):
    template = (TEMPLATES_DIR / f"{run_type}_narrative.md").read_text(
        encoding="utf-8")

    by_section = {}
    for e in evidence_records:
        by_section.setdefault(e["section"], []).append(e)
    ev_lines = []
    for code, recs in by_section.items():
        ev_lines.append(f"### {code}")
        for r in recs:
            bits = [r["claim"]]
            if r.get("value"):
                bits.append(f"(value: {r['value']})")
            src = r["source_name"]
            if r.get("publisher"):
                src += f", {r['publisher']}"
            bits.append(f"— {src}")
            if r.get("url"):
                bits.append(f"({r['url']})")
            if r.get("retrieved"):
                bits.append(f"[retrieved {r['retrieved']}]")
            ev_lines.append("- " + " ".join(bits))
    evidence_block = "\n".join(ev_lines) or "(no evidence found this run)"

    existing_lines = []
    if existing_claims:
        for code, claims in existing_claims.items():
            for c in claims:
                existing_lines.append(f"- [{code}] {c}")
    existing_block = "\n".join(existing_lines) or "(none)"

    return template.format(
        country=country,
        region=region or "entire country",
        region_json=json.dumps(region),
        cycle=cycle_year,
        sections=", ".join(i["code"] for i in items),
        evidence_block=evidence_block,
        existing_block=existing_block,
        schema_excerpt=NARRATIVE_SCHEMA_EXCERPT,
    )


def extract_json(text):
    """Claude is instructed to return bare JSON, but strip fences defensively."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in research output.")
    return json.loads(text[start:end + 1])


def validate_batch(batch):
    """Structural validation per research/schema.json (hand-rolled, no deps)."""
    errors = []
    meta = batch.get("meta")
    if not isinstance(meta, dict):
        errors.append("missing meta")
    else:
        for f in ("country", "cycle", "scope", "run_type"):
            if f not in meta:
                errors.append(f"meta.{f} missing")
        if meta.get("run_type") not in ("risk", "legal"):
            errors.append("meta.run_type must be risk|legal")
    ev = batch.get("evidence")
    if not isinstance(ev, list):
        errors.append("evidence must be a list")
    else:
        for i, e in enumerate(ev):
            for f in ("section", "claim", "source_name", "retrieved"):
                if not e.get(f):
                    errors.append(f"evidence[{i}].{f} missing")
    for nd in batch.get("narrative_drafts", []) or []:
        if not nd.get("section") or not nd.get("text"):
            errors.append("narrative_drafts entries need section and text")
    return errors


def _invoke_claude(prompt, model, allowed_tools, timeout_s):
    if not claude_available():
        raise RuntimeError(
            "Claude Code CLI ('claude') not found on PATH. Research runs need "
            "Claude Code installed — use the chat fallback instead.")
    cmd = ["claude", "-p", "--output-format", "text"]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]
    if model:
        cmd += ["--model", model]
    # Strip harness/session variables so the CLI uses the user's own login,
    # not a parent Claude session's piped authentication.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CLAUDE", "ANTHROPIC"))}
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout_s, shell=True,
                          env=env)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "")[:800]
        if "authenticate" in detail.lower() or "oauth" in detail.lower():
            raise RuntimeError(
                "Claude CLI login has expired. Open a terminal, run `claude`, "
                "and complete the login (/login) once — then retry the research "
                f"run. Details: {detail}")
        raise RuntimeError(f"claude -p failed (exit {proc.returncode}): {detail}")
    return proc.stdout


def draft_narrative(run_type, country, region, cycle_year, items, ev_records,
                    existing_claims=None, model="sonnet", timeout_s=600,
                    attempts=2):
    """Run the narrative pass (no tools) over `ev_records` and return the list
    of {section, text, sources} drafts. Retries if Claude returns valid JSON
    but no usable drafts — an empty result is a failure, not a silent
    success, because the operator would otherwise face a blank textarea with
    no hint anything went wrong. Raises RuntimeError after `attempts`."""
    wanted = {i["code"] for i in items} & {e["section"] for e in ev_records}
    if not wanted:
        raise RuntimeError("No evidence to draft from.")
    prompt = build_narrative_prompt(run_type, country, region, cycle_year, items,
                                    ev_records, existing_claims=existing_claims)
    last_problem = "no attempt made"
    for _ in range(max(1, attempts)):
        out = _invoke_claude(prompt, model, None, timeout_s)
        try:
            drafts = extract_json(out).get("narrative_drafts", []) or []
        except ValueError as err:
            last_problem = str(err)
            continue
        drafts = [d for d in drafts
                  if d.get("section") and (d.get("text") or "").strip()]
        got = {d["section"] for d in drafts}
        if wanted <= got:
            return drafts
        missing = ", ".join(sorted(wanted - got))
        last_problem = f"narrative pass returned no text for {missing}"
        if drafts:
            # Partial result — keep what we have rather than throw it away.
            return drafts
    raise RuntimeError(f"Narrative drafting failed: {last_problem}")


def run_research(run_type, country, region, cycle_year, items, whitelist_rows,
                 timeout_s=1800, existing_claims=None,
                 research_model=None, narrative_model=None):
    """Invoke claude -p (evidence pass, then narrative pass); returns
    (batch_path, batch_dict). Raises on failure of the evidence pass; a
    failed narrative pass is non-fatal — the evidence found is still kept."""
    is_rerun = bool(existing_claims and any(existing_claims.values()))
    research_model = research_model or ("sonnet" if is_rerun else "opus")
    narrative_model = narrative_model or "sonnet"

    evidence_prompt = build_prompt(run_type, country, region, cycle_year, items,
                                   whitelist_rows, existing_claims=existing_claims)
    evidence_out = _invoke_claude(evidence_prompt, research_model,
                                  "WebSearch,WebFetch", timeout_s)
    batch = extract_json(evidence_out)
    errors = validate_batch(batch)
    if errors:
        raise ValueError("Batch failed validation: " + "; ".join(errors[:10]))
    batch.setdefault("narrative_drafts", [])

    ev_records = batch.get("evidence", [])
    if ev_records:
        try:
            batch["narrative_drafts"] = draft_narrative(
                run_type, country, region, cycle_year, items, ev_records,
                existing_claims=existing_claims, model=narrative_model,
                timeout_s=min(600, timeout_s))
        except Exception as err:
            # Don't lose evidence already found just because the narrative
            # pass failed — flag it and let the human write/redo it later
            # (the section card offers a "Generate narrative draft" button).
            batch.setdefault("meta", {})["narrative_error"] = str(err)[:500]

    batch.setdefault("meta", {})["generated_at"] = datetime.now().isoformat(
        timespec="seconds")
    scope_tag = "-".join(i["code"] for i in items)[:40]
    region_tag = f"_{region.replace(' ', '')}" if region else ""
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = RESEARCH_DIR / f"{country.replace(' ', '')}{region_tag}_{run_type}_{scope_tag}_{stamp}.json"
    path.write_text(json.dumps(batch, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path, batch


def pending_batches(country=None, run_type=None):
    """Batch files in research/ not yet imported. If `country` is given,
    only returns batches whose meta.country matches — otherwise a batch
    fetched for one country shows up as "awaiting import" on every other
    country's page too, since they all share the same research/ folder.
    If `run_type` is given too, also filters to that risk|legal batch kind —
    so the risk-only and legal-only import lists on their respective pages
    don't cross-list each other's batches."""
    RESEARCH_DIR.mkdir(exist_ok=True)
    paths = sorted(p for p in RESEARCH_DIR.glob("*.json")
                   if p.name != "schema.json")
    if country is None and run_type is None:
        return paths
    matched = []
    for p in paths:
        try:
            meta = json.loads(p.read_text(encoding="utf-8")).get("meta", {})
        except (ValueError, OSError):
            continue
        if country is not None and meta.get("country") != country:
            continue
        if run_type is not None and meta.get("run_type") != run_type:
            continue
        matched.append(p)
    return matched


def mark_imported(path: Path):
    IMPORTED_DIR.mkdir(exist_ok=True)
    target = IMPORTED_DIR / path.name
    path.rename(target)
    return target
