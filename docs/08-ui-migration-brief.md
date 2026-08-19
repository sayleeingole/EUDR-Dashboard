# 08 — UI migration brief: Streamlit → HTML

**Status:** reference document. Written before the migration starts, to be handed to
the implementing session.
**Scope:** replace `app.py` (692 lines of Streamlit) with a web UI. `core/` stays.
**Author's note:** this is a compliance tool. Every design decision below is
subordinate to one rule — *the interface must never make it easy to record
something the operator did not mean to record.*

---

## Part 0 — Read this first: what the migration actually is

This is **two projects wearing one coat**, and they must be sequenced, not blended:

| | Project A — port | Project B — redesign |
|---|---|---|
| Goal | Same behaviour, new plumbing | Better behaviour |
| Risk | Low, mechanical | Medium, judgement calls |
| Test | "Does it still do what Streamlit did?" | "Is it faster to use?" |

**Do A first, completely, then B.** If you redesign while porting, you will not
know whether a bug is a porting mistake or a design change, and the audit trail
is the thing you cannot afford to get subtly wrong. Get a working, ugly,
feature-identical HTML app. Verify parity. *Then* apply Part 4.

---

## Part 1 — Stack recommendation

**Recommended: FastAPI + Jinja2 templates + htmx + a small amount of vanilla JS.**
No build step, no npm, no bundler, no React.

Why this and not a SPA:
- The app is **forms and lists over a database**. That is exactly what
  server-rendered HTML is best at. A React SPA would mean writing every screen
  twice (API contract + client state) for zero user-visible benefit.
- Deployment to colleagues is a stated driver. "Run one Python process" is a
  dramatically easier story than "build the frontend, serve static assets,
  configure CORS."
- `core/` already returns `sqlite3.Row` objects. Jinja renders those directly.
  A SPA needs a serialization layer (Pydantic models for every entity) that
  currently does not exist.
- htmx gives you the *one* thing Streamlit did well — "click something, part of
  the page updates" — without the full-page rerun that makes Streamlit feel slow.

Use `hx-post` / `hx-target` / `hx-swap` for: approve/reject evidence, save draft,
refine requirement, dismiss a run banner. Each returns an HTML fragment, not JSON.

Add **Alpine.js** only if you find yourself writing more than ~50 lines of vanilla
JS for local UI state (modal open/closed, tab switching). Do not add both htmx and
a framework that duplicates it.

**Templating structure:**
```
templates/
  base.html                 # shell: header, nav, toasts, modal host
  _macros.html              # rating pill, status badge, reason field, empty state
  partials/                 # htmx fragment targets — the important folder
    evidence_row.html
    section_card.html
    run_banner.html
    requirement_row.html
  views/
    risk.html  legal.html  checklist.html  audit.html  cycles.html
static/
  app.css                   # ONE stylesheet, design tokens at the top
  app.js                    # small: toasts, modal, beforeunload, shortcuts
```

**Explicitly reject:** Streamlit-in-a-frame hacks, Gradio, Dash, Panel, Reflex,
NiceGUI. All of them reintroduce the same rerun-and-widget-state model you are
migrating away from.

---

## Part 2 — The seven things that will actually break

These are not style issues. These are correctness landmines in the port. Every one
of them is invisible until it bites.

### 2.1 🔴 `getpass.getuser()` becomes the *server's* user — CRITICAL

`app.py:34` seeds the operator from `getpass.getuser()`. In Streamlit-on-localhost
that is the person sitting at the machine. **On a web server it is the account
running uvicorn** — so every sign-off in the audit trail would be attributed to
`svc_eudr` or whoever launched the process, for every user.

This is a compliance-integrity failure, not a UX bug. `sign_assessment`,
`decide_evidence`, `refine_requirement`, and every `db.audit()` call take `actor`
as a parameter — they are fine. The *source* of that value must change.

**Required:** real per-request identity before this is shared with anyone.
- Minimum viable: a login screen with a signed session cookie, operator chosen
  from a users table. Not a text box the user can type anything into.
- Better, if it will live on the KLK network: Windows/AD integration or an
  SSO reverse proxy passing a header.
