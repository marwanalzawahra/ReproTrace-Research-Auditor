from __future__ import annotations
from .utils import tokenize, jaccard, finite_number

ROLE_COMPAT = {
    "RESULT_RATE": {
        "RESULT_RATE": 1.00,
        "OPERATING_POINT_FPR": 0.02,
        "COUNT": 0.00,
        "THRESHOLD": 0.05,
        "CONFIDENCE_LEVEL": 0.05,
        "OTHER": 0.20,
        "STEP_CAP": 0.00,
        "SEED": 0.00,
    },
    "OPERATING_POINT_FPR": {
        "OPERATING_POINT_FPR": 1.00,
        "RESULT_RATE": 0.20,
        "COUNT": 0.00,
        "THRESHOLD": 0.25,
        "OTHER": 0.10,
    },
    "COUNT": {
        "COUNT": 1.00,
        "OTHER": 0.15,
        "RESULT_RATE": 0.00,
        "OPERATING_POINT_FPR": 0.00,
        "THRESHOLD": 0.05,
        "SEED": 0.05,
    },
    "STEP_CAP": {
        "STEP_CAP": 1.00,
        "COUNT": 0.30,
        "OTHER": 0.20,
        "THRESHOLD": 0.15,
    },
    "OTHER": {"OTHER": 0.40, "COUNT": 0.20, "RESULT_RATE": 0.20}
}

METRIC_GROUPS = {
    "fpr": {"fpr","false","positive"},
    "sabotage": {"sabotage","undetected","evasion"},
    "success": {"success"},
    "safety": {"safety"},
    "accuracy": {"accuracy","acc"},
    "auc": {"auc","auroc"},
    "count": {"count","number","trajectories","tasks","environments","containers","pairs"},
}

def numeric_similarity(claim, evidence):
    if not finite_number(evidence["value"]):
        return 0.0
    c = float(claim["value"])
    e = float(evidence["value"])
    diff = abs(c-e)
    scale = max(abs(c), abs(e), 1.0)
    rel = diff/scale
    if diff <= 1e-10:
        return 1.0
    if rel <= 5e-4:
        return 0.97
    if rel <= 0.002:
        return 0.90
    if rel <= 0.01:
        return 0.72
    return 0.0

def role_compat(claim_role, evidence_role):
    return ROLE_COMPAT.get(claim_role, {}).get(evidence_role, 0.10)

def metric_anchor_score(claim_text, evidence_text):
    ct = tokenize(claim_text)
    et = tokenize(evidence_text)
    score = jaccard(ct, et)

    # Explicit metric-group alignment bonus.
    cg = {g for g, terms in METRIC_GROUPS.items() if ct & terms}
    eg = {g for g, terms in METRIC_GROUPS.items() if et & terms}
    if cg and eg:
        if cg & eg:
            score = max(score, 0.35)
        elif ("sabotage" in cg and "safety" in eg) or ("safety" in cg and "sabotage" in eg):
            # related but not identical semantics
            score = max(score, 0.18)
        else:
            score *= 0.25
    return min(score, 1.0)

def source_compat(claim_type, source_type):
    if claim_type == "RESULT_METRIC":
        return {
            "DERIVED_RESULT":1.0,"LOG":0.75,"RUN_METADATA":0.35,"CONFIG":0.15,
            "DATA_DEFINITION":0.05,"CODE":0.20,"OTHER":0.15
        }.get(source_type,0.10)
    if claim_type == "DATASET_FACT":
        return {
            "DATA_DEFINITION":1.0,"RUN_METADATA":0.75,"CONFIG":0.45,
            "DERIVED_RESULT":0.25,"LOG":0.30,"CODE":0.25,"OTHER":0.20
        }.get(source_type,0.15)
    if claim_type == "HYPERPARAM":
        return {
            "CONFIG":1.0,"CODE":0.85,"RUN_METADATA":0.75,"LOG":0.60,
            "DERIVED_RESULT":0.25,"DATA_DEFINITION":0.20,"OTHER":0.20
        }.get(source_type,0.15)
    if claim_type == "CONDITION":
        return {
            "DERIVED_RESULT":0.90,"LOG":0.85,"CONFIG":0.60,"RUN_METADATA":0.45,
            "OTHER":0.20
        }.get(source_type,0.15)
    return 0.10

def rank_candidates(claim, evidence_values):
    if claim["claim_type"] in {"IGNORED","NON_RESULT"}:
        return []

    ranked = []
    for ev in evidence_values:
        ns = numeric_similarity(claim, ev)
        if ns <= 0:
            continue

        rc = role_compat(claim["claim_role"], ev["evidence_role"])
        if rc <= 0:
            continue

        sc = source_compat(claim["claim_type"], ev["source_type"])
        anchor = metric_anchor_score(claim["context"], f"{ev['locator']} {ev['evidence_text']} {ev['source']}")

        # Role compatibility matters much more in v0.3.
        score = 0.42*ns + 0.28*rc + 0.15*sc + 0.15*anchor

        ranked.append({
            **{k:v for k,v in ev.items() if k != "tokens"},
            "numeric_score": round(ns,4),
            "role_score": round(rc,4),
            "source_score": round(sc,4),
            "anchor_score": round(anchor,4),
            "evidence_score": round(score,4),
        })

    ranked.sort(key=lambda x:(-x["evidence_score"],-x["role_score"],-x["anchor_score"],x["source"]))
    return ranked

def decide_status(claim, candidates):
    if claim["claim_type"] in {"IGNORED","NON_RESULT"}:
        return "IGNORED", claim["classification_reason"]
    if not candidates:
        return "UNSUPPORTED", "no_role_compatible_evidence"

    top = candidates[0]
    second = candidates[1] if len(candidates)>1 else None
    margin = top["evidence_score"] - (second["evidence_score"] if second else 0)

    # Critical v0.3 rule:
    # NEVER verify from exact numeric equality alone.
    if (
        top["numeric_score"] >= 0.97
        and top["role_score"] >= 0.90
        and top["source_score"] >= 0.70
        and top["anchor_score"] >= 0.12
        and top["evidence_score"] >= 0.80
        and (second is None or margin >= 0.06)
    ):
        return "VERIFIED", "role_and_semantic_anchor"

    if top["evidence_score"] >= 0.74:
        if second and margin < 0.04:
            return "AMBIGUOUS", "multiple_role_compatible_candidates"
        return "LIKELY", "strong_candidate_but_not_verified"

    if len(candidates)>1:
        return "AMBIGUOUS", "weak_or_multiple_candidates"
    return "LIKELY", "single_weak_candidate"

def match_claims(claims, evidence_values):
    out=[]
    for c in claims:
        cand=rank_candidates(c,evidence_values)
        status,reason=decide_status(c,cand)
        out.append({
            **c,
            "status":status,
            "status_reason":reason,
            "candidates":cand[:20],
            "candidate_count":len(cand),
        })
    return out
