"""Standalone lead-lane CLI; does not depend on the teammates' API or UI."""

import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys

from rarebridge.assessment import assess, compare_withdrawal
from .brief import build_collaboration_brief
from .config import WORKSPACE_ROOT, load_config
from .preview import build_graph_preview
from .service import AIService, AIServiceError, capabilities


def _read_json(path):
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError("Input JSON exceeds the size limit")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, value):
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


def assessment_response(bundle, withdrawn=()):
    comparison = compare_withdrawal(bundle, withdrawn)
    return {
        "schema_version": "rarebridge.handoff.v1", **comparison,
        "sources": bundle["sources"],
        "coverage": bundle.get("coverage", "This is a curated, limited assessment source pack."),
        "contacts": bundle.get("contacts", []),
        "explanation": {"generation_mode": "none", "text": None, "cited_source_ids": [], "model": None},
        "data_origin": "curated",
    }


def _service(mode):
    config = load_config()
    return AIService(replace(config, mode=mode) if mode else config)


async def _smoke(service, output_dir):
    """Three genuine requests or exact genuine cached replays; never fixtures."""
    directory = Path(output_dir)
    source = _read_json(WORKSPACE_ROOT / "rarebridge/ai/samples/sfari-access-source.json")
    bundle = _read_json(WORKSPACE_ROOT / "rarebridge/data/assessment-syngap1.json")
    extraction = await service.extract_source(source)
    if not extraction["claims"]:
        raise ValueError("Extraction produced no claims; inspect the narrow source before recording the demo")
    preview = build_graph_preview(extraction)
    response = assessment_response(bundle)
    explanation = await service.explain_assessment(response["after"], response["sources"])
    response["explanation"] = explanation
    brief = build_collaboration_brief(response)
    withdrawn = assessment_response(bundle, ["PMID:42446932"])
    withdrawn_explanation = await service.explain_assessment(withdrawn["after"], withdrawn["sources"])
    withdrawn["explanation"] = withdrawn_explanation
    withdrawn_brief = build_collaboration_brief(withdrawn)
    if (brief["generation_mode"] != explanation["generation_mode"]
            or withdrawn_brief["generation_mode"] != withdrawn_explanation["generation_mode"]):
        raise ValueError("Smoke brief rejected its current-state AI draft; inspect the validation and provenance")
    excluded = set(withdrawn["after"]["withdrawn_sources"])
    if excluded & set(withdrawn_explanation["cited_source_ids"]):
        raise ValueError("Withdrawn explanation cited an excluded source")
    if not withdrawn["changed_checks"] or any(edge["review_status"] != "pending" for edge in preview["edges"]):
        raise ValueError("Smoke checks failed for withdrawal or pending extraction")
    artifacts = {
        "extraction.json": extraction, "graph-preview.json": preview,
        "explanation.json": explanation, "assessment-response.json": response,
        "brief.json": brief, "withdrawn-explanation.json": withdrawn_explanation,
        "withdrawn-assessment-response.json": withdrawn, "withdrawn-brief.json": withdrawn_brief,
    }
    for filename, result in artifacts.items():
        _write_json(directory / filename, result)
    (directory / "brief.txt").write_text(brief["text_export"] + "\n", encoding="utf-8")
    (directory / "withdrawn-brief.txt").write_text(withdrawn_brief["text_export"] + "\n", encoding="utf-8")
    summary = {
        "status": "passed", "kind": "actual_provider_or_matching_genuine_cache",
        "provider": service.config.provider, "requested_model": service.config.model,
        "generation_modes": {
            "extraction": extraction["generation_mode"], "explanation": explanation["generation_mode"],
            "withdrawn_explanation": withdrawn_explanation["generation_mode"],
        },
        "claim_count": len(extraction["claims"]), "preview_edges": len(preview["edges"]),
        "changed_check_count": len(withdrawn["changed_checks"]),
        "overall_before": response["after"]["outcome"], "overall_after": withdrawn["after"]["outcome"],
        "withdrawn_source_ids": sorted(excluded), "output_dir": str(directory),
        "response_ids": [value["provenance"]["response_id"] for value in (extraction, explanation, withdrawn_explanation)],
        "scope": "AI-lane extraction, explanation, withdrawal and brief composition; API/UI integration remains separate.",
    }
    _write_json(directory / "run-summary.json", summary)
    return summary


def _parser():
    parser = argparse.ArgumentParser(description="RareBridge AI helpers and reviewable collaboration briefs")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report configuration/capabilities without network calls")
    extract = commands.add_parser("extract", help="Extract pending candidate facts from a supplied public source")
    extract.add_argument("--source", required=True)
    extract.add_argument("--output")
    extract.add_argument("--preview", help="Optional pending graph-preview JSON output")
    explain = commands.add_parser("explain", help="Explain an existing curated assessment")
    explain.add_argument("--bundle", required=True)
    explain.add_argument("--withdraw", action="append", default=[])
    explain.add_argument("--output")
    brief = commands.add_parser("brief", help="Compose a source-backed brief without requiring a model")
    inputs = brief.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--bundle")
    inputs.add_argument("--response", help="Use the exact current API assessment response")
    brief.add_argument("--withdraw", action="append", default=[])
    brief.add_argument("--with-ai", action="store_true")
    brief.add_argument("--output")
    brief.add_argument("--text-output")
    smoke = commands.add_parser("smoke", help="Run extraction, explanation, withdrawal and brief checks using actual AI")
    smoke.add_argument("--output-dir", default=str(WORKSPACE_ROOT / "rarebridge/ai/runs/live-smoke"))
    for command in (extract, explain, brief, smoke):
        command.add_argument("--mode", choices=("auto", "live", "cache", "off"))
    return parser


async def _run(args):
    if args.command == "doctor":
        _write_json(None, {"python": sys.version.split()[0], "config": load_config().diagnostics(), "capabilities": capabilities()})
        return
    if args.command == "brief":
        if args.response and args.withdraw:
            raise ValueError("Use a response already evaluated with the requested withdrawal; do not modify its recorded results")
        response = _read_json(args.response) if args.response else assessment_response(_read_json(args.bundle), args.withdraw)
        if args.with_ai:
            response["explanation"] = await _service(args.mode).explain_assessment(response["after"], response["sources"])
        result = build_collaboration_brief(response)
        _write_json(args.output, result)
        if args.text_output:
            target = Path(args.text_output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(result["text_export"] + "\n", encoding="utf-8")
        return
    service = _service(args.mode)
    if args.command == "extract":
        result = await service.extract_source(_read_json(args.source))
        _write_json(args.output, result)
        if args.preview:
            _write_json(args.preview, build_graph_preview(result))
    elif args.command == "explain":
        bundle = _read_json(args.bundle)
        result = await service.explain_assessment(assess(bundle, args.withdraw), bundle["sources"])
        _write_json(args.output, result)
    elif args.command == "smoke":
        _write_json(None, await _smoke(service, args.output_dir))


def main():
    args = _parser().parse_args()
    try:
        asyncio.run(_run(args))
    except AIServiceError as exc:
        print(json.dumps(exc.to_dict()), file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # Configuration/files are local; do not include provider or secret data.
        error = {"schema_version": "rarebridge.handoff.v1", "error": {
            "code": "invalid_input", "message": "Check input files, arguments and local configuration.", "details": [],
        }}
        print(json.dumps(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
