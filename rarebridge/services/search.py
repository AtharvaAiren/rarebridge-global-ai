"""Global search: resolve a free-text query to stable IDs and the disease IDs
that let the UI enter the disease journey.

Matching is deliberately simple and inspectable: normalized exact match, word
prefix, substring and all-token prefix. No fuzzy medical vocabulary expansion is
claimed. Opaque IDs are compared but never rewritten.
"""

from __future__ import annotations

import re
import unicodedata

from .constants import SEARCH_LIMIT_DEFAULT, SEARCH_LIMIT_MAX, SEARCH_LIMIT_MIN

TYPE_PRIORITY = {
    "disease": 0, "gene": 1, "organization": 2, "study_team": 3, "study": 4, "asset": 5,
    "researcher": 6, "claim": 7, "phenotype": 8, "process": 9, "function": 10,
    "cell_type": 11, "anatomy": 12, "publication": 13, "source": 14,
}
MATCHED_ON_BY_TYPE = {
    "disease": "name", "gene": "gene symbol", "phenotype": "phenotype term",
    "claim": "mechanism claim", "process": "biological process term", "function": "molecular function term",
    "cell_type": "cell type term", "anatomy": "anatomy term", "organization": "organization name",
    "study_team": "study team name", "researcher": "researcher name", "study": "study name",
    "asset": "asset name", "publication": "title", "source": "title",
}
SEARCHABLE_CLAIM_TYPES = {"mechanism", "mechanistic_link"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    text = text.replace("\u2192", " ")
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text).split())


def clamp_limit(limit):
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = SEARCH_LIMIT_DEFAULT
    return max(SEARCH_LIMIT_MIN, min(SEARCH_LIMIT_MAX, value))


