"""Wrap the shared assessment engine in the agreed response envelope.

before/after retain all exact rarebridge.assessment.assess() fields and add only
recorded proposed-use context. Nonempty withdrawals use compare_withdrawal().
Stored bundles are never mutated: the engine receives a deep copy and only the
request's withdrawal list changes between calls. An empty list is the reset.
"""

from __future__ import annotations

from copy import deepcopy

from rarebridge.assessment import assess, compare_withdrawal, validate

ASSET_CONTEXT_KEYS = ("description", "documented_context", "unverified", "owner_status", "proposed_use",
                      "goal_ids", "target_disease_ids", "source_ids", "access_status")
ASSESSMENT_CONTEXT_KEYS = ("proposed_use", "target_subgroup", "documented_differences", "assumptions")


class UnknownAssessment(LookupError):
    pass


class InvalidWithdrawal(ValueError):
    def __init__(self, details):
        self.details = details
        super().__init__("Some withdrawn source IDs are not in this data slice.")


class AssessmentService:
    def __init__(self, registry, contacts):
        self.reg = registry
        self.contacts = contacts

    def _classify_withdrawals(self, bundle, withdrawn):
        aliases = validate(bundle)  # alias -> canonical within this bundle
        applied, ignored, problems = [], [], []
        for index, raw in enumerate(withdrawn):
            if not isinstance(raw, str) or not raw.strip():
                problems.append({"loc": ["body", "withdrawn_source_ids", index],
                                 "msg": "Source IDs must be non-empty strings."})
                continue
            if raw in aliases:
                applied.append(raw)
                continue
            canonical = self.reg.canonical_source(raw)
            if canonical is None:
                problems.append({"loc": ["body", "withdrawn_source_ids", index],
                                 "msg": f"Unknown source ID: {raw}", "value": raw})
            elif canonical in aliases:
                applied.append(canonical)
            else:
                ignored.append({"source_id": raw, "canonical_id": canonical,
                                "reason": "Known source, but this assessment does not cite it."})
        if problems:
            raise InvalidWithdrawal(problems)
        # De-duplicate while keeping the caller's order.
        return list(dict.fromkeys(applied)), ignored

    def evaluate(self, assessment_id, withdrawn_source_ids):
        if assessment_id not in self.reg.bundles:
            raise UnknownAssessment(assessment_id)
        bundle = self.reg.bundle(assessment_id)
        applied, ignored = self._classify_withdrawals(bundle, list(withdrawn_source_ids or []))

        before = assess(bundle)
        if applied:
            comparison = compare_withdrawal(bundle, applied)
            after, changed = comparison["after"], comparison["changed_checks"]
            interpretation = comparison["interpretation"]
        else:
            after, changed = assess(bundle), []
            interpretation = "No source is withdrawn; this is the recorded support."

        # These recorded context fields define the proposed use and participate
        # in the lead's current-assessment fingerprint. Copy them without changing
        # any deterministic check or outcome; do not infer context from an asset.
        for result in (before, after):
            for key in ASSESSMENT_CONTEXT_KEYS:
                if key in bundle:
                    result[key] = deepcopy(bundle[key])

        withheld = set(after["withdrawn_sources"])
        contacts = self.contacts.for_bundle(bundle)
        for contact in contacts:
            canon = {self.reg.canonical_source(s) or s for s in contact.get("source_ids", [])}
            contact["all_sources_withdrawn"] = bool(canon) and canon <= withheld

        source_roles = {}
        for sid in bundle.get("sources", {}):
            source_roles.setdefault(self.reg.canonical_source(sid) or sid, []).append("assessment_evidence")
        for contact in contacts:
            for sid in contact.get("source_ids", []):
                canonical = self.reg.canonical_source(sid) or sid
                roles = source_roles.setdefault(canonical, [])
                if "contact_route" not in roles:
                    roles.append("contact_route")
        sources = self.reg.sources_for(source_roles.keys())
        for canonical, record in sources.items():
            record["withdrawn_in_this_view"] = canonical in withheld

        evidence = [item for check in bundle["checks"] for item in check.get("evidence", [])]
        asset_record = self.reg.assets.get(bundle["asset"]["id"], {})
        return {
            "before": before,
            "after": after,
            "changed_checks": changed,
            "sources": sources,
            "coverage": bundle.get("coverage", ""),
            "contacts": contacts,
            "explanation": {"generation_mode": "none", "text": None, "cited_source_ids": [], "model": None},
            # additive fields
            "goal_id": self.reg.bundle_goal[assessment_id],
            "goal_id_inferred": assessment_id in self.reg.bundle_goal_inferred,
            "interpretation": interpretation,
            "withdrawn_source_ids_applied": sorted(withheld),
            "withdrawn_source_ids_ignored": ignored,
            "source_roles": source_roles,
            "asset_context": {key: asset_record[key] for key in ASSET_CONTEXT_KEYS if key in asset_record},
            "review_summary": {
                "evidence_items": len(evidence),
                "pending": sum(1 for e in evidence if e.get("review_status") == "pending"),
                "source_checked": sum(1 for e in evidence if e.get("review_status") == "source_checked"),
                "note": ("'source_checked' means a person checked a narrow factual assertion against the "
                         "cited source. It is not clinical validation or permission to reuse an asset."),
            },
            "bundle_origin": self.reg.bundle_origin[assessment_id],
        }
