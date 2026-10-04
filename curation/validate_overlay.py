"""Validate curation/atlas-overlay.json: schema plus semantic rules.

Run from the repository root:
    pip install -r curation/requirements.txt
    python3 curation/validate_overlay.py
Exit code 0 = valid. Errors stop integration; warnings are for the reviewer.
"""

import argparse
import json
import re
import sys
from pathlib import Path

if __package__:
    from .build_overlay import validate_review_coverage
else:
    from build_overlay import validate_review_coverage

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_CANDIDATES = ["handoffs/contracts/overlay.schema.json", "contracts/overlay.schema.json",
                     "curation/overlay.schema.json"]
HUMAN_TYPES = {"human_observational"}
ANIMAL_WORDS = re.compile(r"\b(mouse|mice|murine|rat|rats|zebrafish|drosophila|knockout|knock-in)\b", re.I)
FORBIDDEN_STATUS_WORDS = re.compile(r"\b(approved|validated for use|guaranteed|recruiting now)\b", re.I)
BASE_ASSESSMENT_IDS = {"framework-for-syngap1", "framework-for-scn2a"}


def find_schema(arg):
    if arg:
        return Path(arg)
    for rel in SCHEMA_CANDIDATES:
        if (ROOT / rel).exists():
            return ROOT / rel
    sys.exit("overlay schema not found; pass --schema")


