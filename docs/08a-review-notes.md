# 08a — Review notes on the UI migration brief

**Status:** companion to [08-ui-migration-brief.md](08-ui-migration-brief.md). Read both.
**Scope:** 08 stands as written except for the four corrections below, plus four gaps it
does not cover.
**Deployment context that shapes these notes:** local, single-user now; colleagues on the
KLK network later. Several of 08's recommendations are correct for the shared case and
premature for the local one.

---

## Part 1 — Corrections

### 1.1 Autosave drafts (08 §3.5) — do not implement

`db.save_draft` writes an `audit_log` row on every call (`core/db.py:492`). A debounced
autosave on the narrative textarea therefore produces hundreds of `assessment_draft_saved`
rows per narrative written. In a tool whose value rests on an audit trail an external
reviewer can read, that is not a performance concern — it is a legibility failure.

Avoiding it means either a separate non-audited draft store or a suppression flag in
`save_draft`, both of which are changes to `core/` that 08 Part 7 rules out. The document
contradicts itself here.

**Instead:** keep the explicit "Save draft" button, and take the `beforeunload` guard
(08 §3.4). That addresses the actual risk — losing work to a misclick — at no audit cost.

### 1.2 Server-Sent Events for run status (08 §3.6) — use htmx polling

One operator, one research run at a time, runs lasting up to 30 minutes
(`core/researcher.py:118`, `timeout_s=1800`). `hx-trigger="every 5s"` on the banner
element is one attribute and does the same job. SSE introduces a long-lived connection and
worker-affinity considerations for a region of the page that changes twice an hour.

Revisit only if the banner is ever needed for many concurrent runs.

### 1.3 Operator identity (08 §2.1, Part 6 step 3) — build the seam, not the login screen

08's analysis is correct and important: `getpass.getuser()` (`app.py:34`) resolves to the
*server's* account once this is hosted, which would attribute every sign-off to whoever
launched uvicorn. The editable "Operator" text input (`app.py:39`) is not attribution.

But 08 treats this as binary — text box bad, login good — and orders full authentication
before any write path exists. For a local-first port that front-loads work with no local
benefit.

**The port's deliverable is the boundary, not the login.** Remove the import-time
`getpass.getuser()` call and the editable field, and route every `actor` value through a
single function — `current_actor(request)`. Locally its body reads a name from a signed
cookie, which is no weaker than today's behaviour. Moving to the KLK network replaces that
one function body and nothing else.

Build the seam during the port. Build the login when it is shared, and treat 08 §2.1 as
binding at that point.

### 1.4 `research_runs` table (08 §2.2, option b) — right idea, wrong phase

Moving run state into SQLite is the correct end state, and 08's argument that runs would
then survive a restart is sound. But it is a schema change inside a port that is otherwise
meant to be mechanical, and it contradicts Part 7's instruction not to touch `core/`.

**For the port:** take option (a) — pin `--workers 1` and document it. The divergent
per-worker `RUNS` dict is a real problem only under multiple workers, which single-user
local deployment does not have.

Build the table when the app goes multi-user, alongside the auth work in 1.3.

### 1.5 On Part 4

Part 4 is larger than Parts 1–3 combined. Overview screen, evidence queue, section page
rebuild, status system and audit rebuild together plausibly exceed the entire port. Nothing
in it is wrong; it should be read as a menu, not a checklist to complete.

Highest value first three, in order:

1. **Overview screen** (§4.2) — genuinely absent today, and the only thing that answers
   "how far along am I".
2. **Rating pills** (§4.5) — cheap, and fixes a real defect: `RATING_DOT` (`app.py:16`)
   maps seven values onto four emoji, reuses green across two unrelated scales, and
   carries no text, so it fails both colourblind readers and monochrome printing.
3. **Keyboard shortcuts on the evidence queue** (§4.3) — the highest-volume repetitive
   task in the app.

---

## Part 2 — Gaps

### 2.1 There is no dependency file

No `requirements.txt`, `pyproject.toml` or lockfile exists anywhere in the project.
Dependencies are implicit from imports: `streamlit`, `python-docx`, `openpyxl`, otherwise
stdlib. The migration must author one — it is also the mechanism by which this reaches a
colleague's machine, which is a stated driver.

### 2.2 `.claude/launch.json` hardcodes the Streamlit launch

`.claude/launch.json:7` runs `-m streamlit run app.py --server.port 8501`. It needs a
uvicorn entry, or the dev-server launch breaks silently after the port.

### 2.3 No rollback or parallel-run instruction

Keep Streamlit serving on 8501 while the new app runs on 8000, until the parity test in
08 Part 6 passes. 08 §6.7 implies this by asking for a walkthrough "in both apps"; it
should be stated as a requirement, because the alternative is discovering a gap after
`app.py` is gone.

### 2.4 Batch intake has no upload path

`researcher.pending_batches()` (`core/researcher.py:161`) globs JSON files from the
`research/` directory on the server's own disk. That works on a laptop. A colleague on a
shared server cannot put a file there, so the manual-import channel described in
`02-research-runs.md` becomes unreachable for everyone except whoever can log into the
host.

08 covers exports leaving the server (§2.5) but not batches arriving. A
`POST /research/batches` upload endpoint feeding `importer.import_batch` is needed before
multi-user.

---

## Part 3 — What was verified

08's claims were spot-checked against the code rather than taken on trust. Confirmed by
direct inspection: `RATING_DOT` at `app.py:16` is as described; `app.py:413` labels a
button "Show" and calls `runmanager.dismiss()`; `app.py:34` seeds the operator from
`getpass.getuser()`; `app.py:484-485` accepts dates as free text; `db.save_draft`
(`core/db.py:467`) audits on every call; and `core/` contains zero `streamlit` imports, so
the "UI layer only" premise of the whole brief holds.

Two parts of 08 should be followed most closely:

- **Part 0** — port fully, verify parity, then redesign. Blending the two makes it
  impossible to tell a porting bug from a design change, and the audit trail is the thing
  that cannot be subtly wrong.
- **The Part 6 parity test** — walk one country end to end in both apps, then diff the
  `audit_log` tables for the same events, order, actor and reasons. This is the strongest
  thing in the document and the correct gate between the port and the redesign.
