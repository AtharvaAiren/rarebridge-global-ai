"""Integration checks for brief grounding, withdrawal and honest fallbacks."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from rarebridge.ai.brief import build_collaboration_brief
from rarebridge.ai.service import VALIDATION


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "handoffs" / "fixtures"
ANCHOR = "DOI:10.1002/epi.70374"
ALIAS = "PMID:42446932"
ANCHOR_URL = "https://doi.org/10.1002/epi.70374"


def fixture(name="assessment-syngap1.json"):
    return json.loads((FIXTURES / name).read_text())


def validated_explanation(mode="live", *, assessment=None):
    assessment = fixture()["after"] if assessment is None else assessment
    encoded = json.dumps(assessment, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "generation_mode": mode, "model": "test-model",
        "text": "The framework is documented, while access and local feasibility need checking.",
        "draft_message": "Hello, could we discuss access requirements and local feasibility for our proposed study?",
        "cited_source_ids": [ANCHOR, ALIAS],
        "validation": {"status": "passed", "checks": ["schema", "status_alignment", "citation_scope", "required_followups"]},
        "provenance": {"assessment_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest()},
    }


class CollaborationBriefTests(unittest.TestCase):
    def test_known_framework_keeps_two_narrow_facts_and_access_questions(self):
        response = fixture()
        original = deepcopy(response)
        brief = build_collaboration_brief(response)
        self.assertEqual(response, original)
        self.assertEqual(brief["outcome"], "needs_information")
        self.assertEqual({row["check_id"] for row in brief["recorded_support"]}, {"documented-framework", "target-observed"})
        self.assertEqual(brief["provenance"]["distinct_sources_used"], 1)
        self.assertEqual(list(brief["sources"]), [ANCHOR])
        required = [question for question in brief["followup_questions"] if question["required"]]
        self.assertEqual({item["check_id"] for item in required}, {"implementation-access", "local-feasibility"})
        self.assertIn("needs_information", brief["text_export"])
        self.assertIn("permissions, staff and equipment", brief["draft_message"])
        self.assertIn(ANCHOR_URL, brief["text_export"])
        self.assertEqual(brief["generation_mode"], "none")
        self.assertEqual(brief["draft_origin"], "deterministic_template")

    def test_withdrawn_paper_changes_export_and_removes_backed_routes(self):
        response = fixture("assessment-syngap1-withdrawn.json")
        # A withdrawal alias is resolved just as the assessment engine resolves it.
        response["after"]["withdrawn_sources"] = [ALIAS]
        brief = build_collaboration_brief(response)
        self.assertEqual(brief["recorded_support"], [])
        self.assertEqual(brief["sources"], {})
        self.assertEqual(brief["public_collaborator_routes"], [])
        self.assertEqual(len(brief["excluded_collaborator_routes"]), 2)
        self.assertEqual([source["canonical_id"] for source in brief["excluded_sources"]], [ANCHOR])
        self.assertEqual(brief["outcome"], response["after"]["outcome"])
        self.assertEqual({row["check_id"]: row["status"] for row in brief["unanswered_checks"]},
                         {row["id"]: row["status"] for row in response["after"]["checks"]})
        self.assertIn("No active source is cited", brief["text_export"])
        self.assertIn("Excluded sources (not supporting", brief["text_export"])
        self.assertNotIn(ANCHOR_URL, brief["text_export"])
        self.assertNotIn("SYNGAP1 is a studied cohort", brief["draft_message"])

    def test_scn2a_unknown_applicability_does_not_become_negative_evidence(self):
        brief = build_collaboration_brief(fixture("assessment-scn2a.json"))
        row = next(row for row in brief["unanswered_checks"] if row["check_id"] == "target-observed")
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["refuting_source_ids"], [])
        self.assertIn("does not establish SCN2A applicability", row["recorded_evidence"][0]["rationale"])
        self.assertIn("relevant SCN2A subgroup", brief["draft_message"])
        self.assertNotIn("not_supported_for_stated_use", brief["text_export"])

    def test_scn2a_withdrawal_retains_questions_and_loses_framework_support(self):
        brief = build_collaboration_brief(fixture("assessment-scn2a-withdrawn.json"))
        self.assertEqual(brief["recorded_support"], [])
        self.assertEqual(brief["sources"], {})
        self.assertEqual(brief["outcome"], "needs_information")
        self.assertIn("relevant SCN2A subgroup", brief["draft_message"])
        self.assertNotIn(ANCHOR_URL, brief["text_export"])

    def test_repeated_publication_alias_is_one_active_source(self):
        response = fixture()
        check = response["after"]["checks"][0]
        check["supporting_sources"] += [ALIAS, ANCHOR]
        aliased_evidence = dict(check["active_evidence"][0], source_id=ALIAS)
        check["active_evidence"].append(aliased_evidence)
        response["contacts"][0]["source_ids"] += [ALIAS]
        brief = build_collaboration_brief(response)
        self.assertEqual(len(brief["sources"]), 1)
        self.assertEqual(len(brief["recorded_support"][0]["recorded_evidence"]), 1)
        self.assertEqual(brief["recorded_support"][0]["supporting_source_ids"], [ANCHOR])

    def test_unknown_and_ambiguous_source_references_fail_clearly(self):
        response = fixture()
        response["after"]["checks"][0]["supporting_sources"] = ["DOI:missing"]
        with self.assertRaisesRegex(ValueError, "Unknown source"):
            build_collaboration_brief(response)
        response = fixture()
        response["sources"][ALIAS] = deepcopy(response["sources"][ANCHOR])
        with self.assertRaisesRegex(ValueError, "Ambiguous source alias"):
            build_collaboration_brief(response)

    def test_asset_contact_fallback_is_explicitly_unreviewed(self):
        response = fixture()
        response["contacts"] = []
        brief = build_collaboration_brief(response)
        self.assertEqual(len(brief["public_collaborator_routes"]), 2)
        for route in brief["public_collaborator_routes"]:
            self.assertEqual(route["status_for_brief"], "unreviewed")
            self.assertEqual(route["review_status"], "pending")
            self.assertFalse(route["source_backed"])
            self.assertIn("unconfirmed", route["role"])
        self.assertIn("(unreviewed)", brief["text_export"])

    def test_withdrawal_also_hides_alias_urls_in_unreviewed_fallback_routes(self):
        response = fixture("assessment-syngap1-withdrawn.json")
        response["contacts"] = []
        response["after"]["asset"]["url"] = "https://pubmed.ncbi.nlm.nih.gov/42446932/"
        response["after"]["asset"]["public_researcher_routes"] = [{"name": "Recorded researcher", "url": "https://pubmed.ncbi.nlm.nih.gov/42446932/"}]
        brief = build_collaboration_brief(response)
        self.assertIsNone(brief["asset"]["url"])
        self.assertEqual(brief["public_collaborator_routes"], [])
        self.assertNotIn("https://pubmed.ncbi.nlm.nih.gov/42446932/", brief["text_export"])

    def test_invalid_contact_links_are_not_exported(self):
        response = fixture()
        response["contacts"] = [{"id": "bad", "label": "Unknown", "url": "javascript:alert(1)", "source_ids": []},
                                {"id": "local", "label": "Local", "url": "http://127.0.0.1/private", "source_ids": []}]
        brief = build_collaboration_brief(response)
        self.assertEqual(brief["public_collaborator_routes"], [])
        self.assertEqual(len(brief["excluded_collaborator_routes"]), 2)
        self.assertNotIn("javascript:", brief["text_export"])
        self.assertNotIn("127.0.0.1", brief["text_export"])

    def test_unknown_contact_source_is_an_error_not_invented_authority(self):
        response = fixture()
        response["contacts"][0]["source_ids"] = ["missing-contact-source"]
        with self.assertRaisesRegex(ValueError, "Unknown source"):
            build_collaboration_brief(response)

    def test_validated_live_and_cached_drafts_preserve_modes_and_deduplicate_citations(self):
        for mode in ("live", "cached"):
            with self.subTest(mode=mode):
                explanation = validated_explanation(mode)
                brief = build_collaboration_brief(fixture(), explanation=explanation)
                self.assertEqual(brief["generation_mode"], mode)
                self.assertEqual(brief["draft_message"], explanation["draft_message"])
                self.assertEqual(brief["provenance"]["model"], "test-model")
                self.assertEqual(brief["draft_origin"], "ai_service_validated")
                self.assertEqual(len(brief["sources"]), 1)

    def test_actual_service_validation_marker_accepts_generated_draft(self):
        explanation = validated_explanation()
        explanation["validation"] = deepcopy(VALIDATION)
        brief = build_collaboration_brief(fixture(), explanation=explanation)
        self.assertEqual(brief["generation_mode"], "live")
        self.assertEqual(brief["draft_message"], explanation["draft_message"])
        self.assertIsNone(brief["provenance"]["ai_rejection_reason"])

    def test_export_identifies_provider_from_accepted_service_provenance(self):
        explanation = validated_explanation()
        explanation["provider"] = "untrusted_top_level_value"
        explanation["response_id"] = "untrusted_top_level_id"
        explanation["provenance"].update(provider="anthropic", response_id="msg_fixture_test")
        brief = build_collaboration_brief(fixture(), explanation=explanation)
        self.assertEqual(brief["provenance"]["provider"], "anthropic")
        self.assertEqual(brief["provenance"]["response_id"], "msg_fixture_test")
        explanation["provenance"].pop("provider")
        explanation["provenance"].pop("response_id")
        brief = build_collaboration_brief(fixture(), explanation=explanation)
        self.assertIsNone(brief["provenance"]["provider"])
        self.assertIsNone(brief["provenance"]["response_id"])

    def test_same_id_and_citations_cannot_reuse_an_explanation_for_changed_state(self):
        for change in ("status", "local_constraints"):
            with self.subTest(change=change):
                response = fixture()
                explanation = validated_explanation("cached", assessment=response["after"])
                if change == "status":
                    response["after"]["checks"][4]["status"] = "needs_source_review"
                    response["after"]["checks"][4]["active_evidence"][0]["review_status"] = "pending"
                else:
                    response["after"]["target_subgroup"] = "Adults unable to travel to study sites"
                self.assertEqual(response["after"]["assessment_id"], "framework-for-syngap1")
                brief = build_collaboration_brief(response, explanation=explanation)
                self.assertEqual(brief["generation_mode"], "none")
                self.assertEqual(brief["draft_origin"], "deterministic_template")
                self.assertIn("different assessment state", brief["provenance"]["ai_rejection_reason"])
                self.assertNotEqual(brief["provenance"]["assessment_sha256"], explanation["provenance"]["assessment_sha256"])

    def test_generated_draft_requires_assessment_fingerprint(self):
        explanation = validated_explanation()
        explanation.pop("provenance")
        brief = build_collaboration_brief(fixture(), explanation=explanation)
        self.assertEqual(brief["generation_mode"], "none")
        self.assertIn("fingerprint", brief["provenance"]["ai_rejection_reason"])

    def test_unvalidated_or_stale_ai_prose_uses_honest_deterministic_fallback(self):
        cases = []
        unvalidated = validated_explanation()
        unvalidated.pop("validation")
        cases.append((fixture(), unvalidated))
        withdrawn = fixture("assessment-syngap1-withdrawn.json")
        cases.append((withdrawn, validated_explanation("cached", assessment=withdrawn["after"])))
        unlisted_url = validated_explanation()
        unlisted_url["draft_message"] += " See https://unlisted.example.org/claim."
        cases.append((fixture(), unlisted_url))
        for response, explanation in cases:
            with self.subTest(explanation=explanation):
                brief = build_collaboration_brief(response, explanation=explanation)
                self.assertEqual(brief["generation_mode"], "none")
                self.assertEqual(brief["draft_origin"], "deterministic_template")
                self.assertIsNotNone(brief["provenance"]["ai_rejection_reason"])
                self.assertNotEqual(brief["draft_message"], explanation["draft_message"])

    def test_validated_ai_unknown_source_still_fails_reference_validation(self):
        explanation = validated_explanation()
        explanation["cited_source_ids"] = ["unknown-source"]
        with self.assertRaisesRegex(ValueError, "Unknown source"):
            build_collaboration_brief(fixture(), explanation=explanation)

    def test_current_state_inconsistent_with_withdrawal_is_rejected(self):
        response = fixture()
        response["after"]["withdrawn_sources"] = [ANCHOR]
        with self.assertRaisesRegex(ValueError, "withdrawn source"):
            build_collaboration_brief(response)

    def test_documented_negative_check_remains_negative_in_proposal(self):
        response = fixture()
        row = response["after"]["checks"][3]
        row.update(status="refuted", refuting_sources=[ANCHOR],
                   active_evidence=[{"source_id": ANCHOR, "review_status": "source_checked", "polarity": "refute",
                                     "rationale": "Synthetic test: the recorded requirement is not met."}])
        response["after"]["outcome"] = "not_supported_for_stated_use"
        brief = build_collaboration_brief(response)
        self.assertIn("Recorded checks do not support the stated use", brief["draft_message"])
        self.assertIn("alternative resource", brief["draft_message"])
        self.assertIn("— refuted (required)", brief["text_export"])

    def test_scoped_proposal_and_differences_are_not_inferred(self):
        response = fixture()
        proposal = {"description": "Assess remote follow-up feasibility", "subgroup": "Adults with limited travel capacity"}
        response["after"]["proposed_use"] = proposal
        response["after"]["documented_differences"] = [{"text": "Synthetic recorded difference", "source_ids": [ALIAS], "review_status": "source_checked"}]
        brief = build_collaboration_brief(response)
        self.assertEqual(brief["proposed_use"], proposal)
        self.assertIn("Subgroup: Adults with limited travel capacity", brief["text_export"])
        self.assertEqual(brief["documented_differences"][0]["source_ids"], [ANCHOR])
        response = fixture("assessment-syngap1-withdrawn.json")
        response["after"]["documented_differences"] = [{"text": "Synthetic recorded difference", "source_ids": [ALIAS], "review_status": "source_checked"}]
        brief = build_collaboration_brief(response)
        self.assertEqual(brief["documented_differences"], [])
        self.assertEqual(len(brief["excluded_differences"]), 1)
        self.assertNotIn("Synthetic recorded difference", brief["text_export"])


if __name__ == "__main__":
    unittest.main()