def alias_map(source_dicts, errors, where):
    """Map every source ID and alias to one canonical ID; flag clashes."""
    aliases = {}
    for sources in source_dicts:
        for sid, src in sources.items():
            if not src.get("url"):
                errors.append(f"{where}: source {sid} has no URL")
            for alias in [sid, *src.get("aliases", [])]:
                if alias in aliases and aliases[alias] != sid:
                    errors.append(f"{where}: alias {alias} maps to both {aliases[alias]} and {sid}")
                aliases[alias] = sid
    return aliases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlay", default=str(ROOT / "curation/atlas-overlay.json"))
    ap.add_argument("--schema")
    ap.add_argument("--graph", default=str(ROOT / "rarebridge/data/graph.json"))
    ap.add_argument("--base-bundles", nargs="*", default=None)
    args = ap.parse_args()

    errors, warnings = [], []
    overlay = json.loads(Path(args.overlay).read_text())

    # 1. JSON schema
    try:
        import jsonschema
        schema = json.loads(find_schema(args.schema).read_text())
        for err in jsonschema.Draft202012Validator(schema).iter_errors(overlay):
            errors.append(f"schema: {'/'.join(map(str, err.path))}: {err.message}")
    except ImportError:
        errors.append("jsonschema not installed: pip install -r curation/requirements.txt")

    # 2. base data
    graph = json.loads(Path(args.graph).read_text())
    base_nodes = {n["id"]: n for n in graph["nodes"]}
    base_edges = {e["id"] for e in graph["edges"]}
    bundle_paths = args.base_bundles or sorted(str(p) for p in (ROOT / "rarebridge/data").glob("assessment-*.json"))
    base_bundles = [json.loads(Path(p).read_text()) for p in bundle_paths]
    disease_ids = {nid for nid, n in base_nodes.items() if n["type"] == "disease"}

    # 3. sources and aliases across base bundles + overlay
    aliases = alias_map([b["sources"] for b in base_bundles] + [overlay["sources"]], errors, "sources")
    for b in base_bundles:
        for sid, src in b["sources"].items():
            mine = overlay["sources"].get(sid)
            if mine and (mine["url"], sorted(mine["aliases"])) != (src["url"], sorted(src["aliases"])):
                errors.append(f"source {sid} defined differently in overlay and base bundle {b['id']}")

    def resolve(sid, where):
        if sid not in aliases:
            errors.append(f"{where}: unknown source {sid}")

    # 4. nodes: collisions
    overlay_nodes = {}
    for n in overlay["nodes"]:
        if n["id"] in overlay_nodes:
            errors.append(f"duplicate overlay node {n['id']}")
        overlay_nodes[n["id"]] = n
        if n["id"] in base_nodes and base_nodes[n["id"]]["type"] != n["type"]:
            errors.append(f"node {n['id']} collides with base node of type {base_nodes[n['id']]['type']}")
    all_nodes = {**base_nodes, **overlay_nodes}

    # 5. edges
    seen = set()
    for e in overlay["edges"]:
        where = f"edge {e['id']}"
        if e["id"] in seen or e["id"] in base_edges:
            errors.append(f"{where}: duplicate edge ID")
        seen.add(e["id"])
        for end in ("source", "target"):
            if e[end] not in all_nodes:
                errors.append(f"{where}: {end} {e[end]} is not a node in base+overlay")
        if not e["source_ids"]:
            errors.append(f"{where}: no source_ids")
        for sid in e["source_ids"]:
            resolve(sid, where)
        for key, value in e.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool) and re.search("conf|prob|score", key):
                errors.append(f"{where}: numeric {key} is not allowed (qualitative labels only)")
        if e["review_status"] == "pending" and "pending" not in e["confidence_label"].lower():
            errors.append(f"{where}: pending edge must carry a pending confidence label")
        if e["claim_origin"] == "inferred" and "not" not in e["explanation"].lower():
            warnings.append(f"{where}: inferred edge explanation should say what it does NOT establish")

    # 6. assets and contacts
    asset_ids = set()
    for a in overlay["assets"]:
        asset_ids.add(a["id"])
        if not a.get("source_ids"):
            errors.append(f"asset {a['id']}: no source")
        for sid in a.get("source_ids", []):
            resolve(sid, f"asset {a['id']}")
        for did in a.get("target_disease_ids", []):
            if did not in disease_ids:
                errors.append(f"asset {a['id']}: unknown disease {did}")
        if a["id"] not in all_nodes:
            errors.append(f"asset {a['id']}: missing graph node")
    for c in overlay["contacts"]:
        for sid in c["source_ids"]:
            resolve(sid, f"contact {c['id']}")
        if "@" in c["url"]:
            errors.append(f"contact {c['id']}: store a public page URL, not an email address")

    # 7. bundles: engine + scoping
    sys.path.insert(0, str(ROOT / "rarebridge"))
    from assessment import assess, validate  # shared, read-only engine
    asset_targets = {a["id"]: set(a.get("target_disease_ids", [])) for a in overlay["assets"]}
    for b in overlay["assessment_bundles"]:
        where = f"bundle {b['id']}"
        if b["id"] in BASE_ASSESSMENT_IDS:
            errors.append(f"{where}: reuses a base assessment ID")
        if b["target_disease"]["id"] not in disease_ids:
            errors.append(f"{where}: unknown target disease")
        targets = asset_targets.get(b["asset"]["id"])
        if targets is not None and b["target_disease"]["id"] not in targets:
            errors.append(f"{where}: target disease is not in the asset's documented targets")
        for check in b["checks"]:
            for item in check.get("evidence", []):
                if item.get("evidence_type") in HUMAN_TYPES and ANIMAL_WORDS.search(item["rationale"]):
                    errors.append(f"{where}/{check['id']}: animal finding labelled as human evidence")
        try:
            validate(b)
            result = assess(b)
        except ValueError as exc:
            errors.append(f"{where}: engine rejected bundle: {exc}")
            continue
        logged = {r["claim_or_check_id"] for r in overlay["review_log"]}
        for check in b["checks"]:
            if check.get("evidence") and f"{b['id']}/{check['id']}" not in logged:
                errors.append(f"{where}/{check['id']}: evidence has no review-log entry")
        print(f"  {b['id']}: outcome={result['outcome']} | " +
              ", ".join(f"{r['id']}={r['status']}" for r in result["checks"]))

    # 8. review log: AI cannot self-certify
    for r in overlay["review_log"]:
        resolve(r["source_id"], f"review_log {r['claim_or_check_id']}")
        if r["review_status"] == "source_checked" and re.search(r"\b(AI|Claude|model|GPT)\b", r["checked_by"]):
            errors.append(f"review_log {r['claim_or_check_id']}: source_checked must be signed by a person")

    # Coverage is separate from source truth or human approval. The helper
    # accepts historical rows as recorded and checks new joint node/contact
    # pointers without rewriting signatures or changing evidence statuses.
    try:
        validate_review_coverage(overlay)
    except ValueError as exc:
        errors.append(f"review-log coverage: {exc}")

    # 9. wording guard
    for text in json.dumps(overlay).split('"'):
        if FORBIDDEN_STATUS_WORDS.search(text):
            warnings.append(f"wording check: '{text[:80]}'")

    counts = {k: len(overlay[k]) for k in ("nodes", "edges", "assets", "contacts", "assessment_bundles", "review_log")}
    print("counts:", counts)
    pending = sum(1 for e in overlay["edges"] if e["review_status"] == "pending")
    print(f"review: {pending}/{len(overlay['edges'])} edges pending human source review")
    for w in warnings:
        print("WARNING:", w)
    for e in errors:
        print("ERROR:", e)
    print("VALID" if not errors else f"INVALID ({len(errors)} errors)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
