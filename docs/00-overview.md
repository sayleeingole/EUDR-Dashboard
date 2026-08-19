# 00 — System overview

**System:** EUDR Palm Risk Assessment Dashboard
**Owner:** Sustainability, KLK Emmerich GmbH
**Scope:** Country risk assessment (EUDR Art. 10(2)(a)–(n)), national legal requirements mapping (EUDR Art. 2(40)), and generation of the Article 9 supplier documentation checklist — for palm-based raw materials (PKO, fatty alcohols, fatty acids) only.
**Explicitly out of scope:** supplier document tracking, supplier master data, DDS submission, public publication.

## Purpose

The dashboard compresses the country risk assessment from days of manual research to hours, while making the process **audit-proof**: every data point is source-attributed, human-approved, timestamped, and never silently changed. The output of the process is:

1. A signed, versioned **country risk assessment report** per producing country (and sub-national region where governance differs, e.g. Sabah / Sarawak / Peninsular Malaysia).
2. A **legal requirements register** per country, structured by the EUDR Art. 2(40) areas of law.
3. An **Article 9 documentation checklist** per country/region — the documents KLK requests from suppliers — derived from (1) and (2).

## The three sectors

```
┌────────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
│ 1 · Risk assessment    │   │ 2 · Legal requirements │   │ 3 · Art. 9 checklist   │
│ Art. 10(2)(a)–(n)      │   │ Art. 2(40) areas       │   │                        │
│ 10 sections per        │   │ instruments →          │   │ legality BASELINE      │
│ country/region,        │   │ candidate requirements │──▶│ (from sector 2)        │
│ each: evidence →       │──▶│ → relevance refinement │   │ + risk-driven ADD-ONS  │
│ suggested rating →     │   │ → verification docs    │   │ (from sector 1)        │
│ human sign-off         │   │                        │   │ merged, deduplicated,  │
│                        │   │                        │   │ each item justified    │
└────────────────────────┘   └────────────────────────┘   └────────────────────────┘
```

- **Sector 1 — Risk assessment.** Ten sections per country/region, each mapped to its Article 10(2) letter(s). Evidence flows in (in-app research runs, API pulls, manual entry), waits in a review queue, and only counts once approved. The system *suggests* a risk rating from approved evidence via transparent rules; the human confirms or overrides with a reason and signs a narrative conclusion. See `01-risk-assessment-process.md`.
- **Sector 2 — Legal requirements.** Per country: legal instruments (laws, implementing texts, jurisprudence, treaties) are mapped to candidate requirements under the eight Art. 2(40) areas of law; the human refines each to relevant / not relevant; each relevant requirement is linked to the supplier documents that verify compliance. See `04-legal-mapping.md`.
- **Sector 3 — Article 9 checklist.** Generated, never hand-assembled: the **legality baseline** (bare-minimum documents proving Art. 9(1)(h) legality, from sector 2) plus **risk add-ons** (documents responding to specific identified risks, from sector 1), deduplicated, with each item annotated with *why* it is requested. See `05-checklist-generation.md`.

Supporting workflows: the **evidence queue** (`03-evidence-review.md`), **research runs** (`02-research-runs.md`), the **yearly cycle** (`06-yearly-cycle.md`), and the **audit trail** (`07-audit-and-qa.md`).

## Data flow

```
 in-app research run          API fetchers            manual entry
 (Claude, per section /       (GFW, TI CPI, ...)      (structured form)
  per legal area)                    │                       │
        │                            │                       │
        └──────────────┬─────────────┴───────────────────────┘
                       ▼
              EVIDENCE QUEUE  (status: pending)
                       │
             human review: approve / reject (+reason)      ← every decision logged
                       ▼
              APPROVED EVIDENCE  (immutable; corrections = superseding record)
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
  RISK SECTIONS                LEGAL REQUIREMENTS
  suggested rating             candidate → relevant/not relevant (+reason)
  → confirm/override           → verification documents
  → narrative sign-off                │
        │                             │
        └──────────────┬──────────────┘
                       ▼
             ART. 9 CHECKLIST  (baseline + add-ons, each item justified)
                       ▼
             EXPORTS  (docx / xlsx / pdf, named systematically, logged)
```

## Core principles

1. **Human in the loop, always.** No evidence counts, no rating stands, no requirement applies, and no checklist item appears without an explicit human decision. The system suggests; the human decides.
2. **Append-only.** Evidence, decisions, sign-offs, and rule versions are never edited or deleted — corrections create superseding records. The full history is reconstructable at any time.
3. **Source-attributed.** Every claim carries its source, URL, and retrieval date. Sources come from a managed whitelist; unlisted sources are blocked until the source itself is approved.
4. **Justified outputs.** Every checklist item states which risk conclusion and/or legal requirement caused it. A competent authority can trace every request backwards to evidence.
5. **Yearly cadence.** Assessments are conducted per cycle (year). Closed cycles are read-only; changes between years are tracked and explainable.

## Technical summary

- **App:** Python + Streamlit, running locally (`streamlit run app.py`), browser UI at `localhost`. Designed to be intranet-hostable later without redesign.
- **Database:** SQLite — a single local file `data/eudr.sqlite`. No server, no external service. Append-only conventions enforced in the access layer.
- **Research engine:** Claude Code invoked headlessly by the app (`claude -p`), using the operator's existing login; output is schema-validated JSON that enters the queue as *pending*.
- **Nothing leaves the machine** except outbound reads (API/data fetches, research searches). No company data is uploaded anywhere.

## Document map

| File | Process covered |
|---|---|
| `01-risk-assessment-process.md` | The 10 risk sections, rating suggestion, confirm/override, sign-off |
| `02-research-runs.md` | In-app research runs, prompt templates, output schema, source policy |
| `03-evidence-review.md` | Queue workflow, approve/reject, superseding, unlisted sources |
| `04-legal-mapping.md` | Art. 2(40) areas, instruments → requirements → verification documents |
| `05-checklist-generation.md` | Baseline + add-on merge, deduplication, justification |
| `06-yearly-cycle.md` | Opening/closing cycles, roll-forward, year-over-year deltas |
| `07-audit-and-qa.md` | Audit trail, append-only guarantees, export logging, QA checks |
