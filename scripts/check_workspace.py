#!/usr/bin/env python3
"""Read-only, offline workspace checks. No project imports or model requests."""

import argparse
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _load(path, failures):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        failures.append(f"Cannot read JSON {path.name}: {type(exc).__name__}")
        return None


def _command_version(command):
    binary = shutil.which(command)
    if not binary:
        return {"available": False, "version": None}
    try:
        result = subprocess.run([binary, "--version"], capture_output=True,
                                text=True, timeout=5, check=False)
        match = re.search(r"\bv?(\d+\.\d+(?:\.\d+)?)\b", result.stdout)
        return {"available": result.returncode == 0,
                "version": match.group(1) if match else None}
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "version": None}


def _dotenv_keys(path):
    """Read known configuration only; never execute .env or expose its values."""
    accepted = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_WORKSPACE_ID",
                "RAREBRIDGE_AI_PROVIDER", "RAREBRIDGE_AI_MODEL", "RAREBRIDGE_AI_MODE",
                "RAREBRIDGE_AI_CACHE_DIR", "RAREBRIDGE_AI_TIMEOUT_SECONDS",
                "RAREBRIDGE_AI_MAX_OUTPUT_TOKENS"}
    values = {}
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            return values
        for line in lines:
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if key not in accepted:
                continue
            if value.startswith(("\"", "'")) and value[-1:] == value[:1]:
                value = value[1:-1]
            else:
                value = value.split(" #", 1)[0].rstrip()
            values[key] = value
    # Match service behavior: even an explicitly empty exported value wins.
    values.update({key: os.environ[key] for key in accepted if key in os.environ})
    return values


