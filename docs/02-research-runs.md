# 02 — Research runs

How data gets researched and enters the system. Three intake channels exist — **in-app research runs** (primary), **API fetchers**, and **manual entry** — and all three converge on the same evidence queue (`03-evidence-review.md`). No channel bypasses human review.

## In-app research runs (primary channel)

### Trigger
From a country/region page the operator clicks **Run research** and selects scope:
- a single risk section (e.g. "10(2)(f) deforestation — Colombia"),
- several sections, or a full-country sweep,
- or a legal-mapping run for one or more Art. 2(40) areas of law (see `04-legal-mapping.md`).

No leaving the app; no copy-pasting between tools.

### What happens technically
1. The app assembles a prompt from the **prompt template** for that section/area (stored in `research/templates/`, editable), inserting: country/region, cycle year, the section's whitelisted sources, the required output schema, and the instruction set below.
2. The app invokes Claude Code headlessly (`claude -p`) as a background process, using the operator's existing Claude Code login. Progress is displayed in the app.
3. Claude searches and reads sources, then writes a single batch file `research/<country>_<scope>_<YYYY-MM-DD>_<n>.json` conforming to `research/schema.json`.
4. The app validates the file against the schema (malformed batches are rejected whole, with the error shown) and imports every record as **pending** into the evidence queue. The import itself is an audited event.

### Standing instructions embedded in every research prompt
- Use **whitelisted sources first**. A claim from a non-whitelisted source is permitted only when no whitelisted source covers it, and is flagged (see source policy below).
- Every claim must carry: source name, publisher, URL, publication date (if stated), and retrieval date.
- Report **what the source says**, not conclusions. Inference belongs in the narrative draft, marked as inference.
- Prefer primary sources (the regulation text, the census, the trade statistics) over reporting about them.
- Record data vintage explicitly (e.g. "FRA 2020 figure, reference year 2020").
- If sources conflict, include both records and note the conflict — do not resolve it silently.
- Never fabricate a source, URL, or figure. If nothing credible is found for a sub-question, return an explicit `no_finding` entry saying what was searched.

### Batch content (`research/schema.json`)
Each batch contains:

```json
{
  "meta": {
    "country": "...", "region": "... | null", "cycle": 2026,
    "scope": ["10(2)(f)"], "run_type": "risk | legal",
    "generated_at": "...", "template_version": "..."
  },
  "evidence": [
    {
      "section": "10(2)(f)",
      "claim": "one factual statement",
      "value": "quantitative value if applicable",
      "source_name": "...", "publisher": "...", "url": "...",
      "published": "... | unknown", "retrieved": "YYYY-MM-DD",
      "source_whitelisted": true,
      "notes": "conflicts, caveats, vintage"
    }
  ],
  "narrative_drafts": [
    { "section": "10(2)(f)", "text": "analytical prose in house style ...", "sources": ["..."] }
  ],
  "no_findings": [
    { "section": "...", "searched_for": "...", "where_searched": ["..."] }
  ]
}
```

- **`evidence`** records feed the queue and, once approved, the rating rules.
- **`narrative_drafts`** — one per section: a well-written, scientific-style paragraph with inline references (house style: the Malaysia mixing / human rights examples). It pre-fills the section's conclusion editor (see `01`, step 4). The operator edits and signs it; **only the signed narrative** appears in the exported risk assessment report, which therefore reads as a fully referenced report while containing only human-approved text. A draft is never auto-signed.
- **`no_findings`** are shown in the section workspace so absence of data is visible and auditable, not silent.

## Source whitelist policy

The `sources` register lists approved sources per section/area: name, publisher, URL pattern, sections it applies to, status (`active` / `retired`), who added it and when.

- Seeded from the operator's established source lists (FAO FRA, GFW/UMD, EU JRC, TI, CIVICUS, ILO, US DOL/ILAB, US CBP, IWGIA, SUHAKAM, Amnesty, IOM, HRW, UNICEF, Mongabay, Mighty Earth, Global Witness, EIA, Chain Reaction Research, RSPO, MPOB, palmoil.io, EUR-Lex, national statistics offices...).
- Editable only in Admin; every change (add / retire) is an audited event with reason.
- An evidence record citing an unlisted source imports as `pending + unlisted-source` and **cannot be approved** until the operator either approves the source into the whitelist (audited) or rejects the record. This is deliberate two-step control: the source is judged once; its records are judged individually.

## API fetchers (structured data channel)

For sources with machine-readable data, fetcher scripts pull directly:
- **Global Forest Watch API** — tree cover loss by year/region, loss in protected areas, primary forest loss.
- **Transparency International CPI** — annual dataset.
- Further fetchers follow the same pattern as they become worthwhile.

Fetcher output becomes ordinary evidence records (`origin = api`) with the dataset citation and query parameters recorded, entering the queue as **pending** like everything else. A fetched number is not truth; it is a claim awaiting review.

## Manual entry

A structured form (claim, value, source from whitelist or new-source request, URL, dates, section, notes) for anything the operator finds herself. Same queue, same rules (`origin = manual`).

## Fallback: chat-based research

Deep-dive investigations can still be run conversationally in Claude Code chat; the deliverable is the **same JSON batch format** dropped into `research/`, which the app detects and offers for import. Identical schema, identical review path.