class SearchIndex:
    def __init__(self, registry):
        self.registry = registry
        self.entries = []
        self._build()

    # ------------------------------------------------------------------ build
    def _entry(self, item_id, item_type, label, names, disease_ids, ids=()):
        self.entries.append({
            "id": item_id, "type": item_type, "label": label,
            # (display text, normalized text, matched_on)
            "names": [(text, normalize(text), why) for text, why in names if text],
            "ids": [i for i in [item_id, *ids] if i],
            "disease_ids": sorted(set(disease_ids)),
        })

    def _build(self):
        reg = self.registry
        contacts = reg.contacts
        for node_id, node in reg.nodes.items():
            kind = node["type"]
            if kind == "disease":
                names = [(name, "name" if i == 0 else "synonym")
                         for i, name in enumerate(reg.disease_names(node_id))]
                self._entry(node_id, kind, node["label"], names, [node_id])
            elif kind in ("gene", "phenotype", "process", "function", "cell_type", "anatomy"):
                self._entry(node_id, kind, node["label"], [(node["label"], MATCHED_ON_BY_TYPE[kind])],
                            reg.associated_diseases(node_id, max_depth=2))
            elif kind == "claim" and node.get("claim_type") in SEARCHABLE_CLAIM_TYPES:
                self._entry(node_id, "claim", node["label"], [(node["label"], "mechanism claim")],
                            reg.associated_diseases(node_id, max_depth=2))
            elif kind in ("organization", "study_team", "researcher"):
                contact = contacts.get(node_id, {})
                diseases = contact.get("disease_ids") or reg.associated_diseases(node_id)
                self._entry(node_id, kind, node["label"], [(node["label"], MATCHED_ON_BY_TYPE[kind])], diseases)
            elif kind == "study":
                names = [(node["label"], "study name")] + [(alias, "study alias") for alias in node.get("aliases", [])]
                self._entry(node_id, kind, node["label"], names, reg.associated_diseases(node_id, max_depth=2),
                            ids=node.get("registry_ids_reported", []))
            elif kind == "asset":
                asset = reg.assets.get(node_id, {})
                diseases = asset.get("target_disease_ids") or reg.associated_diseases(node_id, max_depth=2)
                self._entry(node_id, kind, node["label"], [(node["label"], "asset name")], diseases)
        # Assets known only from assessment bundles (base-only mode).
        indexed = {entry["id"] for entry in self.entries}
        for asset_id, asset in reg.assets.items():
            if asset_id in indexed:
                continue
            diseases = asset.get("target_disease_ids") or sorted({
                bundle["target_disease"]["id"] for bundle in reg.bundles.values()
                if bundle["asset"]["id"] == asset_id})
            self._entry(asset_id, "asset", asset["label"], [(asset["label"], "asset name")], diseases)
        # Sources: exact ID/alias lookups plus titles.
        source_diseases = {canonical: self._source_diseases(canonical) for canonical in reg.sources}
        for canonical, source in reg.sources.items():
            diseases = set(source_diseases[canonical])
            if source.get("version_of") in source_diseases:
                diseases |= source_diseases[source["version_of"]]
            node = reg.nodes.get(canonical)
            kind_text = source.get("source_kind", "")
            kind = "publication" if (node and node["type"] == "publication") or "publication" in kind_text \
                or "study" in kind_text or kind_text == "preprint" else "source"
            self._entry(canonical, kind, source.get("title", canonical), [(source.get("title"), "title")],
                        diseases, ids=source.get("aliases", []))

    def _source_diseases(self, canonical):
        """Diseases a source is about: graph position, citing edges, bundles, contacts, assets."""
        reg = self.registry
        diseases = set(reg.associated_diseases(canonical, max_depth=4))
        for bundle in reg.bundles.values():
            if canonical in bundle.get("sources", {}):
                diseases.add(bundle["target_disease"]["id"])
        if canonical.startswith("DISMECH:"):
            diseases |= {d for d, s in reg.disease_record_source.items() if s == canonical}
        for edge in reg.edges:
            if edge.get("origin") == "dismech_snapshot":
                continue
            if any(reg.canonical_source(sid) == canonical for sid in edge.get("source_ids", [])):
                for end in (edge["source"], edge["target"]):
                    diseases |= set(reg.associated_diseases(end, max_depth=2))
        for contact in reg.contacts.values():
            if any(reg.canonical_source(sid) == canonical for sid in contact.get("source_ids", [])):
                diseases |= set(contact.get("disease_ids", []))
        for asset in reg.assets.values():
            if any(reg.canonical_source(sid) == canonical for sid in asset.get("source_ids", [])):
                diseases |= set(asset.get("target_disease_ids", []))
        return diseases

    # ----------------------------------------------------------------- query
    @staticmethod
    def _match(q_raw, q_norm, entry):
        """Return (tier, rank, matched_on, matched_text) or None. Lower is better."""
        q_fold = q_raw.strip().casefold()
        for item_id in entry["ids"]:
            fold = item_id.casefold()
            if fold == q_fold or (fold.startswith("doi:") and fold[4:] == q_fold):
                return (0, 0, "id" if item_id == entry["id"] else "alias", item_id)
        if not q_norm:
            return None
        best = None
        q_tokens = q_norm.split()
        for text, norm, why in entry["names"]:
            if not norm:
                continue
            if norm == q_norm:
                cand = (0, 1, why, text)
            elif len(q_norm) < 2:
                continue
            elif norm.startswith(q_norm + " ") or norm.startswith(q_norm):
                cand = (1, 2, why, text)
            elif (" " + q_norm) in (" " + norm):
                cand = (1, 3, why, text)
            elif len(q_norm) >= 3 and q_norm in norm:
                cand = (2, 4, why, text)
            elif len(q_tokens) > 1 and all(
                    len(tok) >= 2 and any(word.startswith(tok) for word in norm.split()) for tok in q_tokens):
                cand = (2, 5, why, text)
            else:
                continue
            if best is None or cand[:2] < best[:2]:
                best = cand
        return best

    def search(self, query, limit=SEARCH_LIMIT_DEFAULT):
        limit = clamp_limit(limit)
        q_raw = (query or "").strip()
        q_norm = normalize(q_raw)
        hits = []
        if q_raw:
            for entry in self.entries:
                match = self._match(q_raw, q_norm, entry)
                if match is None:
                    continue
                tier, rank, why, text = match
                # Diseases lead: the search exists to enter a disease journey.
                tier_key = 0 if entry["type"] == "disease" else tier + 1
                hits.append(((tier_key, TYPE_PRIORITY.get(entry["type"], 99), rank,
                              len(entry["label"]), entry["label"].casefold(), entry["id"]),
                             {"id": entry["id"], "type": entry["type"], "label": entry["label"],
                              "matched_on": why, "disease_ids": entry["disease_ids"],
                              "matched_text": text}))
        hits.sort(key=lambda pair: pair[0])
        items = [item for _key, item in hits]
        return {"items": items[:limit], "total_matches": len(items), "limit": limit}