- The current editable "Operator" text input (`app.py:39`) must **not** survive
  the migration. A field where you type who you are is not attribution.

Until auth exists, if you run it multi-user, every audit row is unreliable.

### 2.2 🔴 Background research threads vs. multiple workers

`runmanager.py` keeps runs in a module-level dict `RUNS` and spawns daemon
threads *inside the process*. This works because Streamlit is one process.

Under `uvicorn --workers 4`, each worker gets its **own** `RUNS` dict. A run
started on worker 1 is invisible to a status poll that lands on worker 3. The
banner will flicker in and out depending on which worker answers.

Also: `--reload` in development kills in-flight threads on every file save.

**Required:** either
- (a) pin to **one** uvicorn worker (`--workers 1`) and document it loudly — the
  app is low-traffic, this is a legitimate choice; or
- (b) move run state into SQLite (a `research_runs` table). This is the correct
  fix and has a bonus: runs survive an app restart, which they currently do not.
  `runmanager.py` line 3's own docstring admits the batch file is the only thing
  that survives today.

Recommend (b) — it is maybe 40 lines and it removes a whole class of "why did the
banner disappear" support questions.

### 2.3 🟠 SQLite concurrency

`db.get_conn()` uses `check_same_thread=False` and `app.py` caches one connection
via `@st.cache_resource`. That is a single connection shared across threads.

Under a web server with concurrent requests plus a background research thread
writing, you will hit `database is locked` — SQLite's default busy timeout is 0.

