"""Background research runs. Each run executes in a daemon thread inside the
web process: the UI stays responsive while Claude researches; results are
imported to the review queue the moment each section's batch finishes. Runs
live in an in-process registry; completed batch files also land in research/
so nothing is lost if the app restarts mid-run (the import banner picks them
up).

A run covering multiple sections/legal areas fans out into one `claude -p`
subprocess PER ITEM, run concurrently (bounded by MAX_CONCURRENT_RESEARCH).
Each item gets its own dedicated, unhurried research pass and its own
item-specific whitelist slice — this keeps per-section depth/relevance high
while cutting overall wall-clock roughly in proportion to the concurrency
cap, instead of one process serially working through every section.

Before Claude touches a section, `core.fetchers.REGISTRY` is checked for a
public-data-API fetcher registered against that section code (S4 -> Global
Forest Watch, S5 -> World Bank governance indicators, S8 -> ILO child
labour, S2 -> FAOSTAT forest area). If one exists, it runs first and its
results are imported immediately and also fed to Claude as "already
recorded" facts — so Claude spends its pass on the qualitative/narrative
work those APIs can't do, instead of re-deriving numbers a deterministic
API already has. A fetcher failing (API down, no key, no fallback for that
country) is non-fatal — Claude still runs the section normally."""

import itertools
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from . import db, fetchers, importer, researcher

_lock = threading.Lock()
_counter = itertools.count(1)
RUNS = {}

# How many `claude -p` research subprocesses run at once for a single multi-
# section run. Kept modest to avoid hammering API/CLI rate limits while still
# giving a real speedup over full serialization.
MAX_CONCURRENT_RESEARCH = 3


def _existing_claims(conn, country, cycle_year, codes):
    existing = {}
    for row in conn.execute(
            "SELECT e.section_code, e.claim FROM evidence e"
            " JOIN countries c ON c.id=e.country_id"
            " JOIN assessment_cycles cy ON cy.id=e.cycle_id"
            " WHERE c.name=? AND cy.year=?"
            " AND e.status IN ('pending','approved')",
            (country, cycle_year)):
        if row["section_code"] in codes:
            existing.setdefault(row["section_code"], []).append(row["claim"])
    return existing


def _whitelist_for_item(code, whitelist):
    return [s for s in whitelist
            if s["applies_to"] == "all" or code in s["applies_to"].split(",")]


def start_run(run_type, country, region, cycle_year, items, whitelist, actor):
    run_id = next(_counter)
    info = {
        "id": run_id, "run_type": run_type, "country": country,
        "region": region, "scope": [i["code"] for i in items],
        "status": "running", "started": datetime.now().strftime("%H:%M"),
        "summary": None, "error": None,
    }
    with _lock:
        RUNS[run_id] = info

    def _fetch_api_evidence(conn, item):
        """Runs the registered public-data fetcher for this section, if any.
        Returns (summary_or_None, error_or_None) — never raises."""
        if run_type != "risk":
            return None, None
        module = fetchers.REGISTRY.get(item["code"])
        if module is None:
            return None, None
        row = conn.execute("SELECT iso3 FROM countries WHERE name=?",
                           (country,)).fetchone()
        if row is None:
            return None, None
        try:
            summary = fetchers.fetch_and_import(
                conn, module, row["iso3"], country, region, cycle_year, actor)
            return summary, None
        except Exception as err:
            return None, f"{module.SOURCE_TAG} fetch failed: {err}"

    def research_one(item):
        """Runs the section's API fetcher (if any) then Claude, importing
        both. Own DB connection since this executes on a worker thread."""
        conn = db.get_conn()
        try:
            api_summary, api_err = _fetch_api_evidence(conn, item)
            existing = _existing_claims(conn, country, cycle_year, [item["code"]])
            item_whitelist = _whitelist_for_item(item["code"], whitelist)
            path, batch = researcher.run_research(
                run_type, country, region, cycle_year, [item], item_whitelist,
                existing_claims=existing)
            summary = importer.import_batch(conn, path, actor)
            narr_err = (batch.get("meta") or {}).get("narrative_error")
            if narr_err:
                msg = (f"narrative draft not produced ({narr_err[:120]}) — "
                       "evidence was kept; use 'Generate narrative draft' on "
                       "the section card after approving it")
                api_err = f"{api_err}; {msg}" if api_err else msg
            if api_summary:
                for key in ("evidence", "unlisted", "duplicates", "drafts"):
                    summary[key] += api_summary[key]
                summary["no_findings"] += api_summary["no_findings"]
            # api_err is a soft warning (a fetcher failed but Claude's pass
            # for this section still succeeded) — surfaced, not fatal.
            return item["code"], summary, None, api_err
        except Exception as err:
            return item["code"], None, str(err), api_err
        finally:
            conn.close()

    def work():
        conn = db.get_conn()
        db.audit(conn, "research_run_started", "research", country=country,
                 after={"run_type": run_type, "scope": info["scope"]},
                 actor=actor)
        conn.commit()
        conn.close()

        totals = {"evidence": 0, "unlisted": 0, "duplicates": 0, "drafts": 0,
                  "no_findings": []}
        errors = []
        warnings = []
        workers = min(MAX_CONCURRENT_RESEARCH, len(items)) or 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(research_one, item) for item in items]
            for fut in as_completed(futures):
                code, summary, err, api_err = fut.result()
                if api_err:
                    warnings.append(f"{code}: {api_err}")
                if err:
                    errors.append(f"{code}: {err}")
                else:
                    totals["evidence"] += summary["evidence"]
                    totals["unlisted"] += summary["unlisted"]
                    totals["duplicates"] += summary["duplicates"]
                    totals["drafts"] += summary["drafts"]
                    totals["no_findings"] += summary["no_findings"]

        conn = db.get_conn()
        info["summary"] = totals
        if errors and totals["evidence"] == 0 and totals["drafts"] == 0:
            info["status"] = "failed"
            info["error"] = "; ".join(errors)
        elif errors or warnings:
            info["status"] = "completed"
            parts = []
            if errors:
                parts.append("Partial — failed sections: " + "; ".join(errors))
            if warnings:
                parts.append("Public-data fetch warnings: " + "; ".join(warnings))
            info["error"] = " | ".join(parts)
        else:
            info["status"] = "completed"
        db.audit(conn, "research_run_finished" if not errors
                 else "research_run_failed", "research", country=country,
                 after={"summary": {k: v for k, v in totals.items()
                                    if k != "no_findings"},
                        "errors": errors} if errors else totals,
                 actor=actor)
        conn.commit()
        conn.close()

    threading.Thread(target=work, daemon=True,
                     name=f"research-run-{run_id}").start()
    return run_id


def runs():
    with _lock:
        return sorted(RUNS.values(), key=lambda r: -r["id"])


def dismiss(run_id):
    with _lock:
        RUNS.pop(run_id, None)


def any_running():
    with _lock:
        return any(r["status"] == "running" for r in RUNS.values())
