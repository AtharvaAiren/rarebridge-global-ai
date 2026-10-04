"""Convert the pinned disease records into a conservative, inspectable graph.

This is an import, not independent verification. Upstream claims remain pending
review. No shared term creates an asset-transfer or therapeutic-transfer edge.
"""

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def stable_id(prefix, *parts):
    key = "\x1f".join(str(part) for part in parts)
    return prefix + ":" + hashlib.sha256(key.encode()).hexdigest()[:20]


def build_graph(entries, manifest):
    nodes, edges = {}, []
    files = {Path(item["local_path"]).name: item for item in manifest["files"]}

    def node(node_id, kind, label, **attributes):
        if node_id not in nodes:
            nodes[node_id] = dict(id=node_id, type=kind, label=label, **attributes)
        return node_id

    def edge(start, end, relation, provenance, **attributes):
        item = dict(id=stable_id("edge", start, end, relation, provenance["source_file"]),
                    source=start, target=end, relation=relation,
                    provenance=provenance, review_status="pending", **attributes)
        edges.append(item)

    def evidence_edges(claim_id, items, provenance):
        for number, item in enumerate(items):
            reference = item.get("reference")
            if not reference:
                continue
            url = ("https://pubmed.ncbi.nlm.nih.gov/" + reference.split(":", 1)[1] + "/"
                   if reference.startswith("PMID:") else None)
            source_id = node(reference, "publication", item.get("reference_title", reference), url=url)
            evidence_id = node(stable_id("evidence", claim_id, number), "evidence",
                               item.get("supports", "UNKNOWN"), upstream_record=item,
                               review_status="pending", publication_id=source_id)
            edge(source_id, evidence_id, "contains_evidence", provenance)
            edge(evidence_id, claim_id, "annotates_claim", provenance,
                 polarity=item.get("supports", "UNKNOWN"))

    for entry in entries:
        record = entry["record"]
        source = files[entry["source_file"]]
        provenance = dict(source_file=entry["source_file"],
                          snapshot_commit=manifest["snapshot_commit"],
                          source_url=source["source_url"], content_license=manifest["content_license"],
                          retrieved_on=manifest["retrieved_on"])
        disease_id = record["disease_term"]["term"]["id"]
        node(disease_id, "disease", record["name"], synonyms=record.get("synonyms", []),
             review_status="pending", provenance=provenance)
        for index, item in enumerate(record.get("genetic", [])):
            term = item.get("gene_term", {}).get("term", {})
            if not term.get("id"):
                continue
            gene_id = node(term["id"], "gene", term.get("label", item["name"]))
            claim_id = node(stable_id("claim", disease_id, "genetic", index), "claim",
                            item["name"] + " association", upstream_record=item, review_status="pending")
            edge(disease_id, claim_id, "has_gene_association_claim", provenance)
            edge(claim_id, gene_id, "mentions_gene", provenance)
            evidence_edges(claim_id, item.get("evidence", []), provenance)
        mechanisms = {}
        for index, item in enumerate(record.get("pathophysiology", [])):
            claim_id = node(stable_id("claim", disease_id, "mechanism", index), "claim", item["name"],
                            upstream_record=item, claim_type="mechanism", review_status="pending")
            mechanisms[item["name"]] = claim_id
            edge(disease_id, claim_id, "has_mechanism_claim", provenance)
            evidence_edges(claim_id, item.get("evidence", []), provenance)
            for field, kind in [("biological_processes", "process"), ("molecular_functions", "function"),
                                ("cell_types", "cell_type"), ("locations", "anatomy")]:
                for binding in item.get(field, []):
                    term = binding.get("term", {})
                    if term.get("id"):
                        term_id = node(term["id"], kind, term.get("label", binding.get("preferred_term", term["id"])))
                        edge(claim_id, term_id, "annotated_with", provenance,
                             annotation_field=field, modifier=binding.get("modifier"))
        for item in record.get("pathophysiology", []):
            for index, link in enumerate(item.get("downstream", [])):
                target = mechanisms.get(link.get("target"))
                if target:
                    # A separate claim preserves the evidence on the causal link itself.
                    link_id = node(stable_id("claim", disease_id, item["name"], "downstream", index),
                                   "claim", item["name"] + " → " + link["target"],
                                   upstream_record=link, claim_type="mechanistic_link", review_status="pending")
                    edge(mechanisms[item["name"]], link_id, "proposed_downstream_claim", provenance)
                    edge(link_id, target, "targets_claim", provenance)
                    evidence_edges(link_id, link.get("evidence", []), provenance)
        for index, item in enumerate(record.get("phenotypes", [])):
            term = item.get("phenotype_term", {}).get("term", {})
            if not term.get("id"):
                continue
            phenotype_id = node(term["id"], "phenotype", term.get("label", item["name"]))
            claim_id = node(stable_id("claim", disease_id, "phenotype", index), "claim", item["name"],
                            upstream_record=item, claim_type="phenotype", review_status="pending")
            edge(disease_id, claim_id, "has_phenotype_claim", provenance)
            edge(claim_id, phenotype_id, "mentions_phenotype", provenance)
            evidence_edges(claim_id, item.get("evidence", []), provenance)
        for field in ["animal_models", "datasets"]:
            for index, item in enumerate(record.get(field, [])):
                asset_id = node(stable_id("asset", disease_id, field, index), "asset",
                                item.get("title", item.get("genotype", field)), asset_type=field,
                                upstream_record=item, access_status="not_checked", review_status="pending")
                edge(disease_id, asset_id, "has_reported_asset", provenance)
                evidence_edges(asset_id, item.get("evidence", []), provenance)
                if item.get("publication"):
                    reference = item["publication"]
                    source_id = node(reference, "publication", reference,
                                     url="https://pubmed.ncbi.nlm.nih.gov/" + reference.split(":", 1)[1] + "/")
                    edge(source_id, asset_id, "reported_in_upstream_record", provenance)
    return {"schema_version": "0.1", "source_manifest": manifest,
            "coverage": {"diseases": len(entries), "included_sections": ["genetic", "pathophysiology", "phenotypes", "animal_models", "datasets"],
                         "omitted_sections": ["treatments", "clinical_trials", "diagnosis", "differential_diagnoses", "discussions"],
                         "limitations": "Incomplete upstream annotations. Shared terms are candidate clues. No asset owner, active recruitment, clinical eligibility or transfer is verified by this import."},
            "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
            "edges": sorted(edges, key=lambda item: item["id"])}


if __name__ == "__main__":
    data = ROOT / "data"
    graph = build_graph(json.loads((data / "disorders.json").read_text()),
                        json.loads((data / "source-manifest.json").read_text()))
    (data / "graph.json").write_text(json.dumps(graph, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
                      "node_types": dict(Counter(item["type"] for item in graph["nodes"]))}))