**Required:**
- `PRAGMA journal_mode=WAL` (readers don't block the writer). One-time setting.
- `PRAGMA busy_timeout=5000`.
- One connection **per request** (FastAPI dependency), not one global. Keep the
  background thread's own connection as it already is (`runmanager.py:30`).
- Keep `PRAGMA foreign_keys=ON` — it is already there, don't lose it.

### 2.4 🟠 Nothing currently prevents two people signing the same section

Streamlit hid this because it was single-user. `sign_assessment` versions
assessments, so two simultaneous signs produce v3 and v4 with no warning that
the second person never saw the first person's conclusion.

**Required at minimum:** when rendering the "Assess & sign" form, embed the
version the operator is working from as a hidden field. On submit, if the current
version is higher, refuse and show "X signed v3 while you were editing — review
their conclusion before signing." Optimistic concurrency, ~15 lines, prevents a
genuinely bad compliance outcome.

### 2.5 🟠 Exports write to a folder the browser cannot reach

`exporter.py` writes into `exports/` and `app.py:653` reports the filename. On a
server, "the file is at `exports/KLK_EUDR_...docx`" means nothing to a user on
another machine.

**Required:** generate, then return as an HTTP download
(`FileResponse` with `Content-Disposition: attachment`). Keep writing the file to
`exports/` as the archival copy — `_audit_export()` logs it and that log entry
should stay truthful. Add an "Export history" list so past exports are
re-downloadable rather than regenerated.

### 2.6 🟡 The `claude -p` subprocess must still be reachable

`researcher.py:38` has `claude_available()`. On a shared server, the service
account needs the CLI installed and authenticated. This will not be true by
default. Surface it: if `claude_available()` is false, the "Run research" button
should be disabled with an explanation, not fail after the user clicks.

### 2.7 🟡 Widget-state hacks disappear (good) — check what depended on them

`app.py:346-349` has an explicit workaround: session-state shadowing a prefill
that arrived later. In HTML this class of bug vanishes, because you render the
value into the `<textarea>` server-side. **Delete the workaround, don't port it.**
Same for every `key=f"...{ws_key}"` — those exist only to keep Streamlit widgets
distinct across reruns and have no HTML equivalent. Do not translate them into
`id` attributes out of habit.

---

## Part 3 — Free wins HTML gives you that Streamlit could not

Take all of these. They are cheap and they are the reason the migration is worth
doing beyond looks.

1. **URLs.** `/risk/malaysia/sabah#S4` is bookmarkable, shareable, e-mailable,
   and works with the browser back button. Streamlit has none of this. This alone
   changes how the tool gets used in a team — "look at this section" becomes a
   link instead of a five-step instruction.
2. **Print stylesheet.** Compliance people print and PDF things for meetings.
   A `@media print` block that hides nav/buttons and expands all collapsed
   content is ~30 lines and will get used constantly.
3. **Real keyboard support.** Approve/reject the evidence queue with `A` / `R`,
   `J`/`K` to move between items. The evidence review queue is the highest-volume
   repetitive task in the app; keyboard support there is the single biggest
   time-saver available.
4. **`beforeunload` guard.** Warn on navigating away from an unsaved narrative.
   Currently a mis-click loses the draft silently.
5. **Autosave drafts.** `save_draft` already exists in `db.py:467`. Call it on a
   debounce from the narrative textarea. Removes the "Save draft" button as a
   thing users must remember.
6. **Server-Sent Events for run status.** Replaces
   `@st.fragment(run_every="5s")` (`app.py:394`) — which polls the entire fragment
   every 5 seconds whether or not anything changed. SSE pushes only on change:
   less server load, instant updates, no flicker.
7. **Real focus management and `aria-live`.** Toasts and status changes can be
   announced to screen readers. Streamlit gave you no control here.
8. **Deep-linkable audit trail.** Filter state in the query string, so an auditor's
   filtered view can be sent as a link.

---

## Part 4 — The redesign (apply after parity)

### 4.1 Information architecture — the core problem

Today: one page, four radio-button "views", everything else stuffed into a
sidebar and three levels of collapsibles (container → expander → popover).

The real structure is **three different jobs with different rhythms**:

| Job | Frequency | Belongs |
|---|---|---|
| Review evidence (approve/reject) | Many times a day, repetitive | Its own dedicated queue |
| Assess & sign a section | A few times a week, deliberate | Focused single-section page |
| Administer cycles, sources, countries | A few times a year | Settings area, off the main path |

**Proposed navigation:**
```
┌ header ────────────────────────────────────────────────────────┐
│ KLK EUDR   [Malaysia ▾] [Sabah ▾]   Cycle 2026 ●open   S.Ingole│
├────────────────────────────────────────────────────────────────┤
│ Overview │ Evidence (12) │ Sections │ Legal │ Checklist │ Audit │
└────────────────────────────────────────────────────────────────┘
```
- Country/region become a **scope switcher in the header**, not sidebar widgets.
  They are context, not settings — the same relationship a repo has to a file tree.
- Cycle management, add country/region, source whitelist → **Settings**. They
  currently sit at the same visual weight as the country picker despite being
  annual actions (fixes review point 6).
- Evidence gets its **own tab with a live count** — it is the highest-volume task
  and today it is scattered inline across ten section cards.

### 4.2 New screen: Overview (does not exist today — highest-value addition)

Fixes review point 4. Landing page for the selected country/region:

- **Progress ring / bar:** "6 of 10 sections signed" — the one number that
  answers "how far along am I."
- **Section status grid:** 10 tiles, each showing code, title, rating pill,
  and status. Click → that section. This replaces scroll-and-hunt (point 10).
- **What needs me now:** evidence pending, sections with drafts but no signature,
  stale checklist, requirements awaiting refinement. Each links directly to
  the thing.
- **Blockers to completion:** surface `checklist_engine.completeness()` gaps
  *here*, at the start, not buried in the checklist tab after the fact
  (`app.py:602`). Today you discover you are incomplete only when you try to
  generate.
- **Recent activity:** last 5 audit events, humanised. Cheap trust signal.

### 4.3 New screen: Evidence queue

Fixes points 1, 3, 13. One record at a time or a dense list — offer both.

- **Claim is the hero.** Large type. Source, date, origin, flags are metadata
  underneath at genuinely lower weight (fixes point 9's inverse problem here).
- **Symmetric decisions.** Approve and Reject are the same shape, size, and
  weight — both labeled with words. Today `✓` fires instantly while `✗` opens a
  popover; that asymmetry causes accidental approvals.
- **Approve needs a beat.** Either a brief undo window (toast with "Undo", 5s)
  or a confirm on the *first* action of a session. `decide_evidence` writes to
  the audit trail — a single stray click should not be able to do that silently.
  Undo is better than a confirm dialog: it does not tax the 200 correct clicks
  to protect against the 1 wrong one.
- **Flags are prominent, not a `⚠️` glyph in a caption.** `unlisted-source` and
  `possible-duplicate` change what the operator should do — they deserve a
  colored banner on the row.
- **Keyboard:** `A` approve, `R` reject, `J`/`K` navigate, `U` undo.
- **Batch approve** for records from a whitelisted source with no flags, with the
  count stated plainly ("Approve all 7 unflagged WRI records?").

### 4.4 Rebuilt: Section assessment page

Fixes points 3, 11, 12. One section, one page, no nesting.

Layout, top to bottom, no collapsibles in the primary path:
1. **Header:** section code, title, article refs, current status, rating pill.
2. **Signature block** — if signed. Given legal weight: who, when, version, in
   readable type, visually distinct (bordered, tinted). Today this is caption
   text the same size as a retrieval date (point 9).
3. **Evidence** — approved records for this section, listed. Not hidden behind
   a popover inside an expander. The operator is being asked to make a judgement;
   the basis for the judgement must be visible while they make it.
4. **Rules** — checkboxes with the suggested rating, as today, but showing the
   rationale inline rather than in a `help` tooltip.
5. **Rating** — segmented control. **Show the scale's meaning.** Three different
   scales exist (`low/medium/high`, `supportive/neutral/weak`, `low/standard/high`
   — `app.py:320-325`) and today you only discover which applies after opening
   the section (point 11). Label it: "Benchmark scale — how this country compares."
6. **Override reason** — appears when confirmed ≠ suggested. Make the divergence
   *visible*: "Rules suggest **medium**, you selected **high**." Today it is an
   unlabeled text box appearing out of nowhere.
7. **Narrative** — generous height, autosaving, character/word count, and a clear
   marker if it was pre-filled from a research draft (`app.py:341`).
8. **Sign** — the only primary-colored button on the page. Confirmation summarises
   what is about to be recorded: rating, override, version number, attributed name.

### 4.5 The status & rating system (fixes point 5)

Current `RATING_DOT` (`app.py:16`) maps 7 values onto 4 emoji, reuses green/yellow/red
across two unrelated scales, and relies on color alone.

**Replace with a pill component carrying three redundant signals:**
color + text label + shape/icon.

| Meaning | Color | Shape | Text |
|---|---|---|---|
| Low risk / supportive | green | ● filled | "Low" |
| Medium / neutral / standard | amber | ◐ half | "Medium" |
| High / weak | red | ▲ triangle | "High" |
| Not signed | gray | ○ hollow | "Not signed" |
| To reverify | blue | ↻ | "To reverify" |

Rules:
- **Never color alone.** Every pill carries its text (fixes colorblind access —
  ~8% of men have some CVD, and this is a document that gets printed in mono).
- **Drop emoji for status.** They render differently on Windows/Mac/Linux and
  cannot be styled, sized, or printed reliably. Use CSS shapes or inline SVG.
- Keep emoji only as decorative accents in headings, if at all.
- The "to reverify" state (`app.py:243`) is genuinely distinct — a rolled-forward
  rating carried from last year that nobody has confirmed. It deserves its own
  visual treatment, not a `🔁` prepended to the old rating.

### 4.6 The reason-capture pattern (fixes point 8)

Five different reason flows exist today, each hand-rolled, each validated
differently: override, reopen, source approval, rejection, requirement refinement.

**Make one macro.** Same label style, same placeholder guidance, same required
marker, same inline error, same minimum-length rule. Because these strings end up
in the permanent audit trail, add:
- a minimum length (a reason of "ok" is worse than useless to a future auditor),
- a hint of what a good reason contains,
- the recently-used reasons for that field as one-click options.

### 4.7 Forms and validation (fixes points 7, 12)

- **Dates:** `<input type="date">`. `app.py:484-485` accepts free text with the
  format only hinted in the label; nothing stops garbage entering evidence that
  feeds the legality baseline. Validate server-side too — never trust the client.
- **Group the manual-evidence form** into three labeled fieldsets: *The claim* /
  *The source* / *Dates & notes*. Today it is one undifferentiated column of ten
  inputs (`app.py:468-487`).
- **Inline errors** next to the offending field, not a single `st.error` at the
  bottom of the form.
- **Never lose input on a validation failure.** Re-render with values intact.
  Streamlit's `clear_on_submit=True` (`app.py:469`) plus a validation error is
  a data-loss bug the port must not reproduce.
- **URL field:** validate it parses, and show the matched whitelist source if the
  domain matches one — cheap, prevents a whole category of unlisted-source flags.

### 4.8 Audit trail (fixes point 14)

Currently a raw dataframe dump (`app.py:684`) for what is the single most
compliance-relevant screen.

- Date range filter, free-text search, actor filter — plus the existing country
  and event-type filters.
- **Visual emphasis on the events that matter**: overrides, reopens, rejections,
  unlisted-source approvals. An auditor scans for exceptions, not for the routine.
- Group by day with readable headers, rather than 500 flat rows.
- Expandable rows showing full before/after JSON — currently truncated to 120
  chars with no way to see the rest.
- CSV/XLSX export straight from the filtered view.
- Pagination or virtualisation — `limit=500` is a silent cap today; users will not
  know rows are missing.

### 4.9 Visual design direction

Keep the existing palette as the seed — `.streamlit/config.toml` already has
`#0F6E56` primary on a near-white ground, which is a good, sober, appropriate
choice for this domain. Carry it over as CSS custom properties.

```css
:root {
  --brand:        #0F6E56;   /* existing primary — actions, focus rings */
  --brand-dark:   #0B5442;
  --ink:          #1E2422;   /* existing text color */
  --ink-muted:    #5C6663;
  --surface:      #FFFFFF;
  --surface-alt:  #F4F6F5;   /* existing secondary background */
  --line:         #DDE3E1;
  --ok:  #157F4B;  --warn: #B4690E;  --danger: #B42318;  --info: #175CD3;
}
```

Principles:
- **Type scale, not ad-hoc sizes.** Four sizes total. Today `####` headings,
  `<small>` HTML, and `st.caption` mix arbitrarily (`app.py:235-237`).
- **One accent color.** Green is for *your* actions. Semantic colors are only for
  status. If everything is green nothing reads as the next step.
- **Spacing scale in multiples of 4px.** The current layout uses arbitrary column
  ratios (`[8,1,1]`, `[7,3]`, `[5,1]`, `[1,1,3]`, `[1,4]`) that produce
  inconsistent rhythm down the page.
- **Density is a feature.** This is a professional tool used daily by an expert,
  not a marketing page. Tighter than a consumer app; generous line-height in
  narratives and claims where reading comprehension matters.
- **Add real identity** (fixes point 15). KLK mark in the header, consistent
  document header on exports. It is a regulatory artifact; it should look
  institutional.
- **Respect `prefers-reduced-motion`** and keep transitions under 150ms.

### 4.10 Micro-copy

- **Never label a button with a word that contradicts its action.** `"Show"`
  currently calls `dismiss()` (`app.py:413`) — the fix is "Dismiss" or, better,
  "Review these →" that actually navigates to them.
- Empty states should teach: "No evidence pending. Run research or add evidence
  manually" with both actions present — not a bare "No records."
- Errors say what to do next, not just what failed. `"Import failed: {err}"`
  (`app.py:466`) should suggest checking the batch file format.
- Write dates in a readable format. `signed_at[:10]` gives `2026-08-11`;
  "11 Aug 2026" reads faster. Keep ISO in exports and the audit trail.

---

## Part 5 — Accessibility & robustness baseline

Not optional for a tool that may be used by others or reviewed externally.

- Every interactive control reachable by keyboard, in a sensible tab order.
- Visible focus ring — do not `outline: none` without a replacement.
- 4.5:1 contrast minimum for text. Check the amber; mid-tone ambers usually fail.
- Icon-only buttons need `aria-label`. Better: avoid icon-only in the primary path
  entirely (fixes point 1).
- Modals: trap focus, close on `Esc`, return focus to the trigger.
- `aria-live="polite"` region for toasts and htmx status updates.
- Forms work without JS where feasible — a normal `<form method="post">` that htmx
  progressively enhances. This is also your fallback if htmx fails to load.
- Test at 200% browser zoom and at 1280px width — likely the real office setup.

---

## Part 6 — Suggested sequencing

1. **Skeleton** — FastAPI app, Jinja base template, one CSS file with tokens,
   scope switcher in header, all four views routed and empty.
2. **Read-only parity** — render every existing screen with real data. No writes.
   Cheap, and immediately shows whether the data layer is fully reachable.
3. **Auth + operator identity** (2.1). Do this *before* any write path exists, so
   no write is ever built against the wrong actor source.
4. **Write paths** — evidence decisions, draft/sign, requirement refinement. Add
   optimistic concurrency (2.4) as you go, not after.
5. **Research runs** — move run state to SQLite (2.2), SSE for status.
6. **Exports as downloads** (2.5) + export history.
7. **Parity checkpoint.** Walk one country end to end in both apps. Compare the
   audit trail row for row. This is the gate between Project A and Project B.
8. **Then redesign** — Part 4, in order: Overview screen, Evidence queue, Section
   page, status system, audit trail, polish.

### Parity test — run before declaring the port done
For Malaysia + one region, in both the old and new app: add manual evidence →
approve one, reject one with a reason → check a rule → override the suggested
rating with a reason → sign → reopen with a reason → re-sign → refine a
requirement → generate a checklist → export all four documents. Then diff the
`audit_log` tables. **Same events, same order, same actor, same reasons.** If they
differ, the port is not done — regardless of how the UI looks.

---

## Part 7 — Things to explicitly not do

- **Do not touch `core/`** during the port beyond the concurrency pragmas (2.3)
  and the `research_runs` table (2.2). It is provider-agnostic by design and
  already carries the append-only guarantees.
- **Do not add a database ORM.** The SQL in `db.py` is explicit, auditable, and
  small. An ORM would obscure exactly the thing that must stay obvious.
- **Do not soften the append-only rules** to make a UI interaction more convenient.
  If a screen wants to edit a signed record, the screen is wrong.
- **Do not port the sidebar.** It is the clearest symptom of the current IA
  problem — resist recreating it because it is familiar.
- **Do not add a JS chart library** before knowing which charts are actually
  wanted. The Overview progress display is CSS.
- **Do not ship multi-user without auth** (2.1). It is a compliance-integrity
  issue, not a feature gap.

---

## Appendix — Line-referenced issue index

| # | Issue | Where today | Fixed by |
|---|---|---|---|
| 1 | Icon-only asymmetric approve/reject | `app.py:200-215` | 4.3 |
| 2 | "Show" button calls `dismiss()` | `app.py:413` | 4.10 |
| 3 | container → expander → popover nesting | `app.py:232-374` | 4.4 |
| 4 | No progress/completion view | — absent — | 4.2 |
| 5 | Emoji-dot status, color-only, overloaded | `app.py:16` | 4.5 |
| 6 | Sidebar doing five jobs | `app.py:36-155` | 4.1 |
| 7 | Free-text dates, unvalidated | `app.py:484-485` | 4.7 |
| 8 | Five ad-hoc reason patterns | 205, 282, 334, 549 | 4.6 |
| 9 | Signature metadata as caption text | `app.py:241-242` | 4.4 |
| 10 | No section navigation or filter | `app.py:510` | 4.2 |
| 11 | Three rating scales, undeclared | `app.py:320-325` | 4.4 |
| 12 | Ungrouped manual-evidence form | `app.py:468-487` | 4.7 |
| 13 | Unbounded stacking run banners | `app.py:394-423` | 4.3 |
| 14 | Audit trail is a raw dataframe | `app.py:684` | 4.8 |
| 15 | No visual identity | `app.py:38` | 4.9 |
| — | **Operator identity from server user** | `app.py:34` | **2.1** |
| — | **Run state lost across workers/restart** | `runmanager.py:15` | **2.2** |
| — | **SQLite locking under concurrency** | `db.py:20-25` | **2.3** |
| — | **No concurrent-sign protection** | `db.py:499` | **2.4** |
| — | **Exports unreachable from browser** | `exporter.py:29` | **2.5** |
