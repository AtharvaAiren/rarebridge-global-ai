"""Each test breaks one rule and expects the validator to reject the overlay.
Run: python3 -m unittest curation/test_validate_overlay.py -v   (from repo root)"""
import copy, json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
BASE = json.loads((ROOT / "curation/atlas-overlay.json").read_text())

def validate(overlay):
    with tempfile.TemporaryDirectory(prefix="rarebridge-validator-") as directory:
        path = Path(directory) / "overlay.json"
        path.write_text(json.dumps(overlay))
        original_bytes = path.read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "curation/validate_overlay.py"), "--overlay", str(path)],
                                capture_output=True, text=True)
        if path.read_bytes() != original_bytes:
            raise AssertionError("Validation must not rewrite its input or source-review statuses")
        return result

class OverlayRules(unittest.TestCase):
    def broken(self, mutate, expected):
        o = copy.deepcopy(BASE); mutate(o); r = validate(o)
        self.assertEqual(r.returncode, 1, r.stdout); self.assertIn(expected, r.stdout)
    def test_shipped_overlay_is_valid(self):
        self.assertEqual(validate(BASE).returncode, 0)
    def test_dangling_edge(self):
        self.broken(lambda o: o["edges"][0].update(target="nope:1"), "is not a node")
    def test_numeric_confidence(self):
        self.broken(lambda o: o["edges"][0].update(confidence=0.9), "numeric confidence")
    def test_reused_assessment_id(self):
        self.broken(lambda o: o["assessment_bundles"][0].update(id="framework-for-syngap1"), "reuses a base")
    def test_wrong_target_scope(self):
        self.broken(lambda o: o["assessment_bundles"][1]["target_disease"].update(id="MONDO:0012812"), "documented targets")
    def test_animal_as_human(self):
        self.broken(lambda o: o["assessment_bundles"][0]["checks"][0]["evidence"].append(
            {"source_id": "DOI:10.1002/epi.70374", "polarity": "support", "review_status": "pending",
             "rationale": "Knockout mice show release failure.", "evidence_type": "human_observational"}), "animal finding")
    def test_alias_clash(self):
        self.broken(lambda o: o["sources"]["DOI:10.1002/epi.70374"].update(aliases=["PMID:1"]), "defined differently")
    def test_ai_cannot_self_certify(self):
        self.broken(lambda o: o["review_log"][0].update(review_status="source_checked", checked_by="AI"), "signed by a person")
    def test_no_email_as_contact(self):
        self.broken(lambda o: o["contacts"][0].update(url="a@b.org"), "not an email")
    def test_missing_edge_review_log_is_rejected(self):
        target = "edge:overlay:paper-describes-starr"
        self.broken(lambda o: o.update(review_log=[r for r in o["review_log"] if r["claim_or_check_id"] != target]),
                    '"edges": ["' + target)
    def test_missing_node_review_log_is_rejected(self):
        target = "study:prommis"
        self.broken(lambda o: o.update(review_log=[r for r in o["review_log"] if r["claim_or_check_id"] != target]),
                    '"nodes": ["' + target)
    def test_missing_contact_review_log_is_rejected(self):
        target = "researcher:ingo-helbig"
        self.broken(lambda o: o.update(review_log=[r for r in o["review_log"] if r["claim_or_check_id"] != target]),
                    '"contacts": ["' + target)
    def test_shared_contact_node_review_requires_public_route_facet(self):
        def remove_public_route(o):
            for row in o["review_log"]:
                if row["claim_or_check_id"] == "researcher:jillian-mckee" and row.get("prepared_from") == "existing_curation_metadata_only":
                    row["review_facets"] = [facet for facet in row["review_facets"] if facet != "public_route"]
        self.broken(remove_public_route, "Shared contact/node review does not cover role and route")
    def test_shared_contact_node_review_requires_contact_group(self):
        def remove_contact_group(o):
            for row in o["review_log"]:
                if row["claim_or_check_id"] == "team:stanford-synaptopathy" and row.get("prepared_from") == "existing_curation_metadata_only":
                    row["record_groups"] = [group for group in row["record_groups"] if group != "contacts"]
        self.broken(remove_contact_group, "Shared contact/node review does not cover role and route")
    def test_validation_preserves_signed_and_pending_records(self):
        original = copy.deepcopy(BASE)
        self.assertEqual(validate(BASE).returncode, 0)
        self.assertEqual(BASE, original)
        signed = [row for row in BASE["review_log"] if row["review_status"] == "source_checked"]
        self.assertTrue(signed)
        self.assertEqual(signed, [row for row in original["review_log"] if row["review_status"] == "source_checked"])

if __name__ == "__main__":
    unittest.main()
