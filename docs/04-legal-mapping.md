# 04 — Legal requirements mapping (Sector 2)

Maps the national legal requirements relevant to palm production per country, following the EFI Legality Due Diligence Navigator methodology as process reference (legal mapping → compliance framework), adapted to KLK's needs. EFI/Preferred by Nature published tools are **not imported as data**; they may be consulted manually as reference material only.

## Legal basis

EUDR Art. 3(b) requires products to be **produced in accordance with the relevant legislation of the country of production**. Art. 2(40) defines that legislation as the laws applicable to the production area concerning the legal status of the area and, in particular:

| Code | Area of law |
|---|---|
| A1 | Land use rights |
| A2 | Environmental protection |
| A3 | Third parties' rights |
| A4 | Labour rights |
| A5 | Human rights protected under international law |
| A6 | The principle of free, prior and informed consent (FPIC), incl. as set out in the UN Declaration on the Rights of Indigenous Peoples |
| A7 | Tax, anti-corruption, trade and customs regulations |

**Deliberate exclusion:** the Art. 2(40) area "forest-related rules, including forest management and biodiversity, where directly related to wood harvesting" is excluded from this mapping as it applies to wood harvesting and is not relevant to palm production. The exclusion is recorded here so the scope decision is documented.

Art. 9(1)(h) requires the operator to hold **adequately conclusive and verifiable information that production complied with that legislation, including documents on the legal right to use the area**. The output of this sector is therefore the **legality baseline checklist**: which documents demonstrate compliance, per country.

## Process

```
instruments ──▶ candidate requirements ──▶ relevance refinement ──▶ verification documents
 (register)        (per area of law)        (human decision)          (→ legality baseline)
```

### 1. Instruments register
Per country, a register of legal instruments: national laws and regulations, implementing texts, jurisprudence (in common-law countries), and ratified international treaties. Each entry: official title, citation/number, type, area(s) of law, status (in force / amended / repealed), region applicability (critical where regions have separate regimes — e.g. Sarawak Land Code vs Peninsular land law), source URL, retrieval date.

Populated by **legal-mapping research runs** (see `02`) and manual entry; entries pass through the evidence queue like all data.

### 2. Candidate requirements
From each instrument, concrete obligations relevant to palm production are extracted as **candidate requirements** — one obligation per record, in plain language, citing instrument and provision. Examples of the intended shape:
- (A1) "Producer holds a valid land title, lease, or licence for the production area" — [land law citation].
- (A4) "Employer does not retain workers' passports" — [labour law citation].
- (A2) "Plantation operation holds the required environmental approval (e.g. EIA) where thresholds are met" — [environmental law citation].
- (A7) "Producing entity is registered and licensed with the national palm authority" — [sector regulation citation].

### 3. Relevance refinement (human decision)
Each candidate is decided by the operator: **relevant / not relevant** (+ mandatory reason, e.g. "does not apply to palm", "superseded", "applies only to region X — scoped accordingly"), with region scoping where applicable. Decisions are audited and versioned; refinement can be revisited each cycle. Only *relevant* requirements proceed.

### 4. Verification documents
Each relevant requirement is linked to the **document(s) or evidence a supplier can provide to verify compliance**: land title/lease copy, licence number verifiable in a public register, EIA approval, labour policy + payroll sample, tax registration, etc. One requirement may map to several acceptable documents; one document may verify several requirements. These mappings are the raw material of the legality baseline checklist (`05-checklist-generation.md`).

## Region handling

Where legal regimes differ sub-nationally (Sabah / Sarawak / Peninsular Malaysia being the canonical case), instruments and requirements carry region scope, and the legality baseline is generated per region. Requirements without region scope apply country-wide.

## Interaction with the risk assessment

Sector 2 defines **what must be complied with and how compliance is evidenced** (the baseline). Sector 1 assesses **how likely non-compliance is** (the risk). They meet in two places:
- Risk section 8 (human rights) and section 3 (indigenous peoples/FPIC) draw on the same legal instruments — a weak FPIC legal baseline found here is evidence there.
- High risk in a section can escalate verification intensity for related legal areas in the checklist (e.g. high section-8 risk → labour documents move from declaration-level to proof-level). See `05`.
