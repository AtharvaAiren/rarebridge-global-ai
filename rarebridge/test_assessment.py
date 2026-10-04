"""Checks for consequential evidence and provenance failures, using stdlib only."""

import copy
import json
import unittest
from pathlib import Path

from assessment import assess, compare_withdrawal
from build_graph import build_graph


DATA = Path(__file__).resolve().parent / "data"


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads((DATA / "assessment-syngap1.json").read_text())

    def check(self, result, check_id):
        return next(row for row in result["checks"] if row["id"] == check_id)

    def test_missing_permission_does_not_become_reuse_permission(self):
        result = assess(self.bundle)
        self.assertEqual(result["outcome"], "needs_information")
        self.assertEqual(self.check(result, "target-observed")["status"], "supported")
        self.assertEqual(self.check(result, "implementation-access")["status"], "unknown")
        self.assertTrue(any(row["check_id"] == "implementation-access" for row in result["followup_questions"]))

    def test_related_disease_without_target_evidence_remains_unknown(self):
        bundle = json.loads((DATA / "assessment-scn2a.json").read_text())
        result = assess(bundle)
        self.assertEqual(self.check(result, "target-observed")["status"], "unknown")
        self.assertEqual(result["outcome"], "needs_information")

    def test_one_publication_with_two_identifiers_is_withdrawn_everywhere(self):
        result = compare_withdrawal(self.bundle, ["PMID:42446932"])
        self.assertEqual(result["after"]["withdrawn_sources"], ["DOI:10.1002/epi.70374"])
        for check_id in ["documented-framework", "target-observed"]:
            self.assertEqual(self.check(result["after"], check_id)["status"], "unknown")
        self.assertEqual({item["check_id"] for item in result["changed_checks"]},
                         {"documented-framework", "target-observed"})

    def test_redundant_independent_source_retains_support(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["sources"]["synthetic-independent-source"] = {"url": "https://example.org/test-only"}
        bundle["checks"][1]["evidence"].append({"source_id": "synthetic-independent-source",
             "polarity": "support", "review_status": "source_checked", "rationale": "Synthetic test evidence."})
        result = compare_withdrawal(bundle, ["PMID:42446932"])
        self.assertEqual(self.check(result["after"], "target-observed")["status"], "supported")
        self.assertEqual(self.check(result["after"], "target-observed")["supporting_sources"],
                         ["synthetic-independent-source"])

    def test_conflicting_source_requires_expert_review(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["sources"]["synthetic-conflict"] = {"url": "https://example.org/test-only"}
        bundle["checks"][1]["evidence"].append({"source_id": "synthetic-conflict", "polarity": "refute",
             "review_status": "source_checked", "rationale": "Synthetic contradicting evidence."})
        result = assess(bundle)
        self.assertEqual(self.check(result, "target-observed")["status"], "conflicting")
        self.assertEqual(result["outcome"], "needs_expert_review")

    def test_explicit_context_mismatch_is_not_overridden_by_other_support(self):
        bundle = copy.deepcopy(self.bundle)
        # Synthetic context test; no medical fact is asserted by this fixture.
        bundle["checks"].append({"id": "variant-effect", "question": "Do the documented variant effects match?",
          "required": True, "evidence": [{"source_id": "PMID:42446932", "polarity": "refute",
            "review_status": "source_checked", "rationale": "Synthetic test: incompatible experimental direction."}],
          "next_question": "Which experimental model has the required direction?"})
        self.assertEqual(assess(bundle)["outcome"], "not_supported_for_stated_use")

    def test_unchecked_extraction_cannot_create_supported_status(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["checks"][1]["evidence"][0]["review_status"] = "pending"
        result = assess(bundle)
        self.assertEqual(self.check(result, "target-observed")["status"], "needs_source_review")
        self.assertEqual(result["outcome"], "needs_source_review")

    def test_unknown_withdrawal_is_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, "Unknown source to withdraw"):
            assess(self.bundle, ["not-in-corpus"])

    def test_ambiguous_publication_alias_is_rejected(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["sources"]["duplicate"] = {"url": "https://example.org/test-only", "aliases": ["PMID:42446932"]}
        with self.assertRaisesRegex(ValueError, "Ambiguous source alias"):
            assess(bundle)

    def test_no_required_checks_cannot_create_positive_assessment(self):
        bundle = copy.deepcopy(self.bundle)
        for check in bundle["checks"]:
            check["required"] = False
        with self.assertRaisesRegex(ValueError, "at least one required"):
            assess(bundle)


class GraphImportTests(unittest.TestCase):
    def test_graph_preserves_provenance_and_does_not_invent_transfers(self):
        manifest = json.loads((DATA / "source-manifest.json").read_text())
        graph = build_graph(json.loads((DATA / "disorders.json").read_text()), manifest)
        node_ids = {item["id"] for item in graph["nodes"]}
        edge_ids = [item["id"] for item in graph["edges"]]
        self.assertEqual(len(edge_ids), len(set(edge_ids)))
        self.assertEqual(sum(item["type"] == "disease" for item in graph["nodes"]), 3)
        for edge in graph["edges"]:
            self.assertIn(edge["source"], node_ids)
            self.assertIn(edge["target"], node_ids)
            self.assertEqual(edge["review_status"], "pending")
            self.assertEqual(edge["provenance"]["snapshot_commit"], manifest["snapshot_commit"])
            self.assertNotIn(edge["relation"], {"can_share_treatment", "can_reuse_asset", "eligible_for_trial"})


if __name__ == "__main__":
    unittest.main()
