"""Select a compact supporting subgraph for one disease (and optionally one
assessment) by explanatory relevance, not by random slicing.

Node groups are added whole, in priority order, until max_nodes is reached:
  query disease -> assessment asset + its sources -> related diseases ->
  recorded route nodes (studies, framework, paper) -> contacts -> related
  communities' organizations -> gene association -> shared-annotation basis ->
  other assets -> remaining mechanism claims -> phenotype claims -> evidence.
A group that does not fit is skipped (reported in coverage) and smaller later
groups may still fit. Every served edge keeps its provenance and review status
and gains source_ids, a qualitative confidence_label and a short explanation.
Synthetic edges (assessment scope/evidence, ranking candidates) are labelled
with claim_origin and never assert therapeutic or eligibility transfer.
"""

from __future__ import annotations

import copy

from rarebridge.assessment import assess

from .constants import CHECKED_LABEL, FORBIDDEN_RELATIONS, INFERRED_PENDING_LABEL, PENDING_LABEL
from .related import RANKING_METHOD


class UnknownGraphTarget(LookupError):
    pass


class GraphService:
    def __init__(self, registry, related, contacts):
        self.reg = registry
        self.related = related
        self.contacts = contacts

    # ----------------------------------------------------------- synthetic
    def _retrieved_on(self):
        return self.reg.manifest.get("retrieved_on", "")

    def _assessment_layer(self, bundle_id):
        """Nodes/edges derived from a curated assessment bundle (claim_origin 'recorded')."""
        reg = self.reg
        bundle = reg.bundle(bundle_id)
        asset = bundle["asset"]
        target = bundle["target_disease"]["id"]
        nodes, edges = {}, []
        asset_node = asset["id"]
        if asset_node not in reg.nodes:
            nodes[asset_node] = {"id": asset_node, "type": "asset", "label": asset["label"],
                                 "url": asset.get("url"), "asset_type": asset.get("type"),
                                 "access_status": asset.get("access_status"),
                                 "origin": "assessment_bundle", "review_status": "pending"}
        source_nodes = {}
        for canonical in bundle.get("sources", {}):
            canon = reg.canonical_source(canonical) or canonical
            node_id = reg.node_alias.get(canon, canon)
            if node_id not in reg.nodes:
                src = reg.sources[canon]
                kind = src.get("source_kind", "")
                nodes[node_id] = {"id": node_id, "label": src.get("title", canon), "url": src.get("url"),
                                  "type": "publication" if ("study" in kind or "publication" in kind
                                                            or kind == "preprint") else "source",
                                  "source_kind": kind, "origin": "assessment_bundle"}
            source_nodes[canon] = node_id
        result = assess(bundle)
        evidence = [item for check in bundle["checks"] for item in check.get("evidence", [])]
        all_checked = bool(evidence) and all(e["review_status"] == "source_checked" for e in evidence)
        supported = [r["id"] for r in result["checks"] if r["status"] == "supported"]
        open_required = [r["id"] for r in result["checks"] if r["required"] and r["status"] != "supported"]
        provenance = {"source_url": asset.get("url", ""), "retrieved_on": self._retrieved_on(),
                      "derived_from": f"assessment bundle {bundle_id}"}
        edges.append({
            "id": f"assessment:{bundle_id}:scope", "source": target, "target": asset_node,
            "relation": "assessment_scope", "provenance": provenance,
            "review_status": "source_checked" if all_checked else "pending",
            "source_ids": sorted(source_nodes), "claim_origin": "recorded",
            "confidence_label": f"Assessment outcome: {result['outcome']} (not an approval)",
            "explanation": (f"Scoped assessment {bundle_id} for '{bundle['goal']}'. Supported checks: "
                            f"{', '.join(supported) or 'none'}. Open required checks: "
                            f"{', '.join(open_required) or 'none'}. Records what cited sources show; "
                            "it is not permission to reuse the asset."),
            "assessment_id": bundle_id, "assessment_outcome": result["outcome"],
        })
        for row in result["checks"]:
            for index, item in enumerate(row["active_evidence"]):
                canon = item["source_id"]
                src_url = reg.sources.get(canon, {}).get("url", "")
                edges.append({
                    "id": f"assessment:{bundle_id}:{row['id']}:{index}", "source": source_nodes[canon],
                    "target": asset_node, "relation": "evidence_for_check",
                    "provenance": {"source_url": src_url, "retrieved_on": self._retrieved_on(),
                                   "derived_from": f"assessment bundle {bundle_id}"},
                    "review_status": item["review_status"], "source_ids": [canon], "claim_origin": "recorded",
                    "confidence_label": CHECKED_LABEL if item["review_status"] == "source_checked" else PENDING_LABEL,
                    "explanation": (f"{item['rationale']} (check '{row['question']}': {row['status']}; "
                                    f"evidence polarity {item['polarity']})."),
                    "assessment_id": bundle_id, "check_id": row["id"], "check_status": row["status"],
                    "polarity": item["polarity"],
                })
        # Derived public routes that have no curated node yet.
        for contact in self.contacts.for_bundle(bundle):
            if contact["id"] in reg.nodes:
                continue
            nodes[contact["id"]] = {"id": contact["id"], "type": contact["kind"], "label": contact["label"],
                                    "url": contact["url"], "origin": "assessment_bundle",
                                    "review_status": contact["review_status"]}
            edges.append({
                "id": f"assessment:{bundle_id}:route:{contact['id']}", "source": contact["id"],
                "target": asset_node, "relation": "listed_as_public_route",
                "provenance": provenance, "review_status": "pending", "source_ids": contact["source_ids"],
                "claim_origin": "recorded", "confidence_label": PENDING_LABEL,
                "explanation": "Listed as a public route on the asset record; a potential contact, not the confirmed owner.",
            })
        return nodes, edges, asset_node, list(source_nodes.values())

    def _candidate_edge(self, query_id, item):
        reg = self.reg
        a, b = sorted([query_id, item["id"]])
        url = ""
        for sid in item["source_ids"]:
            if sid.startswith("DISMECH:"):
                url = reg.sources[sid]["url"]
                break
        return {
            "id": f"inferred:shared-annotations:{a}:{b}", "source": query_id, "target": item["id"],
            "relation": "candidate_shared_annotations",
            "provenance": {"source_url": url, "retrieved_on": self._retrieved_on(), "derivation": RANKING_METHOD},
            "review_status": "pending",
            "source_ids": [sid for sid in item["source_ids"] if sid.startswith("DISMECH:")],
            "claim_origin": "inferred", "confidence_label": INFERRED_PENDING_LABEL,
            "candidate_score": item["candidate_score"],
            "explanation": (f"Ranking candidate from {item['shared_term_count']} shared upstream annotations "
                            f"(score {item['candidate_score']}, a ranking aid only). Does not establish shared "
                            "biology, asset compatibility or treatment applicability."),
        }

    # ------------------------------------------------------------- groups
    def _claims(self, disease_id, relation):
        return [e["target"] for e in self.reg.out_edges.get(disease_id, []) if e["relation"] == relation]

    def _targets(self, node_id, relation):
        return [e["target"] for e in self.reg.out_edges.get(node_id, []) if e["relation"] == relation]

    def _groups(self, disease_id, bundle_layer, related):
        reg = self.reg
        groups = [("query disease", [disease_id])]
        if bundle_layer:
            _nodes, _edges, asset_node, source_nodes = bundle_layer
            groups.append(("assessment asset", [asset_node]))
            groups.append(("assessment sources", source_nodes))
        for item in related[:3]:
            groups.append((f"related disease {item['id']}", [item["id"]]))
        for item in related:
            for route in item["recorded_routes"]:
                groups.append(("recorded route", route["node_path"]))
                route_pubs = [reg.node_alias.get(sid, sid) for sid in route["source_ids"]]
                groups.append(("route sources", [n for n in route_pubs if n in reg.nodes]))
        for contact in self.contacts.for_disease(disease_id):
            groups.append((f"contact {contact['kind']}", [contact["id"]]))
        for item in related:
            if not item["recorded_routes"]:
                continue  # an organization is only connected through a recorded study route
            for org in item.get("organizations") or self.contacts.for_disease(item["id"], kinds={"organization"}):
                groups.append((f"related community {item['id']}", [org["id"]]))
        for disease in [disease_id] + [item["id"] for item in related[:2]]:
            for claim in self._claims(disease, "has_gene_association_claim"):
                groups.append(("gene association", [claim, *self._targets(claim, "mentions_gene")]))
        mechanism_claims = self._claims(disease_id, "has_mechanism_claim")
        for claim in mechanism_claims[:3]:
            groups.append(("key mechanism claim", [claim, *self._targets(claim, "annotated_with")[:1]]))
        for rank, item in enumerate(related[:2]):
            for term in item.get("shared_terms", [])[:2 - rank]:
                groups.append(("shared annotation basis",
                               [term["query_claim_ids"][0], term["id"], term["related_claim_ids"][0]]))
        for asset_id, record in sorted(reg.assets.items()):
            if disease_id in record.get("target_disease_ids", []) and asset_id in reg.nodes:
                groups.append(("asset", [asset_id]))
        for asset_id in self._targets(disease_id, "has_reported_asset"):
            groups.append(("upstream reported asset", [asset_id]))
        for claim in mechanism_claims[3:]:
            groups.append(("mechanism claim", [claim, *self._targets(claim, "annotated_with")[:2]]))
        for claim in self._claims(disease_id, "has_phenotype_claim"):
            groups.append(("phenotype claim", [claim, *self._targets(claim, "mentions_phenotype")]))
        for claim in self._claims(disease_id, "has_mechanism_claim") + self._claims(disease_id, "has_phenotype_claim"):
            for edge in reg.in_edges.get(claim, []):
                if edge["relation"] == "annotates_claim":
                    pubs = [e["source"] for e in reg.in_edges.get(edge["source"], [])
                            if e["relation"] == "contains_evidence"]
                    groups.append(("upstream evidence", [*pubs, edge["source"]]))
        return groups

    # ------------------------------------------------------------- public
    def build(self, disease_id=None, assessment_id=None, max_nodes=40):
        reg = self.reg
        if assessment_id is not None and assessment_id not in reg.bundles:
            raise UnknownGraphTarget(("assessment", assessment_id))
        if disease_id is None:
            if assessment_id is None:
                raise UnknownGraphTarget(("missing", None))
            disease_id = reg.bundles[assessment_id]["target_disease"]["id"]
        if reg.nodes.get(disease_id, {}).get("type") != "disease":
            raise UnknownGraphTarget(("disease", disease_id))

        layer = self._assessment_layer(assessment_id) if assessment_id else None
        extra_nodes = dict(layer[0]) if layer else {}
        extra_edges = list(layer[1]) if layer else []
        related = self.related.related_for(disease_id)
        for item in related:
            if item["candidate_score"]:
                extra_edges.append(self._candidate_edge(disease_id, item))

        groups = self._groups(disease_id, layer, related)
        if layer:
            at = next(i for i, (name, _m) in enumerate(groups) if name == "assessment sources") + 1
            extra_groups = []
            target = reg.bundles[assessment_id]["target_disease"]["id"]
            if target != disease_id:
                extra_groups.append(("assessment target disease", [target]))
            for contact in self.contacts.for_bundle(reg.bundles[assessment_id]):
                extra_groups.append(("assessment contact", [contact["id"]]))
            groups[at:at] = extra_groups

        selected, skipped, pool = [], [], set()
        chosen = set()
        for name, members in groups:
            members = [m for m in dict.fromkeys(members) if m in reg.nodes or m in extra_nodes]
            pool.update(members)
            new = [m for m in members if m not in chosen]
            if not new:
                continue
            if len(selected) + len(new) > max_nodes:
                skipped.append(name)
                continue
            selected.extend(new)
            chosen.update(new)

        # Drop nodes left without any served edge (except anchors) so nothing floats unexplained.
        anchors = {disease_id}
        if layer:
            anchors.add(layer[2])
        linked = set()
        for edge in reg.edges + extra_edges:
            if edge["source"] in chosen and edge["target"] in chosen:
                linked.update((edge["source"], edge["target"]))
        selected = [n for n in selected if n in linked or n in anchors]
        chosen = set(selected)

        nodes_out = []
        for node_id in selected:
            node = copy.deepcopy(reg.nodes.get(node_id) or extra_nodes[node_id])
            node.setdefault("origin", reg.node_origin.get(node_id, "assessment_bundle"))
            nodes_out.append(node)

        edges_out = []
        for edge in reg.edges + extra_edges:
            if edge["source"] in chosen and edge["target"] in chosen and edge["relation"] not in FORBIDDEN_RELATIONS:
                item = copy.deepcopy(edge)
                item.setdefault("source_ids", [])
                item.setdefault("claim_origin", "imported")
                item.setdefault("confidence_label",
                                CHECKED_LABEL if item.get("review_status") == "source_checked" else PENDING_LABEL)
                item.setdefault("explanation", "Relationship from the cited source; see provenance.")
                edges_out.append(item)

        cited = {sid for edge in edges_out for sid in edge["source_ids"]}
        cited |= {n["id"] for n in nodes_out if n["type"] in ("publication", "source") and reg.canonical_source(n["id"])}
        sources = reg.sources_for(sorted(cited))

        totals = reg.total_counts()
        omitted = len(pool - chosen)
        note = (f"Showing {len(nodes_out)} of {totals['total_nodes']} nodes and {len(edges_out)} of "
                f"{totals['total_edges']} edges, chosen by explanatory relevance to "
                f"{reg.disease_label(disease_id)}"
                + (f" and assessment {assessment_id}" if assessment_id else "") + ". "
                + (f"{omitted} further relevant nodes are hidden by max_nodes={max_nodes}; hidden is not absent. "
                   if omitted else "")
                + "Imported DisMech edges remain pending review; confidence labels are qualitative, not probabilities.")
        if not any(item["recorded_routes"] for item in related) and not assessment_id:
            note += " No recorded route to another disease or asset exists for this disease in the slice."
        return {
            "nodes": nodes_out, "edges": edges_out, "sources": sources,
            "coverage": {"scope_note": note, "truncated": omitted > 0,
                         "total_nodes": totals["total_nodes"], "total_edges": totals["total_edges"],
                         "shown_nodes": len(nodes_out), "shown_edges": len(edges_out),
                         "relevant_nodes_available": len(pool), "omitted_relevant_nodes": omitted,
                         "skipped_groups": sorted(set(skipped)), "max_nodes": max_nodes},
            "data_origin": reg.data_origin,
        }
