-- EUDR Palm Risk Assessment Dashboard — SQLite schema
-- Append-only conventions: evidence, evidence_decisions, assessments (versions),
-- rules (versions), audit_log are never UPDATEd or DELETEd by application code,
-- except for narrow status transitions noted below.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assessment_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    opened_by TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_by TEXT,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS countries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    iso3 TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS regions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id INTEGER NOT NULL REFERENCES countries(id),
    name TEXT NOT NULL,
    UNIQUE (country_id, name)
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,          -- e.g. 'S1'..'S10'
    article_refs TEXT NOT NULL,         -- e.g. '10(2)(a)'
    title TEXT NOT NULL,
    min_scope TEXT NOT NULL,            -- directional minimum scope (not limiting)
    rating_scale TEXT NOT NULL DEFAULT 'risk'  -- 'risk' | 'benchmark' | 'support'
);

CREATE TABLE IF NOT EXISTS legal_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,          -- 'A1'..'A7'
    title TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    publisher TEXT,
    url_pattern TEXT,
    applies_to TEXT NOT NULL DEFAULT 'all',   -- comma list of section codes / area codes / 'all'
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
    added_by TEXT NOT NULL,
    added_at TEXT NOT NULL,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL REFERENCES assessment_cycles(id),
    country_id INTEGER NOT NULL REFERENCES countries(id),
    region_id INTEGER REFERENCES regions(id),
    section_code TEXT NOT NULL,               -- section code or legal area code
    claim TEXT NOT NULL,
    value TEXT,
    source_id INTEGER REFERENCES sources(id),
    source_name TEXT NOT NULL,                -- as cited (also when unlisted)
    publisher TEXT,                           -- outlet/publisher name, as cited (e.g. 'Mongabay')
    url TEXT,
    published TEXT,
    retrieved TEXT NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('claude_research','api','manual')),
    batch_file TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','rejected','superseded')),
    flag TEXT,                                -- 'unlisted-source' | 'possible-duplicate' | NULL
    confidence TEXT,                          -- 'low' | 'medium' | 'high' | NULL — source reliability
    significance TEXT,                        -- 'low' | 'medium' | 'high' | NULL — materiality to the section
    req_type TEXT,                            -- legal areas only: instrument|requirement|jurisprudence|treaty|policy
    authority TEXT,                           -- legal areas only: issuing/administering body
    verification_docs TEXT,                   -- legal areas only: JSON list of document names
    applicability TEXT                        -- legal areas only: plantation|smallholder|both
        CHECK (applicability IS NULL OR applicability IN ('plantation','smallholder','both')),
    supply_chain_node TEXT,                   -- legal areas only: comma-list of business_partner|mill|refinery|source
    is_mandatory TEXT                         -- legal areas only: yes|no|conditional
        CHECK (is_mandatory IS NULL OR is_mandatory IN ('yes','no','conditional')),
    alt_document TEXT,                        -- legal areas only: free-text alternative document description
    mandatory_condition TEXT,                 -- legal areas only: when is_mandatory='conditional', the stated condition (e.g. hectare threshold)
    source_type TEXT,                         -- official|intergovernmental|academic|civil_society|media|industry|other (see core/source_type.py)
    supersedes_id INTEGER REFERENCES evidence(id),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id INTEGER NOT NULL REFERENCES evidence(id),
    decision TEXT NOT NULL CHECK (decision IN ('approved','rejected','reconfirmed')),
    reason TEXT,
    decided_by TEXT NOT NULL,
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL REFERENCES assessment_cycles(id),
    country_id INTEGER NOT NULL REFERENCES countries(id),
    region_id INTEGER REFERENCES regions(id),
    section_code TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    suggested_rating TEXT,
    rule_trace TEXT,
    confirmed_rating TEXT,
    override_reason TEXT,
    narrative TEXT,
    evidence_ids TEXT,                        -- JSON list frozen at sign-off
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','signed','to_reverify')),
    signed_by TEXT,
    signed_at TEXT
);

