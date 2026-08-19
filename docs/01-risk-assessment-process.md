# 01 — Risk assessment process (Sector 1)

Covers the country risk assessment under EUDR Article 10(2), conducted per producing country and — where governance or risk profiles differ materially — per sub-national region (e.g. Malaysia → Sabah, Sarawak, Peninsular).

## The ten sections

Each country/region assessment consists of ten sections, each tied to its Article 10(2) letter(s). Example sources listed are the seeded whitelist starting points; the whitelist is editable (see `02-research-runs.md`).

**The "What is assessed" column is directional, not limiting.** It states the minimum scope each section must cover; research runs must additionally surface any other credible, relevant information found in that thematic space (new listings, new studies, regulatory changes, emerging grievances, etc.). A section's evidence base is defined by its Article 10(2) letters and theme — never by the examples in this table.

| # | Section | EUDR basis | What is assessed (minimum scope — see note above) | Example whitelisted sources |
|---|---|---|---|---|
| 1 | Country risk classification | Art. 10(2)(a); Art. 29 benchmarking | Commission classification (low / standard / high) and the due diligence level it triggers | EUR-Lex: Reg. (EU) 2023/1115; Impl. Reg. (EU) 2025/1093; Reg. (EU) 2025/2650 |
| 2 | Presence of forests | Art. 10(2)(b) | Forest cover, primary forest, peatland presence in sourcing areas | FAO FRA 2020; EU JRC 2020 Global Forest Cover; GFW/UMD; MPOB (peat) |
| 3 | Indigenous peoples & customary tenure | Art. 10(2)(c), (d), (e) | Presence of indigenous peoples in production areas; FPIC legal baseline; consultation in good faith; documented claims/unrest; active grievances | National census bodies; IWGIA; national human rights commissions (e.g. SUHAKAM); Mongabay; country-specific watchdogs |
| 4 | Prevalence of deforestation | Art. 10(2)(f), (k) | Tree cover loss trend, state of primary forest, loss in protected areas, agriculture-driven loss, post-2020 trend | GFW/UMD (Hansen); WRI Global Forest Review; EU Forest Observatory; EFI; palmoil.io |
| 5 | Governance concerns | Art. 10(2)(g), (h) | Corruption (TI CPI), sector regulation quality, EU/UN sanctions, civic space (CIVICUS), transparency indices, tracked environmental crimes | Transparency International; EU/UN sanctions lists; CIVICUS Monitor; Global Witness; EIA; Chain Reaction Research; RSPO Complaints Panel |
| 6 | Supply chain complexity | Art. 10(2)(i) | Palm supply chain structure: planted area, mills, refineries, kernel crushers, biodiesel plants; smallholder share; independent vs linked plantations; traceability implications | National commodity boards (e.g. MPOB); government statistics |
| 7 | Risk of mixing | Art. 10(2)(j) | Points where unknown-origin material can enter: dealers/collection points, mill weighbridges, multi-origin refinery blending, bulk port tanks, cross-border flows; certification model limits (MB vs SG/IP) | National trade statistics; Mighty Earth Rapid Response; investigative reporting; conclusions drawn from sections 4–6 data |
| 8 | Human rights | Art. 10(2)(l); Art. 2(40) | Labour and human rights law enforcement: forced/child labour listings, import control measures (e.g. CBP WROs), migrant workforce structure, recruitment practices, national action plans | US DOL/ILAB TVPRA; US CBP; ILO; Amnesty International; IOM; Human Rights Watch; UNICEF |
| 9 | Substantiated concerns | Art. 10(2)(m) | First-party grievances and coalition submissions alleging non-compliance for palm products from the country/region | NGO coalition submissions; Mongabay; Mighty Earth; palmoil.io grievance data; RSPO complaints |
| 10 | Certification & third-party schemes | Art. 10(2)(n) | Coverage and *content* of mandatory and voluntary schemes (e.g. MSPO, RSPO; MB/SG/IP models) against Art. 9 information requirements. A certification is supportive evidence, never a green lane | Scheme documentation; national regulators; RSPO |

**Section interdependency rule:** Sections 7 (mixing) and 9 (substantiated concerns) are synthesis sections — their conclusions must reference quantitative findings from sections 4–6 and grievance data. Scientific derivation from collected data is permitted; unsupported assumption is not. The narrative must distinguish "evidence shows" from "we infer".

## Section workflow (per country/region × cycle)

```
evidence approved (see 03) ──▶ suggested rating + rule trace ──▶ human decision ──▶ signed section
```

### 1. Evidence basis
Only **approved** evidence records for this section/country/region/cycle are visible in the section workspace. Pending or rejected records never influence a rating.

### 2. Suggested rating (system)
The rules engine evaluates the approved evidence against the **rating-suggestion rules** (editable in Admin; versioned). Each rule is of the form:

> IF *evidence condition* THEN *suggested rating ≥ X*, with rationale text.

Seed examples:
- Active CBP Withhold Release Order or TVPRA listing for palm → section 8 suggested **high**.
- Post-2020 tree cover loss trend rising in sourcing region → section 4 suggested **high**.
- Substantial crude imports from a higher-risk neighbouring producer + documented cross-border leakage → section 7 suggested **high**.
- Mandatory national certification with plot-level requirements in force → section 10 suggested **supportive** (note: ratings for section 10 use `supportive / neutral / weak` instead of low/medium/high).

The suggestion is displayed **with its rule trace**: which rules fired, on which evidence records. If no rule fires, the suggestion is "insufficient basis — manual rating required".

### 3. Human decision (binding)
The operator either:
- **Confirms** the suggested rating, or
- **Overrides** it — selecting a different rating and entering a mandatory override reason.

Rating scale: **low / medium / high** (section 1 uses the official benchmarking category; section 10 uses supportive / neutral / weak). The confirmed rating — not the suggestion — is what the dashboard displays and what drives checklist generation.

### 4. Narrative conclusion
Each section requires a **narrative conclusion**: analytical prose in the established house style (evidence-dense, source-attributed, e.g. the Malaysia mixing and human rights examples), ending with a source list. Research runs pre-fill a draft narrative; the operator edits it. The narrative must be consistent with the approved evidence; it may include reasoned inference but must flag it as such.

### 5. Sign-off
Signing a section freezes rating + narrative + the evidence set it was based on as a **version** (v1, v2, ...). Re-opening after sign-off creates the next version; prior versions remain readable. The audit log records signer, timestamp, suggestion, decision, and override reason.

A country/region assessment is **complete** for a cycle when all ten sections are signed. Only then can the final report be exported as "complete" (partial drafts export with a DRAFT watermark).

## Sub-national drill-down

A region inherits its country's sections. A section may be assessed at country level only (regions inherit) or per region where risk differs (e.g. deforestation and indigenous-peoples sections for Sarawak vs Peninsular Malaysia). The report shows region-level conclusions where they exist, country-level otherwise. The choice of assessment level per section is itself recorded and justified.

## Risk display

- Sidebar dot per country/region: grey = not assessed this cycle; green/amber/red = highest confirmed rating among signed sections; ring = sections pending.
- Section cards: confirmed rating, evidence counts (approved / pending), sign-off status and version.
