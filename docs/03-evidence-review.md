# 03 — Evidence review (the queue)

The single control point through which **all** data passes before it can influence any rating, requirement, or checklist. This is the primary human-in-the-loop mechanism.

## States

```
                     ┌────────── superseded (by a newer approved record)
                     │
 pending ──▶ approved ──▶ (feeds ratings / requirements)
    │
    ├──▶ rejected (+ mandatory reason)
    │
    └──▶ pending + unlisted-source  ──(source approved)──▶ pending ──▶ ...
                                     └─(record rejected)─▶ rejected
```

- **pending** — imported or entered, awaiting review. Visible, but has zero effect on anything.
- **approved** — counts as evidence. Immutable from this point.
- **rejected** — kept forever with the reviewer's reason; never deleted; never counts.
- **superseded** — still readable, no longer current; points to its replacement.
- **unlisted-source** — blocked until the source itself is decided (see `02`, source policy).

## Review workflow

The queue lists pending records filterable by country/region, section, origin (research / api / manual), and flag. For each record the reviewer sees: claim, value, source + URL (clickable), publication and retrieval dates, section, origin, batch it arrived in, and any notes (conflicts, vintage caveats).

Actions:
- **Approve** — record becomes evidence. Logged: reviewer, timestamp.
- **Reject** — mandatory reason (e.g. "duplicate", "source misread", "outdated vintage", "not relevant to region"). Logged.
- **Approve source** (only on unlisted-source records) — adds the source to the whitelist with a reason, then the record returns to normal pending state for its own decision. Two separate logged decisions by design.

Bulk approve is available **only** within one batch × one section at a time, and never for flagged records — deliberate friction against rubber-stamping.

## Immutability and corrections (supersede, never edit)

Approved records are frozen — the UI offers no edit. When a figure is revised (e.g. GFW restates a year's loss) or an error is found:

1. A **new record** is created with the corrected content, referencing `supersedes_id` of the old one.
2. On approval of the new record, the old one automatically becomes `superseded`.
3. Any signed section that relied on the superseded record is flagged **evidence changed — review advised** (it is not auto-unsigned; the operator decides whether the change is material and re-signs a new version if so — see `01`, step 5).

This guarantees the evidence set behind any past sign-off can be reconstructed exactly as it was.

## Duplicates and conflicts

- The importer flags likely duplicates (same section + same source + similar claim) as `possible-duplicate`; the reviewer resolves by rejecting one with reason "duplicate".
- Conflicting records (two sources, different figures) are both kept if both are credible; the section narrative must address the conflict. The rating rules use the more conservative (higher-risk) reading unless the narrative justifies otherwise.

## What reviewers check before approving

1. **Source integrity** — the URL opens and actually contains the claim (spot-check at minimum; mandatory for records feeding a `high` rating suggestion).
2. **Vintage** — the data year is stated and appropriate for the cycle.
3. **Scope match** — the claim is about the right country/region and about palm (or clearly applicable context).
4. **Claim fidelity** — the claim states what the source says, without embedded conclusions.

## Timeliness

Queue counts are always visible per country (badge on the tab). A research batch left unreviewed does nothing — there is no time-based auto-approval, ever.
