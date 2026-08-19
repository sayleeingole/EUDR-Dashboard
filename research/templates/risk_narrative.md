# Risk research run — narrative drafting pass (v1)

You are writing the analytical narrative for an EUDR country risk assessment for
palm-based raw materials, on behalf of a sustainability expert at KLK Emmerich GmbH.
Base the narrative ONLY on the evidence given below — do not search the web, do not
invent facts, and do not cite anything not present in the evidence list.

## Scope
- Country: {country}
- Region: {region}
- Assessment cycle (year): {cycle}
- Sections: {sections}

## Evidence gathered this run
{evidence_block}

## Already recorded (background context — do not restate as new findings)
{existing_block}

## Instructions
For each section that has evidence above, write ONE narrative draft: analytical prose
in scientific style with inline source references, evidence-dense, in the style of a
formal risk assessment report. End it with a source list drawn only from the evidence
given. Mark any inference explicitly as inference. 150-300 words per section. If a
section has no evidence above, omit it — do not fabricate a narrative for it.

## Output format
Respond with ONLY a single JSON object (no markdown fences, no commentary before or
after) conforming exactly to this structure:

{schema_excerpt}

Use section codes exactly as given in the scope (e.g. "S4"). Set meta.run_type to
"risk", meta.country to "{country}", meta.region to {region_json}, meta.cycle to
{cycle}, meta.template_version to "risk-narrative-v1".
