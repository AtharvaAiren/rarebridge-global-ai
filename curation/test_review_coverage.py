"""Review-pointer coverage tests; files are written only inside temporary dirs."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from curation.build_overlay import (
    OVERLAY, PAPER, PREPRINT, build_overlay, derive_missing_review_rows,
    validate_review_coverage, write_overlay,
)


class ReviewCoverageTests(unittest.TestCase):
    def setUp(self):
        self.existing = json.loads((Path(__file__).parent / "atlas-overlay.json").read_text())
        # Root applies the append-only repair to the live JSON independently.
        # Restore the historical gap in memory so these tests keep exercising
        # derivation and preserve the original signatures after that repair.
        self.existing["review_log"] = [
            row for row in self.existing["review_log"]
            if row.get("prepared_from") != "existing_curation_metadata_only"
        ]

    def repaired(self, original=None):
        result = deepcopy(original or self.existing)
        result["review_log"].extend(derive_missing_review_rows(result))
        return result

    def test_real_records_all_gain_review_coverage_without_mutating_signatures(self):
        original = deepcopy(self.existing)
        rows = derive_missing_review_rows(self.existing)
        self.assertEqual(self.existing, original)
        result = self.repaired()
        self.assertEqual(result["review_log"][:len(original["review_log"])], original["review_log"])
        for key in ("nodes", "edges", "contacts", "assets", "sources", "assessment_bundles"):
            self.assertEqual(result[key], original[key])
        self.assertEqual(validate_review_coverage(result), {"edges": 25, "nodes": 15, "contacts": 6})
        self.assertTrue(all(row["review_status"] == "pending" for row in rows))
        self.assertTrue(all(row["checked_on"] == "" for row in rows))
        self.assertTrue(all("no human" in row["checked_by"].lower() for row in rows))

    def test_derivation_is_deterministic_and_append_only_idempotent(self):
        self.assertEqual(derive_missing_review_rows(self.existing), derive_missing_review_rows(self.existing))
        self.assertEqual(derive_missing_review_rows(self.repaired()), [])

    def test_omitting_an_edge_review_fails_coverage(self):
        result = self.repaired()
        missing_id = result["edges"][0]["id"]
        result["review_log"] = [row for row in result["review_log"] if row["claim_or_check_id"] != missing_id]
        with self.assertRaisesRegex(ValueError, "Missing review-log coverage"):
            validate_review_coverage(result)

    def test_shared_researcher_rows_cover_identity_authorship_and_public_route(self):
        result = self.repaired()
        for identifier in ("researcher:ingo-helbig", "researcher:jillian-mckee", "team:stanford-synaptopathy"):
            rows = [row for row in result["review_log"] if row["claim_or_check_id"] == identifier]
            self.assertTrue(rows)
            for row in rows:
                self.assertEqual(set(row["record_groups"]), {"nodes", "contacts"})
                self.assertTrue({"node_identity", "contact_role", "public_route"} <= set(row["review_facets"]))
                self.assertIn("Public discovery route", row["assertion_checked"])
                self.assertIn("Recorded collaborator role", row["assertion_checked"])
        bad = deepcopy(result)
        row = next(row for row in bad["review_log"] if row["claim_or_check_id"] == "researcher:jillian-mckee")
        row["review_facets"] = ["node_identity"]
        with self.assertRaisesRegex(ValueError, "role and route"):
            validate_review_coverage(bad)

    def test_duplicate_and_ambiguous_record_ids_are_rejected(self):
        result = self.repaired()
        result["edges"].append(deepcopy(result["edges"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate edges"):
            validate_review_coverage(result)
        result = self.repaired()
        result["contacts"][0]["label"] = "A different organization"
        with self.assertRaisesRegex(ValueError, "Ambiguous shared"):
            validate_review_coverage(result)

    def test_duplicate_review_rows_and_unknown_log_ids_are_rejected(self):
        result = self.repaired()
        result["review_log"].append(deepcopy(result["review_log"][-1]))
        with self.assertRaisesRegex(ValueError, "Duplicate review"):
            validate_review_coverage(result)
        result = self.repaired()
        result["review_log"][-1]["claim_or_check_id"] = "unrecorded:fiction"
        with self.assertRaisesRegex(ValueError, "unknown record ID"):
            validate_review_coverage(result)

    def test_published_claim_binding_keeps_reviewed_preprint_version_separate(self):
        rows = derive_missing_review_rows(self.existing)
        paper_claims = [row for row in rows if row["cited_source_id"] == PAPER and "edges" in row["record_groups"]]
        self.assertTrue(paper_claims)
        for row in paper_claims:
            self.assertEqual(row["source_id"], PREPRINT)
            self.assertIn("published article was not read", row["caveat"])
        self.assertEqual(self.existing["sources"][PREPRINT]["version_of"], PAPER)
        self.assertNotIn(PREPRINT, self.existing["sources"][PAPER]["aliases"])
        bad = self.repaired()
        row = next(row for row in bad["review_log"] if row.get("cited_source_id") == PAPER and "edges" in row.get("record_groups", []))
        row["source_id"] = "WEB:stxbp1-foundation-starr"
        with self.assertRaisesRegex(ValueError, "source-version binding"):
            validate_review_coverage(bad)

    def test_builder_never_promotes_clinical_or_review_status(self):
        overlay = build_overlay()
        self.assertTrue(all(row["review_status"] == "pending" for row in overlay["review_log"]))
        self.assertTrue(all(item["review_status"] == "pending" for group in ("edges", "nodes", "contacts") for item in overlay[group]))
        self.assertEqual(overlay["assessment_bundles"], OVERLAY["assessment_bundles"])

    def test_writer_creates_only_temp_output_and_refuses_signed_overwrites(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "new-draft"
            result = write_overlay(path)
            self.assertTrue((path / "atlas-overlay.json").is_file())
            self.assertTrue((path / "source-review-log.json").is_file())
            self.assertEqual(len(json.loads((path / "source-review-log.json").read_text())["entries"]), len(result["review_log"]))
            result["review_log"][0].update(review_status="source_checked", checked_by="Existing person", checked_on="2026-10-04")
            target = path / "atlas-overlay.json"
            target.write_text(json.dumps(result))
            before = {file.name: file.read_bytes() for file in path.iterdir()}
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite signed"):
                write_overlay(path)
            self.assertEqual({file.name: file.read_bytes() for file in path.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