CREATE TABLE IF NOT EXISTS legal_instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id INTEGER NOT NULL REFERENCES countries(id),
    region_scope TEXT,                        -- NULL = country-wide
    title TEXT NOT NULL,
    citation TEXT,
    instrument_type TEXT NOT NULL DEFAULT 'law'
        CHECK (instrument_type IN ('law','regulation','implementing_text','jurisprudence','treaty')),
    areas TEXT NOT NULL,                      -- comma list of area codes
    status TEXT NOT NULL DEFAULT 'in_force'
        CHECK (status IN ('in_force','amended','repealed')),
    url TEXT,
    retrieved TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS legal_requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL REFERENCES assessment_cycles(id),
    country_id INTEGER NOT NULL REFERENCES countries(id),
    region_scope TEXT,
    area_code TEXT NOT NULL,
    instrument_id INTEGER REFERENCES legal_instruments(id),
    requirement TEXT NOT NULL,
    provision TEXT,
    relevance TEXT NOT NULL DEFAULT 'candidate'
        CHECK (relevance IN ('candidate','relevant','not_relevant')),
    relevance_reason TEXT,
    req_type TEXT,                            -- instrument|requirement|jurisprudence|treaty|policy
    authority TEXT,                           -- issuing/administering body
    verification_docs TEXT,                   -- JSON list of document names
    reference_law TEXT,                       -- cited law/instrument name (from evidence.source_name)
    applicability TEXT                        -- plantation|smallholder|both
        CHECK (applicability IS NULL OR applicability IN ('plantation','smallholder','both')),
    supply_chain_node TEXT,                   -- comma-list of business_partner|mill|refinery|source
    is_mandatory TEXT                         -- yes|no|conditional
        CHECK (is_mandatory IS NULL OR is_mandatory IN ('yes','no','conditional')),
    alt_document TEXT,                        -- free-text alternative document description
    mandatory_condition TEXT,                 -- when is_mandatory='conditional', the stated condition (e.g. hectare threshold)
    decided_by TEXT,
    decided_at TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_code TEXT NOT NULL,                  -- stable code, e.g. 'R-07'
    version INTEGER NOT NULL DEFAULT 1,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('rating','mitigation')),
    section_code TEXT NOT NULL,
    condition_text TEXT NOT NULL,             -- human-readable condition
    trigger_rating TEXT,                      -- mitigation: min rating that triggers
    suggested_rating TEXT,                    -- rating rules: rating to suggest
    measures TEXT,                            -- JSON list (mitigation)
    documents TEXT,                           -- JSON list (mitigation)
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checklist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL REFERENCES assessment_cycles(id),
    country_id INTEGER NOT NULL REFERENCES countries(id),
    region_id INTEGER REFERENCES regions(id),
    generation_id TEXT NOT NULL,              -- groups one generation run
    document_name TEXT NOT NULL,
    description TEXT,
    stream TEXT NOT NULL CHECK (stream IN ('legality-baseline','risk-addon','merged')),
    justification TEXT NOT NULL,              -- JSON: requirement ids, section ratings, rule codes
    escalation TEXT,
    grouping TEXT,
    stale INTEGER NOT NULL DEFAULT 0,
    generated_by TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    notes TEXT,                               -- free-text reviewer remark, editable, not part of the audited justification
    notes_by TEXT,
    notes_at TEXT,
    is_mandatory TEXT                         -- yes|no|conditional, from the source legal requirement; null for risk add-ons
        CHECK (is_mandatory IS NULL OR is_mandatory IN ('yes','no','conditional')),
    mandatory_condition TEXT,                 -- when is_mandatory='conditional', the stated condition
    reference_law TEXT,                       -- law citation, used to sequence items law-by-law within a group
    alt_group TEXT                            -- items sharing this id are alternatives to one another (any ONE
                                               -- of them satisfies the requirement), not all required together
);

-- A document a reviewer decided the checklist doesn't need, scoped to one
-- country (+ optionally one region). Applied at read time (latest_generation)
-- so it stays hidden across every future regeneration and export, without
-- touching the auto-computed generation logic — restore just flips it back.
CREATE TABLE IF NOT EXISTS checklist_exclusions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id INTEGER NOT NULL REFERENCES countries(id),
    region_id INTEGER REFERENCES regions(id),
    document_name TEXT NOT NULL,              -- normalized (lower/stripped) for matching
    status TEXT NOT NULL DEFAULT 'excluded' CHECK (status IN ('excluded','restored')),
    excluded_by TEXT NOT NULL,
    excluded_at TEXT NOT NULL,
    restored_by TEXT,
    restored_at TEXT
);

-- A per-country display-name override for a generated document — e.g. a
-- risk-triggered document has no editable source, so this lets a reviewer
-- rename it without touching the rules engine. Applied at read time
-- (latest_generation), same as exclusions; matches by original name.
CREATE TABLE IF NOT EXISTS checklist_renames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id INTEGER NOT NULL REFERENCES countries(id),
    region_id INTEGER REFERENCES regions(id),
    original_name TEXT NOT NULL,
    new_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','reverted')),
    renamed_by TEXT NOT NULL,
    renamed_at TEXT NOT NULL,
    reverted_by TEXT,
    reverted_at TEXT
);

-- A document a reviewer hand-added because neither a legal requirement nor a
-- risk rule captured it. Merged into the checklist at read time, alongside
-- the generated items, under the chosen group heading.
CREATE TABLE IF NOT EXISTS checklist_additions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id INTEGER NOT NULL REFERENCES countries(id),
    region_id INTEGER REFERENCES regions(id),
    document_name TEXT NOT NULL,
    grouping TEXT NOT NULL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','removed')),
    added_by TEXT NOT NULL,
    added_at TEXT NOT NULL,
    removed_by TEXT,
    removed_at TEXT,
    note_by TEXT,
    note_at TEXT
);

CREATE TABLE IF NOT EXISTS narrative_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER NOT NULL REFERENCES assessment_cycles(id),
    country_id INTEGER NOT NULL REFERENCES countries(id),
    region_id INTEGER REFERENCES regions(id),
    section_code TEXT NOT NULL,
    text TEXT NOT NULL,
    sources TEXT,                             -- JSON list
    batch_file TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT,
    country TEXT,
    section_code TEXT,
    before_state TEXT,
    after_state TEXT,
    reason TEXT,
    actor TEXT NOT NULL,
    at TEXT NOT NULL
);
