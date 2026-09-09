"""Rating suggestion engine. Rules are data (rules table); the operator marks
which conditions are met by the approved evidence; the engine derives the
suggested rating and a rule trace. The human confirms or overrides — the
suggestion is never binding."""

import json

RISK_ORDER = ["negligible", "not_negligible"]


def rating_rules(conn, section_code):
    return conn.execute(
        "SELECT * FROM rules WHERE rule_type='rating' AND section_code=?"
        " AND status='active' ORDER BY rule_code", (section_code,)).fetchall()


def mitigation_rules(conn, section_code=None):
    q = "SELECT * FROM rules WHERE rule_type='mitigation' AND status='active'"
    params = []
    if section_code:
        q += " AND section_code=?"
        params.append(section_code)
    return conn.execute(q + " ORDER BY rule_code", params).fetchall()


def suggest(rating_scale, met_rules):
    """Derive suggested rating from the met rules' suggested_rating values.

    risk scale (S2-S10): most severe among met rules wins — any single met
    rule pointing to not_negligible makes the section not_negligible; no met
    rules -> None.
    benchmark scale (S1): taken from evidence directly, not rules -> None.
    """
    ratings = [r["suggested_rating"] for r in met_rules if r["suggested_rating"]]
    if not ratings:
        return None
    order = RISK_ORDER
    idx = max(order.index(x) for x in ratings if x in order)
    return order[idx]


def build_trace(met_rules, evidence_count):
    return json.dumps({
        "met_rules": [
            {"rule_code": r["rule_code"], "condition": r["condition_text"],
             "suggested_rating": r["suggested_rating"]}
            for r in met_rules],
        "approved_evidence_count": evidence_count,
    }, ensure_ascii=False)
