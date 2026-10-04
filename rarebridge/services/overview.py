"""Disease overview: the entry point of the journey.

Opportunities are strictly target-scoped: an assessment appears for disease D
only if its bundle targets D for the requested goal. A bundle for another target
is never substituted, even when the asset is shared; the gap is reported instead.
"""

from __future__ import annotations

import re

from rarebridge.assessment import assess

from .constants import SUPPORTED_GOALS

ASSET_TYPE_ORDER = {"published_study_framework": 0, "measurement_method": 1,
                    "biomarker_acquisition_protocol": 2, "dataset": 3, "registry_dataset": 4,
                    "data_collection_platform": 5}


class UnknownDisease(LookupError):
    pass


class UnknownGoal(ValueError):
    pass


def _first_sentences(text, count=2, limit=420):
    text = " ".join((text or "").split())
    parts = re.split(r"(?<=[.!?])\s+", text)
    summary = " ".join(parts[:count]).strip()
    return summary if len(summary) <= limit else summary[:limit].rsplit(" ", 1)[0] + "\u2026"


class OverviewService:
    def __init__(self, registry, related, contacts):
        self.reg = registry
        self.related = related
        self.contacts = contacts

    def _check_inputs(self, disease_id, goal_id):
        if self.reg.nodes.get(disease_id, {}).get("type") != "disease":
            raise UnknownDisease(disease_id)
        if goal_id not in SUPPORTED_GOALS:
            raise UnknownGoal(goal_id)

    def disease_card(self, disease_id):
        node = self.reg.nodes[disease_id]
        record = self.reg.disease_records.get(disease_id, {})
        summary_source = self.reg.disease_record_source.get(disease_id)
        summary = _first_sentences(record.get("description"))
        if not summary:
            summary = "No summary in the imported record; inspect the sources for the proposed research use."
        return {
            "id": disease_id, "type": "disease", "label": node["label"], "summary": summary,
            "synonyms": self.reg.disease_names(disease_id)[1:],
            "summary_source_ids": [summary_source] if summary_source else [],
            "summary_review_status": "pending",
            "summary_note": "First sentences of the AI-curated DisMech description; pending independent review.",
        }

    def opportunities(self, disease_id, goal_id):
        reg = self.reg
        bundle_ids = sorted(
            {bid for (asset_id, target, goal), ids in reg.bundles_by_scope.items()
             if target == disease_id and goal == goal_id for bid in ids},
            key=lambda bid: (ASSET_TYPE_ORDER.get(reg.bundles[bid]["asset"].get("type"), 9), bid))
        out = []
        for bid in bundle_ids:
            bundle = reg.bundle(bid)
            asset = bundle["asset"]
            record = reg.assets.get(asset["id"], {})
            result = assess(bundle)
            open_required = [row["id"] for row in result["checks"] if row["required"] and row["status"] != "supported"]
            documented_for = sorted(set(record.get("target_disease_ids", [])) - {disease_id})
            reason = (record.get("proposed_use") or "Existing research resource with a scoped assessment.")
            reason += (f" Assessment {bid} is scoped to {bundle['target_disease']['label']}; "
                       f"current outcome {result['outcome']} with {len(open_required)} open required "
                       f"check{'s' if len(open_required) != 1 else ''}. Inspect the checks before any reuse.")
            out.append({
                "id": f"opportunity:{bid}",
                "asset": asset,
                "assessment_id": bid,
                "reason": reason,
                "source_ids": reg.bundle_source_ids(bid),
                "candidate_score": None,
                "ranking_method": "curated_target_scoped_assessment",
                # additive
                "outcome": result["outcome"],
                "open_required_check_ids": open_required,
                "documented_for_other_disease_ids": documented_for,
                "bundle_origin": reg.bundle_origin[bid],
            })
        return out

    def unassessed_assets(self, disease_id, goal_id, assessed_asset_ids):
        reg = self.reg
        out = []
        for asset_id, record in reg.assets.items():
            if asset_id in assessed_asset_ids or disease_id not in record.get("target_disease_ids", []):
                continue
            if goal_id not in record.get("goal_ids", [goal_id]):
                continue
            node = reg.nodes.get(asset_id, {})
            out.append({
                "asset": {k: record[k] for k in ("id", "label", "type", "url", "access_status") if k in record},
                "assessment_id": None,
                "reason": ("Documented for this disease by its sources, but no scoped assessment exists yet "
                           "for this disease and goal. Inspect the sources before planning any use."),
                "source_ids": sorted({reg.canonical_source(s) or s for s in record.get("source_ids", [])}),
                "review_status": node.get("review_status", "pending"),
                "unverified": record.get("unverified", []),
            })
        out.sort(key=lambda item: (ASSET_TYPE_ORDER.get(item["asset"].get("type"), 9), item["asset"]["id"]))
        return out

    def build(self, disease_id, goal_id):
        self._check_inputs(disease_id, goal_id)
        reg = self.reg
        label = reg.disease_label(disease_id)
        related = self.related.related_for(disease_id)
        for item in related:
            item["organizations"] = self.contacts.for_disease(item["id"], kinds={"organization"})
        opportunities = self.opportunities(disease_id, goal_id)
        assessed_assets = {opp["asset"]["id"] for opp in opportunities}
        unassessed = self.unassessed_assets(disease_id, goal_id, assessed_assets)
        organizations = self.contacts.for_disease(disease_id)

        gaps = []
        if not reg.overlay_meta["loaded"]:
            gaps.append("Curation overlay not loaded: patient organizations, studies and curated assets "
                        "are unavailable in this run.")
        if not opportunities:
            gaps.append(f"No assessment in this slice targets {label} for {goal_id}.")
        def documented_here(asset_id):
            targets = reg.assets.get(asset_id, {}).get("target_disease_ids")
            return targets is None or disease_id in targets

        other_target = sorted({bid for (asset_id, target, goal), ids in reg.bundles_by_scope.items()
                               if target != disease_id and goal == goal_id and asset_id not in assessed_assets
                               and documented_here(asset_id) for bid in ids})
        for bid in other_target:
            asset = reg.bundles[bid]["asset"]
            target_label = reg.bundles[bid]["target_disease"]["label"]
            gaps.append(f"Assessment {bid} covers '{asset['label']}' for {target_label} only; it was not "
                        f"substituted for {label}. A {label}-targeted assessment is needed.")
        if not any(c["kind"] == "organization" for c in organizations):
            gaps.append(f"No patient organization for {label} is recorded in this slice. Absence here does not "
                        "mean none exists.")
        if not any(item["recorded_routes"] for item in related):
            gaps.append(f"No recorded study route links {label} to another disease in this slice; related "
                        "diseases shown are annotation-overlap candidates only.")

        scope = (f"{len(reg.disease_ids())}-disease demonstration slice (pinned DisMech snapshot "
                 f"{reg.snapshot_commit[:12]}"
                 + (" plus curated overlay" if reg.overlay_meta["loaded"] else "")
                 + "). Not a complete literature search; missing items here are not evidence they do not exist.")
        if reg.overlay_meta.get("loaded"):
            pending = reg.overlay_meta["review_log_status"].get("pending", 0)
            if pending:
                scope += f" {pending} curated assertions are still pending human source review."
        return {
            "disease": self.disease_card(disease_id),
            "goal_id": goal_id,
            "related_diseases": related,
            "opportunities": opportunities,
            "organizations": organizations,
            "coverage": {"disease_count": len(reg.disease_ids()), "scope_note": scope, "gaps": gaps},
            "data_origin": reg.data_origin,
            # additive
            "goal_label": SUPPORTED_GOALS[goal_id],
            "unassessed_assets": unassessed,
        }
