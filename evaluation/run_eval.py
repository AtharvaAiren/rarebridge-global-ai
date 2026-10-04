"""Score answers against the frozen held-out cases, or audit the rule engine.

  python3 evaluation/run_eval.py --engine-audit
      Runs the assessment engine directly on the bundles named in the cases.
      Labelled ENGINE AUDIT: it checks our rules, not the app or the science.
  python3 evaluation/run_eval.py --template > evaluation/answers-asset_check.json
      Writes a blank answers file to fill from real app runs.
  python3 evaluation/run_eval.py --answers evaluation/answers-asset_check.json [--manual manual.json]
      Scores filled answers. Results are written ONLY from real runs.
"""
import argparse, copy, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rarebridge"))
CASES = json.loads((ROOT / "evaluation/heldout-cases.json").read_text())["cases"]


def aliases():
    """Alias -> canonical source ID, from the overlay and base bundles."""
    table = {}
    srcs = [json.loads(p.read_text())["sources"] for p in (ROOT / "rarebridge/data").glob("assessment-*.json")]
    ov = ROOT / "curation/atlas-overlay.json"
    if ov.exists():
        srcs.append(json.loads(ov.read_text())["sources"])
    for s in srcs:
        for sid, src in s.items():
            for a in [sid, *src.get("aliases", [])]:
                table[a] = sid
    return table


def load_bundle(ref, state):
    if ref.startswith("overlay:"):
        ov = json.loads((ROOT / "curation/atlas-overlay.json").read_text())
        bundle = next(b for b in ov["assessment_bundles"] if b["id"] == ref.split(":", 1)[1])
    else:
        bundle = json.loads((ROOT / ref).read_text())
    bundle = copy.deepcopy(bundle)
    # "as_shipped" means the original pending evidence-lane draft, even after
    # real reviewers sign the live overlay. Base bundles retain their own state.
    draft_state = state == "pending" or (state == "as_shipped" and ref.startswith("overlay:"))
    if draft_state or state == "after_signoff":  # in-memory simulation only; files are not changed
        for c in bundle["checks"]:
            for e in c["evidence"]:
                e["review_status"] = "source_checked" if state == "after_signoff" else "pending"
    return bundle


def engine_audit():
    from assessment import assess, compare_withdrawal
    rows, passed = [], 0
    for case in CASES:
        spec = case.get("engine_audit")
        if not spec:
            continue
        b = load_bundle(spec["bundle"], spec["review_state"])
        res = compare_withdrawal(b, spec["withdraw"])["after"] if spec.get("withdraw") else assess(b)
        got = {r["id"]: r["status"] for r in res["checks"]}
        ok = res["outcome"] == spec["expect_outcome"] and all(got.get(k) == v for k, v in spec["expect_checks"].items())
        if spec.get("expect_withdrawn"):
            ok = ok and res["withdrawn_sources"] == spec["expect_withdrawn"]
        passed += ok
        rows.append(f"{case['id']} [{spec['review_state']}] {'PASS' if ok else 'FAIL'}: outcome={res['outcome']} "
                    + ", ".join(f"{k}={got.get(k)}" for k in spec["expect_checks"]))
    print("ENGINE AUDIT (rules only; not app output, not clinical validation)")
    print("\n".join(rows))
    print(f"passed {passed}/{len(rows)} engine-auditable cases ({len(CASES) - len(rows)} cases need app answers)")
    return 0 if passed == len(rows) else 1


def template():
    return [{"case_id": c["id"], "system": "asset_check|baseline", "outcome": None, "followup_check_ids": [],
             "cited_source_ids": [], "text": "", "run_by": "", "run_on": ""} for c in CASES]


NEGATION = re.compile(r"\b(not|no|never|isn't|doesn't|does not|cannot|can't|without)\b[^.]{0,40}$")


def asserted(phrase, text):
    """True if phrase appears and is not negated just before it (simple heuristic;
    flagged rows still deserve a human look)."""
    for m in re.finditer(re.escape(phrase.lower()), text):
        if not NEGATION.search(text[max(0, m.start() - 60):m.start()]):
            return True
    return False


def score(answers, manual):
    amap, by_case = aliases(), {c["id"]: c for c in CASES}
    out = []
    for a in answers:
        exp = by_case[a["case_id"]]["expected"]
        cited = {amap.get(s, s) for s in a.get("cited_source_ids", [])}
        need = {amap.get(s, s) for s in exp["must_cite_any"]}
        text = a.get("text", "").lower()
        bad = [p for p in exp["must_not_assert"] if asserted(p, text)]
        if a.get("outcome") in exp["forbidden_outcomes"]:
            bad.append(f"forbidden outcome {a['outcome']}")
        gaps = exp["required_gap_check_ids"]
        m = manual.get(a["case_id"], {})
        out.append({
            "case_id": a["case_id"], "system": a.get("system"),
            "source_accuracy": (1 if (not need or cited & need) else 0) + m.get("source_location_ok", 0),
            "unsupported_positive_assertions": len(bad), "unsupported_details": bad,
            "required_gaps_detected": (sum(g in a.get("followup_check_ids", []) for g in gaps) / len(gaps)) if gaps else None,
            "correct_scoping": (1 if a.get("outcome") in exp["allowed_outcomes"] else 0) if exp["allowed_outcomes"] else None,
            "next_action_usefulness": m.get("next_action_usefulness"),
        })
    n = len(out)
    print(json.dumps({"n_answers": n, "note": "Tiny pilot; report denominators.", "rows": out}, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-audit", action="store_true"); ap.add_argument("--template", action="store_true")
    ap.add_argument("--answers"); ap.add_argument("--manual")
    a = ap.parse_args()
    if a.engine_audit:
        sys.exit(engine_audit())
    if a.template:
        print(json.dumps(template(), indent=2)); sys.exit()
    if a.answers:
        man = json.loads(Path(a.manual).read_text()) if a.manual else {}
        score(json.loads(Path(a.answers).read_text()), man); sys.exit()
    ap.print_help()
