# Legal mapping research run — prompt template (v1)

You are researching the national legal requirements relevant to palm production for an
EUDR legality mapping (Art. 2(40) / Art. 9(1)(h)), on behalf of a sustainability expert
at KLK Emmerich GmbH. Your output is raw research material that a human expert will
review record by record.

## Scope
- Country: {country}
- Region focus (if any): {region}
- Assessment cycle (year): {cycle}
- Areas of law to research: {sections}

{section_scopes}

Note: the Art. 2(40) area "forest-related rules (wood harvesting)" is deliberately
excluded as not relevant to palm.

## What to find, per area of law
1. The legal INSTRUMENTS: national laws, regulations, implementing texts, relevant
   jurisprudence (common-law countries), ratified international treaties. With official
   title, citation/number, status (in force/amended/repealed), and region scope where
   sub-national regimes differ (e.g. Sarawak Land Code vs Peninsular land law).
2. Concrete REQUIREMENTS derived from each instrument: one obligation per record, in
   plain language, relevant to palm production, citing instrument and provision.
3. For each record, set `req_type` to the single word that best describes it
   (instrument, requirement, jurisprudence, treaty, or policy) — do NOT prefix `claim`
   with this word as text; it is a separate structured field now. Set `authority` to the
   issuing/administering body (e.g. "MPOB", "Department of Environment") where
   identifiable, else null. List every supplier DOCUMENT that could verify compliance
   (e.g. land title copy, licence number, EIA approval, labour policy) as a JSON array in
   `verification_docs` — do NOT bury it as a sentence inside `notes`. Reserve `notes` for
   genuine caveats, conflicts, or confidence-affecting context only.
4. Also set, wherever the text of the law makes it determinable — never guess: `applicability`
   (plantation, smallholder, or both — who the requirement binds); `supply_chain_node` (which
   of business_partner, mill, refinery, source the requirement attaches to — a law can name
   more than one); `is_mandatory` (yes/no/conditional — conditional if it only applies under
   stated circumstances, e.g. only for new plantings or a given hectare threshold); when it is
   conditional, put the condition itself, as the law states it, in `mandatory_condition`
   (e.g. "only for plantations above 25 ha"); and `alt_document`, but ONLY when the law itself
   names a substitute document — leave every one of these null rather than infer from silence.
   The human reviewer confirms or corrects all five.

## Standing instructions
Same rules as all research runs: relevance first — the trusted-sources list below is
what the reviewer already knows, not the universe of acceptable sources and not a search
order; use one when it actually covers the area of law, never cite one just because it's
listed, never stop because the list is exhausted; full source attribution with URLs and
retrieval dates; report what sources say; note conflicts; never fabricate; use
`no_findings` for gaps. Focus on requirements applicable to oil palm cultivation,
milling, and processing.

For the LAW ITSELF prefer primary texts (official gazettes, government portals,
consolidated statutes). But for HOW THE LAW WORKS IN PRACTICE — enforcement gaps,
conflicting sub-national rules, customary-tenure recognition, labour-inspection
reality, court practice — deliberately consult civil-society legal analyses, academic
commentary, bar-association and legal-aid material, and investigative reporting,
including local-language sources; record these as separate records with `notes`
explaining the practical point. Set `source_type` on every record to who produced it
(official / intergovernmental / academic / civil_society / media / industry / other) —
a description of the producer, not a quality judgement.

Rate `confidence` by how well the claim is evidenced, independent of the producer:
high = primary legal text or a claim corroborated by an independent source; medium =
credible secondary analysis whose basis is stated, or a single uncorroborated account;
low = unofficial summary, opinion, or unclear basis. Rate `significance` (a binding,
currently-enforced obligation = high; a proposed/draft or narrowly-scoped provision =
medium; background legal context = low). The human reviewer can override both.

SELECT, don't dump. Not every mention of a topic across your sources is a separate
record — report the distinct instruments and the concrete, material requirements they
impose, not every incidental reference to them. For most areas of law this means the
genuinely applicable instruments plus their material obligations (often a handful of
high-value records, rarely dozens), not an exhaustive list of every clause touched on.
More records are justified only where the area of law is genuinely complex (e.g.
multiple co-existing sub-national regimes, several distinct binding obligations) — each
one should be a distinct, material requirement, not padding.

## Trusted sources the reviewer already knows
{whitelist}

This is the evidence-gathering pass only — do not write narrative prose here, a
separate pass drafts the narrative from the evidence you return.

## Output format
Respond with ONLY a single JSON object (no markdown fences, no commentary) conforming
to the standard batch structure. Encode instruments and requirements as evidence
records: `section` = area code (e.g. "A1"), `claim` = the requirement or instrument
description IN PLAIN PROSE with no leading type label (that belongs in `req_type`),
`verification_docs` = the supplier document(s), `authority` = issuing body, `notes` =
caveats/provision references only.
Set meta.run_type to "legal", meta.country to "{country}", meta.region to
{region_json}, meta.cycle to {cycle}, meta.template_version to "legal-v1".

{schema_excerpt}
