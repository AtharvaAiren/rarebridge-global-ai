"""Promote reviewed items from 'pending' to 'source_checked' after a PERSON
has opened the cited source location and agrees with the assertion.

  python3 curation/sign_off.py --list                     # what is waiting
  python3 curation/sign_off.py --reviewer "Saanvi" --ids framework-for-stxbp1/target-observed edge:overlay:helbig-leads-starr
  python3 curation/sign_off.py --reviewer "Saanvi" --all-listed   # only if you checked every listed item

Edits curation/atlas-overlay.json and curation/source-review-log.json in place.
Bundle evidence for a check is promoted only when every log entry for that
check is signed. Run validate_overlay.py afterwards.
"""
import argparse, json
from datetime import date
from pathlib import Path
HERE = Path(__file__).resolve().parent
OV, LOG = HERE / "atlas-overlay.json", HERE / "source-review-log.json"

ap = argparse.ArgumentParser()
ap.add_argument("--list", action="store_true"); ap.add_argument("--reviewer")
ap.add_argument("--ids", nargs="*", default=[]); ap.add_argument("--all-listed", action="store_true")
a = ap.parse_args()
ov = json.loads(OV.read_text())
if a.list:
    for r in ov["review_log"]:
        print(f"[{r['review_status']}] {r['claim_or_check_id']}\n    source: {r['source_id']} @ {r['source_location']}\n"
              f"    claim:  {r['assertion_checked']}\n    caveat: {r['caveat']}\n")
    raise SystemExit
if not a.reviewer or not a.reviewer.strip() or "claude" in a.reviewer.lower() or a.reviewer.strip().upper() == "AI":
    raise SystemExit("--reviewer must be the person who checked the sources")
ids = {r["claim_or_check_id"] for r in ov["review_log"]} if a.all_listed else set(a.ids)
unknown_ids = ids - {r["claim_or_check_id"] for r in ov["review_log"]}
if unknown_ids:
    raise SystemExit("Unknown review IDs; no files changed: " + ", ".join(sorted(unknown_ids)))
if not ids:
    raise SystemExit("Choose --ids or --all-listed; no files changed")
for r in ov["review_log"]:
    if r["claim_or_check_id"] in ids:
        r["review_status"], r["checked_by"] = "source_checked", a.reviewer
        r["checked_on"] = date.today().isoformat()
signed = {}
for r in ov["review_log"]:
    signed.setdefault(r["claim_or_check_id"], []).append(r["review_status"] == "source_checked")
done = {k for k, v in signed.items() if all(v)}
for b in ov["assessment_bundles"]:
    for c in b["checks"]:
        if f"{b['id']}/{c['id']}" in done:
            for e in c["evidence"]: e["review_status"] = "source_checked"
for group in ("edges", "nodes", "contacts"):
    for item in ov[group]:
        if item.get("id") in done:
            item["review_status"] = "source_checked"
            if group == "edges": item["confidence_label"] = "Source checked (narrow factual review; not clinical validation)"
OV.write_text(json.dumps(ov, indent=2, ensure_ascii=False) + "\n")
LOG.write_text(json.dumps({"schema_version": ov["schema_version"], "entries": ov["review_log"]}, indent=2, ensure_ascii=False) + "\n")
print(f"signed {len(ids & set(signed))} log IDs; fully signed now: {len(done)}. Run validate_overlay.py next.")