def check_workspace(root):
    failures, warnings = [], []
    data = root / "rarebridge" / "data"
    graph = _load(data / "graph.json", failures)
    manifest = _load(data / "source-manifest.json", failures)
    disorders = _load(data / "disorders.json", failures)
    counts = {"nodes": 0, "edges": 0, "diseases": 0, "assessment_bundles": 0}
    disease_ids = set()

    if graph is not None and not isinstance(graph, dict):
        failures.append("Graph must be an object")
    if isinstance(graph, dict):
        nodes, edges = graph.get("nodes"), graph.get("edges")
        if not isinstance(nodes, list) or not isinstance(edges, list):
            failures.append("Graph must contain node and edge lists")
        else:
            counts.update(nodes=len(nodes), edges=len(edges))
            ids = [node.get("id") for node in nodes if isinstance(node, dict)]
            if len(ids) != len(nodes) or any(not isinstance(i, str) or not i for i in ids):
                failures.append("Graph contains a node without a valid ID")
            valid_ids = {i for i in ids if isinstance(i, str) and i}
            if len(valid_ids) != len(ids):
                failures.append("Graph contains duplicate or invalid node IDs")
            disease_ids = {n["id"] for n in nodes if isinstance(n, dict)
                           and n.get("type") == "disease" and isinstance(n.get("id"), str)}
            counts["diseases"] = len(disease_ids)
            edge_ids = set()
            for edge in edges:
                if not isinstance(edge, dict):
                    failures.append("Graph contains a non-object edge")
                    continue
                edge_id = edge.get("id")
                if not isinstance(edge_id, str) or not edge_id or edge_id in edge_ids:
                    failures.append("Graph contains a duplicate or invalid edge ID")
                else:
                    edge_ids.add(edge_id)
                if (not isinstance(edge.get("source"), str)
                        or not isinstance(edge.get("target"), str)
                        or edge["source"] not in valid_ids or edge["target"] not in valid_ids):
                    failures.append("Graph contains an edge with an unresolved endpoint")
                provenance = edge.get("provenance")
                if not isinstance(provenance, dict) or not provenance.get("source_url"):
                    failures.append("An imported graph edge is missing source provenance")
                if edge.get("review_status") != "pending":
                    failures.append("An imported graph edge has unexpected review status")

    if manifest is not None and not isinstance(manifest, dict):
        failures.append("Manifest must be an object")
    if isinstance(manifest, dict):
        if not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("snapshot_commit", ""))):
            failures.append("Manifest snapshot_commit is not a full commit ID")
        if manifest.get("content_license") != "CC-BY-4.0" or not manifest.get("attribution"):
            failures.append("Manifest attribution or expected content license is missing")
        entries = manifest.get("files")
        if not isinstance(entries, list) or not entries:
            failures.append("Manifest has no raw source files")
        else:
            for entry in entries:
                if (not isinstance(entry, dict)
                        or not isinstance(entry.get("local_path"), str) or not entry["local_path"]):
                    failures.append("Manifest raw-file entry is incomplete")
                elif not (data / entry["local_path"]).is_file():
                    failures.append("A manifest raw source file is missing")
                elif not entry.get("source_url"):
                    failures.append("A manifest raw source URL is missing")
        if isinstance(graph, dict):
            graph_manifest = graph.get("source_manifest")
            if (not isinstance(graph_manifest, dict)
                    or graph_manifest.get("snapshot_commit") != manifest.get("snapshot_commit")):
                failures.append("Graph and manifest snapshot IDs differ")

    if isinstance(disorders, list):
        try:
            converted_ids = {item["record"]["disease_term"]["term"]["id"] for item in disorders}
            if converted_ids != disease_ids:
                failures.append("Converted disorder IDs do not match graph disease IDs")
        except (KeyError, TypeError):
            failures.append("Converted disorders are missing stable disease IDs")
    elif disorders is not None:
        failures.append("Converted disorders must be a list")

    global_aliases = {}
    paths = sorted(data.glob("assessment-*.json"))
    if not paths:
        failures.append("No foundation assessment bundles found")
    bundle_ids = set()
    for path in paths:
        bundle = _load(path, failures)
        if not isinstance(bundle, dict):
            if bundle is not None:
                failures.append(f"{path.name}: assessment must be an object")
            continue
        counts["assessment_bundles"] += 1
        prefix = path.name + ": "
        bundle_id = bundle.get("id")
        if not isinstance(bundle_id, str) or not bundle_id or bundle_id in bundle_ids:
            failures.append(prefix + "duplicate or invalid assessment ID")
        else:
            bundle_ids.add(bundle_id)
        target = bundle.get("target_disease")
        if (not isinstance(target, dict) or not isinstance(target.get("id"), str)
                or target["id"] not in disease_ids):
            failures.append(prefix + "target disease ID is absent from graph")
        if not bundle.get("goal") or not isinstance(bundle.get("asset"), dict) or not bundle["asset"].get("id"):
            failures.append(prefix + "goal or asset scope is missing")
        sources, checks = bundle.get("sources"), bundle.get("checks")
        aliases = {}
        if not isinstance(sources, dict):
            failures.append(prefix + "sources must be a map")
            sources = {}
        for source_id, source in sources.items():
            if not isinstance(source, dict) or not source.get("url"):
                failures.append(prefix + "source URL missing")
                continue
            alternate = source.get("aliases", [])
            if not isinstance(alternate, list):
                failures.append(prefix + "source aliases must be a list")
                alternate = []
            for alias in [source_id, *alternate]:
                if not isinstance(alias, str) or not alias:
                    failures.append(prefix + "invalid source alias")
                    continue
                if alias in aliases and aliases[alias] != source_id:
                    failures.append(prefix + "source alias maps to multiple publications")
                if alias in global_aliases and global_aliases[alias] != source_id:
                    failures.append(prefix + "source alias disagrees across foundation bundles")
                aliases[alias] = source_id
                global_aliases[alias] = source_id
        if not isinstance(checks, list) or not checks:
            failures.append(prefix + "explicit checks are missing")
            continue
        if not any(isinstance(check, dict) and check.get("required", True) for check in checks):
            failures.append(prefix + "at least one required check is needed")
        check_ids = set()
        for check in checks:
            if not isinstance(check, dict):
                failures.append(prefix + "check must be an object")
                continue
            check_id = check.get("id")
            if not isinstance(check_id, str) or not check_id or check_id in check_ids:
                failures.append(prefix + "duplicate or invalid check ID")
            else:
                check_ids.add(check_id)
            if not check.get("question") or not check.get("next_question"):
                failures.append(prefix + "check scope or next question is missing")
            evidence = check.get("evidence", [])
            if not isinstance(evidence, list):
                failures.append(prefix + "check evidence must be a list")
                continue
            for item in evidence:
                if not isinstance(item, dict):
                    failures.append(prefix + "evidence must be an object")
                elif (not isinstance(item.get("source_id"), str)
                      or item["source_id"] not in aliases
                      or item.get("polarity") not in {"support", "refute", "uncertain"}
                      or item.get("review_status") not in {"pending", "source_checked"}
                      or not item.get("rationale")):
                    failures.append(prefix + "evidence has invalid source, polarity, review status or scope")

    python_ok = sys.version_info >= (3, 10)
    if not python_ok:
        failures.append("Python 3.10 or newer is required")
    node, npm = _command_version("node"), _command_version("npm")
    node_ok = False
    if node["version"]:
        parts = tuple(int(x) for x in node["version"].split("."))
        node_ok = parts >= (22, 12) or (parts[0] == 20 and parts >= (20, 19))
    if not node_ok or not npm["available"]:
        warnings.append("Frontend runtime setup pending: Node 20.19+ in the 20.x line, or 22.12+, plus npm")
    dependencies = {}
    for package in ("fastapi", "uvicorn", "pydantic"):
        try:
            dependencies[package] = {"installed": True, "version": importlib.metadata.version(package)}
        except importlib.metadata.PackageNotFoundError:
            dependencies[package] = {"installed": False, "version": None}
    if not all(value["installed"] for value in dependencies.values()):
        warnings.append("Backend dependency installation pending")

    lane_paths = {
        "backend": [root / "rarebridge" / "api"],
        "frontend": [root / "frontend"],
        "curation": [root / "curation" / "atlas-overlay.json"],
        "evaluation": [root / "evaluation" / "heldout-cases.json"],
        "ai_service": [root / "rarebridge" / "ai" / "service.py"],
    }
    lanes = {name: {"present": all(path.exists() for path in paths),
                    "verification": "not_executed"} for name, paths in lane_paths.items()}
    for name, lane in lanes.items():
        if not lane["present"]:
            warnings.append(f"{name}: teammate/lead artifact not present; integration pending")

    config = _dotenv_keys(root / ".env")
    def credential_configured(name):
        value = config.get(name, "").strip()
        return bool(value) and not any(token in value.lower() for token in
                                      ("your-key", "your_key", "replace", "placeholder", "paste"))

    openai_configured = credential_configured("OPENAI_API_KEY")
    anthropic_configured = credential_configured("ANTHROPIC_API_KEY")
    provider = config.get("RAREBRIDGE_AI_PROVIDER", "openai").strip().lower()
    provider_valid = provider in {"openai", "anthropic"}
    active_key_configured = {"openai": openai_configured,
                             "anthropic": anthropic_configured}.get(provider, False)
    if not provider_valid:
        warnings.append("AI provider configuration invalid; use openai or anthropic")
    mode = config.get("RAREBRIDGE_AI_MODE", "auto").strip().lower()
    valid_mode = mode in {"live", "cache", "auto", "off"}
    if not valid_mode:
        warnings.append("AI mode configuration invalid; check .env locally")
    if not active_key_configured:
        warnings.append("Active AI provider key not configured; genuine live smoke run still pending")
    try:
        timeout_value = float(config.get("RAREBRIDGE_AI_TIMEOUT_SECONDS", "40"))
        timeout_ok = math.isfinite(timeout_value) and 1 <= timeout_value <= 120
    except ValueError:
        timeout_ok = False
    if not timeout_ok:
        warnings.append("AI timeout configuration invalid; check .env locally")
    try:
        tokens_ok = 256 <= int(config.get("RAREBRIDGE_AI_MAX_OUTPUT_TOKENS", "6000")) <= 12000
    except ValueError:
        tokens_ok = False
    if not tokens_ok:
        warnings.append("AI output-token configuration invalid; check .env locally")

    return {
        "check_version": "rarebridge.workspace.v1", "offline": True,
        "foundation": {"status": "pass" if not failures else "fail", "counts": counts,
                       "failures": sorted(set(failures))},
        "runtime": {"python": {"version": ".".join(map(str, sys.version_info[:3])),
                               "supported": python_ok}, "node": dict(node, supported=node_ok),
                    "npm": npm, "backend_dependencies": dependencies},
        "configuration": {"dotenv_present": (root / ".env").is_file(),
                          "ai_provider": provider if provider_valid else "invalid",
                          "ai_provider_valid": provider_valid,
                          "active_provider_key_configured": active_key_configured,
                          "openai_key_configured": openai_configured,
                          "anthropic_key_configured": anthropic_configured,
                          "anthropic_workspace_id_configured": bool(config.get("ANTHROPIC_WORKSPACE_ID", "").strip()),
                          "ai_model_configured": bool(config.get("RAREBRIDGE_AI_MODEL")),
                          "ai_mode_valid": valid_mode, "ai_timeout_valid": timeout_ok,
                          "ai_output_tokens_valid": tokens_ok,
                          "live_request_performed": False},
        "lanes": lanes, "integration": "pending_manual_verification",
        "warnings": sorted(set(warnings)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report")
    parser.add_argument("--root", type=Path, default=ROOT, help="Workspace root (read-only)")
    args = parser.parse_args(argv)
    report = check_workspace(args.root.resolve())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        foundation = report["foundation"]
        print("RareBridge offline workspace check")
        print("Foundation: " + foundation["status"])
        print("Records: " + ", ".join(f"{key}={value}" for key, value in foundation["counts"].items()))
        print("Python: " + report["runtime"]["python"]["version"])
        print("Node/npm available: " + str(report["runtime"]["node"]["available"])
              + "/" + str(report["runtime"]["npm"]["available"]))
        print(".env present: " + str(report["configuration"]["dotenv_present"]))
        print("AI provider: " + report["configuration"]["ai_provider"])
        print("Active provider key configured: " + str(report["configuration"]["active_provider_key_configured"]))
        print("OpenAI key configured: " + str(report["configuration"]["openai_key_configured"]))
        print("Anthropic key configured: " + str(report["configuration"]["anthropic_key_configured"]))
        print("Anthropic workspace ID configured: " + str(report["configuration"]["anthropic_workspace_id_configured"]))
        print("Live API requests performed: False")
        print("Integration: pending manual verification")
        for item in foundation["failures"]:
            print("FAIL: " + item)
        for item in report["warnings"]:
            print("PENDING: " + item)
    return 0 if report["foundation"]["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
