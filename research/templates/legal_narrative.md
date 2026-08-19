# Legal mapping research run — narrative drafting pass (v1)

You are writing the analytical narrative summarising the national legal landscape for
an EUDR legality mapping (Art. 2(40) / Art. 9(1)(h)), on behalf of a sustainability
expert at KLK Emmerich GmbH. Base the narrative ONLY on the evidence given below — do
not search the web, do not invent facts, and do not cite anything not present in the
evidence list.

## Scope
- Country: {country}
- Region focus (if any): {region}
- Assessment cycle (year): {cycle}
- Areas of law: {sections}

## Evidence gathered this run
{evidence_block}

## Already recorded (background context — do not restate as new findings)
{existing_block}

## Instructions
For each area of law that has evidence above, write ONE narrative draft summarising
the legal landscape (100-200 words, with sources drawn only from the evidence given).
Mark any inference explicitly as inference. If an area has no evidence above, omit it.

## Output format
Respond with ONLY a single JSON object (no markdown fences, no commentary before or
after) conforming exactly to this structure:

{schema_excerpt}

Use area codes exactly as given in the scope (e.g. "A1"). Set meta.run_type to
"legal", meta.country to "{country}", meta.region to {region_json}, meta.cycle to
{cycle}, meta.template_version to "legal-narrative-v1".
