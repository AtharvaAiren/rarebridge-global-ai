"""Evaluate evidence attached to an explicitly scoped research-asset question.

This module does not determine biological compatibility from similarity or select
treatments. A curator supplies the question, required checks and evidence labels.
Statuses describe the recorded evidence, never permission to conduct a study.
"""

import argparse
import json
from pathlib import Path


def validate(bundle):
    sources = bundle.get("sources", {})
    aliases = {}
    for source_id, source in sources.items():
        if not source.get("url"):
            raise ValueError(f"Source {source_id} has no URL")
        for alias in [source_id, *source.get("aliases", [])]:
            if alias in aliases and aliases[alias] != source_id:
                raise ValueError(f"Ambiguous source alias: {alias}")
            aliases[alias] = source_id
    if not bundle.get("checks"):
        raise ValueError("An assessment needs explicit required checks")
    if not any(check.get("required", True) for check in bundle["checks"]):
        raise ValueError("An assessment needs at least one required check")
    check_ids = set()
    for check in bundle["checks"]:
        if check["id"] in check_ids:
            raise ValueError(f"Duplicate check ID: {check['id']}")
        check_ids.add(check["id"])
        if not check.get("question"):
            raise ValueError(f"Check {check['id']} has no scoped question")
        if not check.get("next_question"):
            raise ValueError(f"Check {check['id']} has no follow-up question")
        for evidence in check.get("evidence", []):
            if evidence.get("source_id") not in aliases:
                raise ValueError(f"Unknown evidence source: {evidence.get('source_id')}")
            if evidence.get("polarity") not in {"support", "refute", "uncertain"}:
                raise ValueError("Evidence polarity must be support, refute or uncertain")
            if evidence.get("review_status") not in {"pending", "source_checked"}:
                raise ValueError("Evidence needs a source-review status")
            if not evidence.get("rationale"):
                raise ValueError("Evidence needs an explanation of its scope")
    return aliases


def assess(bundle, withdrawn_sources=()):
    """Withdrawal removes every occurrence of a publication, including aliases.

    'source_checked' means a curator checked this source against this specific
    factual assertion. It does not mean a scientist approved the proposed use.
    A publication appearing on several edges remains one source.
    """
    aliases = validate(bundle)
    unknown = set(withdrawn_sources) - aliases.keys()
    if unknown:
        raise ValueError(f"Unknown source to withdraw: {sorted(unknown)}")
    withdrawn = {aliases[item] for item in withdrawn_sources}
    rows = []
    for check in bundle["checks"]:
        active, removed = [], []
        for item in check.get("evidence", []):
            evidence = dict(item, source_id=aliases[item["source_id"]])
            (removed if evidence["source_id"] in withdrawn else active).append(evidence)
        reviewed = [item for item in active if item["review_status"] == "source_checked"]
        support = {item["source_id"] for item in reviewed if item["polarity"] == "support"}
        refute = {item["source_id"] for item in reviewed if item["polarity"] == "refute"}
        if support and refute:
            status = "conflicting"
        elif refute:
            status = "refuted"
        elif support:
            status = "supported"
        elif any(item["review_status"] == "pending" for item in active):
            status = "needs_source_review"
        else:
            status = "unknown"
        rows.append({
            "id": check["id"], "question": check["question"],
            "required": check.get("required", True), "category": check.get("category", "research"),
            "status": status, "supporting_sources": sorted(support),
            "refuting_sources": sorted(refute), "active_evidence": active,
            "withdrawn_evidence": removed, "next_question": check["next_question"],
            "contact_role": check.get("contact_role", "research collaborator"),
        })
    required = [row for row in rows if row["required"]]
    states = {row["status"] for row in required}
    if "conflicting" in states:
        outcome = "needs_expert_review"
    elif "refuted" in states:
        outcome = "not_supported_for_stated_use"
    elif "needs_source_review" in states:
        outcome = "needs_source_review"
    elif "unknown" in states:
        outcome = "needs_information"
    else:
        outcome = "candidate_for_expert_review"
    followups = [{"check_id": row["id"], "question": row["next_question"],
                  "contact_role": row["contact_role"], "reason": row["status"]}
                 for row in required if row["status"] != "supported"]
    return {
        "assessment_id": bundle["id"], "target_disease": bundle["target_disease"],
        "goal": bundle["goal"], "asset": bundle["asset"], "outcome": outcome,
        "checks": rows, "followup_questions": followups,
        "withdrawn_sources": sorted(withdrawn),
        "limitations": "A rule-based assessment of curated evidence. No biological validation, access permission, treatment recommendation or calibrated probability is implied.",
    }


def compare_withdrawal(bundle, withdrawn_sources):
    before = assess(bundle)
    after = assess(bundle, withdrawn_sources)
    previous = {row["id"]: row for row in before["checks"]}
    changes = []
    for row in after["checks"]:
        old = previous[row["id"]]
        if (old["status"], old["supporting_sources"], old["refuting_sources"]) != (
                row["status"], row["supporting_sources"], row["refuting_sources"]):
            changes.append({"check_id": row["id"], "before": old["status"],
                            "after": row["status"], "remaining_support": row["supporting_sources"]})
    return {"before": before, "after": after, "changed_checks": changes,
            "interpretation": "This shows dependence on recorded publications, not biological causality. An unchanged overall outcome can still conceal loss of support for an individual check."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--withdraw", action="append", default=[])
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_text())
    result = compare_withdrawal(bundle, args.withdraw) if args.withdraw else assess(bundle)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
