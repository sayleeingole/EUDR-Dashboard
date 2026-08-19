# 06 — Yearly assessment cycle

The risk assessment is repeated per year. The cycle mechanism makes the yearly repetition fast (roll-forward) while keeping years cleanly separated and comparable.

## Cycle lifecycle

```
open cycle ──▶ work (evidence, ratings, requirements, checklists) ──▶ close cycle
   │                                                                     │
   └── roll-forward from previous cycle                                  └── read-only forever
```

- **Open** — one cycle per year (e.g. `2026`). Opening is an audited action. More than one cycle can technically be open during a transition, but the normal state is one.
- **Work** — everything created during the year (evidence, decisions, sign-offs, refinements, checklist versions, exports) is keyed to the cycle.
- **Close** — closing freezes the cycle read-only. Mandatory pre-close check: all in-scope countries either fully signed or explicitly marked "not assessed this cycle" with reason. Closing is audited; reopening requires an audited reason.

## Roll-forward (what makes year 2 fast)

Opening cycle N+1 offers roll-forward per country/region:

1. **Sections** are pre-filled with cycle N's signed rating and narrative, in status **`to re-verify`** — visibly distinct from signed. Nothing is auto-signed.
2. **Evidence** from cycle N is listed as *carried forward — re-confirm or supersede*. Re-confirming (audited, one click per record or per batch) marks it valid for the new cycle; time-sensitive evidence past its refresh horizon (see below) cannot be re-confirmed and must be refreshed by a new research run/fetch.
3. **Legal requirements** carry forward as *relevant (unverified for cycle N+1)*; a legal-update research run checks for amendments, new instruments, and repeals; the operator re-confirms or revises refinements.
4. **Checklists** do not carry forward — they are regenerated from the new cycle's signed state.

### Refresh horizons (defaults, editable in Admin)
| Data type | Must be refreshed |
|---|---|
| Annual datasets (GFW loss year, TI CPI, trade statistics) | every cycle |
| Listings and measures (WRO, TVPRA, sanctions, benchmarking classification) | every cycle (cheap to check) |
| Grievances / substantiated concerns | every cycle |
| Structural facts (legal instruments, SC structure, census-based figures) | re-confirm; refresh when a new edition exists or every 3 cycles |

A section cannot be re-signed in the new cycle while any of its underlying evidence is expired-unrefreshed.

## Year-over-year comparison

A comparison view (and xlsx/docx delta export) per country/region shows, per section:
- rating in cycle N vs N+1, with the reasons recorded at sign-off;
- evidence added, superseded, expired;
- legal requirements added/removed/rescoped;
- checklist items added/removed and why.

The delta report is the standing answer to an auditor's "what changed since last year and why".

## Mid-cycle events

Significant events (a new WRO, a major grievance, a benchmarking reclassification) do not wait for the next cycle: new evidence enters the open cycle's queue at any time, the affected section is flagged, and the operator may re-sign a new version and regenerate the checklist mid-cycle. The version history shows intra-cycle updates.
