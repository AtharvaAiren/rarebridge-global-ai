"""An extracted relationship is a pending preview, never a curated graph merge."""

import hashlib


def build_graph_preview(extraction):
    if extraction.get("generation_mode") not in {"live", "cached"}:
        raise ValueError("Preview needs an actual live or cached extraction")
    if extraction.get("validation", {}).get("status") != "passed":
        raise ValueError("Preview needs a structurally validated extraction")
    source = extraction["source"]
    source_id = extraction["source_id"]
    nodes = {item["id"]: dict(item, review_status="pending") for item in extraction["entities"]}
    nodes[source_id] = {
        "id": source_id, "type": "publication", "label": source["title"],
        "url": source["url"], "review_status": "pending",
    }
    edges = []
    for claim in extraction["claims"]:
        if claim.get("review_status") != "pending" or claim["source_id"] != source_id:
            raise ValueError("Preview claim has invalid source or review state")
        if claim["subject_id"] not in nodes or claim["object_id"] not in nodes:
            raise ValueError("Preview claim references an absent entity")
        key = source_id + "\x1f" + claim["id"]
        edges.append({
            "id": "ai-preview:" + hashlib.sha256(key.encode()).hexdigest()[:20],
            "source": claim["subject_id"], "target": claim["object_id"],
            "relation": claim["relation"], "source_ids": [source_id],
            "review_status": "pending", "claim_origin": "imported",
            "confidence_label": "AI-extracted — source review pending",
            "explanation": claim["rationale"], "source_excerpt": claim["source_excerpt"],
            "source_location": claim["source_location"],
            "evidence_type": claim["evidence_type"], "qualifiers": claim["qualifiers"],
            "provenance": {
                "source_url": source["url"],
                "source_sha256": extraction["provenance"]["source_sha256"],
                "response_id": extraction["provenance"]["response_id"],
                "extracted_at": extraction["provenance"]["generated_at"],
                "source_origin": "caller_supplied_excerpt",
            },
        })
    return {
        "schema_version": "rarebridge.handoff.v1", "nodes": list(nodes.values()),
        "edges": edges, "sources": {source_id: {
            "title": source["title"], "url": source["url"], "aliases": [],
            "published_on": source.get("published_on"), "source_kind": "supplied_source_excerpt",
            "note": "Extracted source excerpt; all generated relationships await factual review.",
        }},
        "coverage": {"scope_note": "Preview of one supplied source; not merged into the reviewed atlas.",
                     "truncated": False, "total_nodes": len(nodes), "total_edges": len(edges)},
        "data_origin": "ai_pending_preview", "generation_mode": extraction["generation_mode"],
    }
