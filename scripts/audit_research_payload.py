"""Inspect the fixed public-data discovery payload without credentials or network."""

import json
from pathlib import Path
from urllib.parse import urlsplit

from rarebridge.ai.research import discovery_context
from rarebridge.services.registry import Registry


def main():
    root = Path(__file__).resolve().parents[1]
    context = discovery_context(Registry(), "MONDO:0012960")
    manifest = json.loads((root / "rarebridge/data/source-manifest.json").read_text())
    public_hosts = {"github.com", "doi.org", "www.stxbp1disorders.org", "curesyngap1.org",
                    "www.stanfordchildrens.org", "globalgenes.org"}
    for source in context["sources"].values():
        url = urlsplit(source["url"])
        assert url.scheme == "https" and url.hostname in public_hosts
    assert manifest["upstream"] == "https://github.com/monarch-initiative/dismech"
    assert manifest["content_license"] == "CC-BY-4.0"
    assert set(context) == {"query_disease_id", "goal_id", "diseases", "nodes", "edges",
                            "sources", "known_routes", "coverage_note"}
    for node in context["nodes"]:
        assert set(node) == {"id", "type", "label", "description", "review_status"}
        assert node["type"] not in {"patient", "account", "profile"}
    report = {
        "passed": True,
        "provider_destination": "https://api.anthropic.com/v1/messages",
        "purpose": "The user requested a trained-model research scout and patient research assistant using their configured Claude API credits.",
        "data_origins": [manifest["upstream"], "curation/atlas-overlay.json: public papers and institutional/program pages"],
        "public_snapshot": manifest["snapshot_commit"], "license": manifest["content_license"],
        "sources": {sid: source["url"] for sid, source in context["sources"].items()},
        "payload_chars": len(json.dumps(context, separators=(",", ":"))),
        "input_scope": "Disease-level public records; no patient records, local account profiles, lab chats, private documents or .env contents.",
        "verification_questions": ["What should we ask a researcher next?", "What changes if a paper is hidden?"],
        "limits": "This checks payload provenance and field selection, not biomedical correctness. Source claims retain their original review states.",
    }
    (root / "submission/RESEARCH_PAYLOAD_AUDIT.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
