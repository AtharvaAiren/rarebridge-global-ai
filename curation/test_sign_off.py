"""Sign-off CLI regression tests; every write is to a synthetic temporary copy."""
from datetime import date
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class SignOffTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        source = Path(__file__).parent
        shutil.copy2(source / "sign_off.py", self.folder / "sign_off.py")
        self.original = json.loads((source / "atlas-overlay.json").read_text())
        for name, value in (
            ("atlas-overlay.json", self.original),
            ("source-review-log.json", {"schema_version": self.original["schema_version"], "entries": self.original["review_log"]}),
        ):
            (self.folder / name).write_text(json.dumps(value))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(self.folder / "sign_off.py"), *args], capture_output=True, text=True)

    def test_list_is_read_only_and_includes_new_pending_records(self):
        before = {name: (self.folder / name).read_bytes() for name in ("atlas-overlay.json", "source-review-log.json")}
        result = self.run_cli("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[pending] edge:overlay:paper-describes-starr", result.stdout)
        self.assertIn("[pending] researcher:jillian-mckee", result.stdout)
        self.assertEqual(before, {name: (self.folder / name).read_bytes() for name in before})

    def test_unknown_id_cannot_change_any_signatures_or_files(self):
        before = {name: (self.folder / name).read_bytes() for name in ("atlas-overlay.json", "source-review-log.json")}
        result = self.run_cli("--reviewer", "Synthetic test reviewer", "--ids", "does-not-exist")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no files changed", result.stderr)
        self.assertEqual(before, {name: (self.folder / name).read_bytes() for name in before})

    def test_simulated_signing_dates_selected_rows_and_preserves_other_reviews(self):
        identifier = "researcher:jillian-mckee"
        result = self.run_cli("--reviewer", "Synthetic test reviewer", "--ids", identifier)
        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads((self.folder / "atlas-overlay.json").read_text())
        selected = [row for row in updated["review_log"] if row["claim_or_check_id"] == identifier]
        self.assertTrue(selected)
        for row in selected:
            self.assertEqual(row["review_status"], "source_checked")
            self.assertEqual(row["checked_by"], "Synthetic test reviewer")
            self.assertEqual(row["checked_on"], date.today().isoformat())
        untouched = [row for row in updated["review_log"] if row["claim_or_check_id"] != identifier]
        self.assertEqual(untouched, [row for row in self.original["review_log"] if row["claim_or_check_id"] != identifier])
        for group in ("nodes", "contacts"):
            self.assertEqual(next(item for item in updated[group] if item["id"] == identifier)["review_status"], "source_checked")
        self.assertEqual(updated["assessment_bundles"], self.original["assessment_bundles"])
        self.assertEqual(updated["review_log"], json.loads((self.folder / "source-review-log.json").read_text())["entries"])


if __name__ == "__main__":
    unittest.main()
