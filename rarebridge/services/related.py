"""Related-disease routes for the overview and graph.

Two route families, kept distinct:

1. Recorded routes (claim_origin recorded/inferred-from-recorded): an explicit
   overlay edge between two diseases, or a path in the graph where both diseases
   have cohorts in studies that use the same documented framework/asset. These
   say "the same study method was used", never "shared biology or treatment".

2. Candidate routes from a transparent baseline: shared ontology annotations
   (HPO phenotypes; GO process/function, cell type and anatomy terms attached to
   mechanism claims) in the upstream DisMech records. Each shared term is
   weighted by an inverse document frequency over the diseases in this slice, so
   terms common to every disease count less. The score is a weighted Jaccard
   overlap: sum(weight of shared terms) / sum(weight of all terms of the pair).
   It is a ranking aid, not a probability and not clinical confidence. Every
   basis claim is AI-curated upstream and pending review.
"""

from __future__ import annotations

import math
from collections import defaultdict

RANKING_METHOD = "idf_weighted_jaccard_shared_annotations_v1"
RECORDED_METHOD = "recorded_route"
ANNOTATION_TYPES = {"phenotype", "process", "function", "cell_type", "anatomy"}


class RelatedDiseases:
    def __init__(self, registry):
        self.reg = registry
        self.disease_ids = registry.disease_ids()
        self.terms = {d: self._annotation_terms(d) for d in self.disease_ids}
        df = defaultdict(int)
        for terms in self.terms.values():
            for term in terms:
                df[term] += 1
        n = len(self.disease_ids)
        self.df = dict(df)
        self.idf = {term: math.log((n + 1) / count) for term, count in df.items()}

    # --------------------------------------------------------------- features
    def _annotation_terms(self, disease_id):
        """term_id -> set of claim IDs (of this disease) that carry the term."""
        reg = self.reg
        out = defaultdict(set)
        for edge in reg.out_edges.get(disease_id, []):
            claim = edge["target"]
            if edge["relation"] == "has_phenotype_claim":
                for inner in reg.out_edges.get(claim, []):
                    if inner["relation"] == "mentions_phenotype":
                        out[inner["target"]].add(claim)
            elif edge["relation"] == "has_mechanism_claim":
                for inner in reg.out_edges.get(claim, []):
                    if inner["relation"] == "annotated_with" and \
                            reg.nodes[inner["target"]]["type"] in ANNOTATION_TYPES:
                        out[inner["target"]].add(claim)
        return out

    def _cited_publications(self, claim_ids):
        reg = self.reg
        pubs = set()
        for claim in claim_ids:
            for edge in reg.in_edges.get(claim, []):
                if edge["relation"] != "annotates_claim":
                    continue
                for inner in reg.in_edges.get(edge["source"], []):
                    if inner["relation"] == "contains_evidence":
                        pubs.add(inner["source"])
        return sorted(pubs)

    def annotation_candidate(self, query_id, other_id):
        mine, theirs = self.terms.get(query_id, {}), self.terms.get(other_id, {})
        shared = set(mine) & set(theirs)
        union = set(mine) | set(theirs)
        if not shared or not union:
            return None
        score = sum(self.idf[t] for t in shared) / sum(self.idf[t] for t in union)
        ranked_terms = sorted(shared, key=lambda t: (-self.idf[t], self.reg.nodes[t]["label"].casefold()))
        basis_claims = sorted(set().union(*(mine[t] | theirs[t] for t in shared)))
        reg = self.reg
        return {
            "score": round(score, 4),
            "shared_terms": [{
                "id": t, "label": reg.nodes[t]["label"], "type": reg.nodes[t]["type"],
                "diseases_with_term_in_slice": self.df[t], "weight": round(self.idf[t], 4),
                "query_claim_ids": sorted(mine[t]), "related_claim_ids": sorted(theirs[t]),
            } for t in ranked_terms],
            "basis_claim_ids": basis_claims,
            "source_ids": sorted({reg.disease_record_source[d] for d in (query_id, other_id)
                                  if d in reg.disease_record_source}),
            "upstream_cited_publications": self._cited_publications(basis_claims),
            "union_size": len(union),
        }

    # ------------------------------------------------------------ recorded
    def recorded_routes(self, query_id, other_id):
        reg = self.reg
        routes = []
        # (a) explicit edges directly between the two diseases (either direction)
        for edge in reg.out_edges.get(query_id, []) + reg.in_edges.get(query_id, []):
            ends = {edge["source"], edge["target"]}
            if ends == {query_id, other_id}:
                routes.append(self._route("direct_edge", [edge], [query_id, other_id], edge.get("explanation", "")))
        # (b) both diseases studied in studies that use one documented framework/asset
        studies_q = self._studies(query_id)
        studies_o = self._studies(other_id)
        for study_q, edge_q in studies_q:
            for study_o, edge_o in studies_o:
                if study_q == study_o:
                    routes.append(self._route("shared_study", [edge_q, edge_o],
                                              [query_id, study_q, other_id],
                                              "Both diseases have cohorts in the same recorded study."))
                    continue
                for asset, edge_fq in self._frameworks(study_q):
                    for asset_o, edge_fo in self._frameworks(study_o):
                        if asset != asset_o:
                            continue
                        label = reg.nodes[asset]["label"]
                        routes.append(self._route(
                            "shared_study_framework", [edge_q, edge_fq, edge_fo, edge_o],
                            [query_id, study_q, asset, study_o, other_id],
                            f"Both diseases have cohorts in studies using one documented framework ({label}). "
                            "A shared study method, not shared biology or treatment response."))
        return routes

    def _studies(self, disease_id):
        return [(edge["target"], edge) for edge in self.reg.out_edges.get(disease_id, [])
                if edge["relation"] == "studied_in"]

    def _frameworks(self, study_id):
        return [(edge["source"], edge) for edge in self.reg.in_edges.get(study_id, [])
                if edge["relation"] == "framework_used_by"]

    def _route(self, kind, edges, node_path, explanation):
        source_ids = sorted({self.reg.canonical_source(sid) or sid
                             for edge in edges for sid in edge.get("source_ids", [])})
        status = "source_checked" if all(e.get("review_status") == "source_checked" for e in edges) else "pending"
        return {"kind": kind, "edge_ids": [e["id"] for e in edges], "node_path": node_path,
                "source_ids": source_ids, "review_status": status,
                "claim_origin": "inferred" if kind != "direct_edge" else edges[0].get("claim_origin", "recorded"),
                "explanation": explanation}

    # ------------------------------------------------------------- compose
    def related_for(self, query_id):
        """One entry per related disease; recorded routes first, then candidates by score."""
        reg = self.reg
        out = []
        for other in self.disease_ids:
            if other == query_id:
                continue
            routes = self.recorded_routes(query_id, other)
            candidate = self.annotation_candidate(query_id, other)
            if not routes and not candidate:
                continue
            reason_parts, source_ids = [], set()
            if routes:
                direct = next((r for r in routes if r["kind"] == "direct_edge"), None)
                if direct is not None:
                    reason_parts.append(direct["explanation"].strip())
                else:
                    reason_parts.append("Recorded route: " + routes[0]["explanation"].strip())
                for route in routes:
                    source_ids.update(route["source_ids"])
            if candidate:
                top = ", ".join(term["label"] for term in candidate["shared_terms"][:3])
                n = len(candidate["shared_terms"])
                prefix = "Also" if routes else "Candidate only"
                reason_parts.append(
                    f"{prefix}: the upstream DisMech records for both diseases annotate {n} shared "
                    f"term{'s' if n != 1 else ''} (most specific in this slice: {top}). These AI-curated "
                    "annotations are pending review and do not establish a shared mechanism, asset "
                    "compatibility or treatment applicability.")
                source_ids.update(candidate["source_ids"])
            checked_route = any(r["review_status"] == "source_checked" for r in routes)
            out.append({
                "id": other,
                "label": reg.disease_label(other),
                "reason": " ".join(reason_parts),
                "basis_claim_ids": candidate["basis_claim_ids"] if candidate else [],
                "source_ids": sorted(source_ids),
                "review_status": "source_checked" if checked_route else "pending",
                # additive fields
                "relation_kind": "published_co_study" if routes else "shared_upstream_annotations",
                "ranking_method": RECORDED_METHOD if routes else RANKING_METHOD,
                "candidate_score": candidate["score"] if candidate else None,
                "candidate_score_method": RANKING_METHOD if candidate else None,
                "score_note": "Ranking aid only; not a probability, similarity of biology or clinical confidence.",
                "recorded_routes": routes,
                "shared_terms": candidate["shared_terms"][:8] if candidate else [],
                "shared_term_count": len(candidate["shared_terms"]) if candidate else 0,
                "upstream_cited_publications": candidate["upstream_cited_publications"] if candidate else [],
            })
        out.sort(key=lambda item: (0 if item["recorded_routes"] else 1, -(item["candidate_score"] or 0),
                                   item["label"].casefold()))
        return out
