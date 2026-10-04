"""Load the pinned snapshot plus the optional curation overlay into one registry.

Load order (contract): base graph -> base disease records -> base assessment
bundles -> curation/atlas-overlay.json (if present). The overlay only appends.
Any ID or source-alias conflict raises DataError with every problem listed; the
registry never silently overwrites a base record.

This module never opens the evaluation lane (held-out cases must stay out of
runtime data, search and prompts).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

from rarebridge.assessment import validate as validate_bundle

from .constants import CHECKED_LABEL, PENDING_LABEL

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "rarebridge" / "data"
DEFAULT_OVERLAY = ROOT / "curation" / "atlas-overlay.json"
SCHEMA_CANDIDATES = (
    ROOT / "handoffs" / "contracts" / "overlay.schema.json",
    ROOT / "contracts" / "overlay.schema.json",
)
OVERLAY_DISABLED_VALUES = {"", "0", "off", "none", "false", "disabled"}

SOURCE_REQUIRED = ("title", "url", "aliases", "published_on", "source_kind", "note")

# Human-readable explanations for imported DisMech relations.
IMPORTED_EXPLANATIONS = {
    "has_gene_association_claim": "The upstream DisMech record states a gene association for this disease. Imported; not independently reviewed.",
    "mentions_gene": "The association claim names this gene. Imported; not independently reviewed.",
    "has_phenotype_claim": "The upstream DisMech record lists this phenotype for the disease. Imported; frequency and population not reviewed.",
    "mentions_phenotype": "The phenotype claim maps to this ontology term. Imported; not independently reviewed.",
    "has_mechanism_claim": "The upstream DisMech record proposes this mechanism for the disease. Imported hypothesis, pending source review.",
    "annotated_with": "The mechanism claim is annotated with this ontology term in the upstream record. An annotation, not a measured finding.",
    "proposed_downstream_claim": "The upstream record proposes a downstream mechanistic link. Proposed causal direction is not established here.",
    "targets_claim": "The proposed mechanistic link points to this mechanism claim. Imported; not independently reviewed.",
    "contains_evidence": "The upstream record cites this publication for the claim. RareBridge has not checked that the publication supports it.",
    "annotates_claim": "Upstream evidence label attached to the claim. The label comes from DisMech's AI-assisted curation.",
    "has_reported_asset": "The upstream record reports this research asset. Availability, owner and access were not checked.",
    "reported_in_upstream_record": "The upstream record links this asset to the publication. Not independently checked.",
}


class DataError(RuntimeError):
    """Raised when base or overlay data cannot be combined safely."""

    def __init__(self, problems):
        self.problems = list(problems)
        message = "RareBridge data error (nothing was overwritten):\n  - " + "\n  - ".join(self.problems)
        super().__init__(message)


def _read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_overlay_path(explicit=None):
    """Explicit argument wins; then RAREBRIDGE_OVERLAY; then the default path.

    Returns None when the overlay is disabled. A missing default file is not an
    error: the registry starts with base data only.
    """
    if explicit is not None:
        return None if str(explicit).strip().lower() in OVERLAY_DISABLED_VALUES else Path(explicit)
    env = os.environ.get("RAREBRIDGE_OVERLAY")
    if env is not None:
        return None if env.strip().lower() in OVERLAY_DISABLED_VALUES else Path(env)
    return DEFAULT_OVERLAY


class Registry:
    """In-memory, read-only view over the snapshot and overlay.

    Stored records are never mutated after load. Callers receive deep copies
    where a response could be modified downstream.
    """

    def __init__(self, data_dir=DATA_DIR, overlay_path=None, schema_path=None):
        self.data_dir = Path(data_dir)
        self.overlay_path = resolve_overlay_path(overlay_path)
        self.schema_path = Path(schema_path) if schema_path else next(
            (p for p in SCHEMA_CANDIDATES if p.exists()), None)

        self.nodes: dict[str, dict] = {}
        self.node_origin: dict[str, str] = {}
        self.node_alias: dict[str, str] = {}
        self.edges: list[dict] = []
        self.edge_by_id: dict[str, dict] = {}
        self.out_edges = defaultdict(list)
        self.in_edges = defaultdict(list)

        self.sources: dict[str, dict] = {}
        self.source_alias: dict[str, str] = {}
        self.source_origin: dict[str, str] = {}

        self.bundles: dict[str, dict] = {}
        self.bundle_origin: dict[str, str] = {}
        self.bundle_goal: dict[str, str] = {}
        self.bundle_goal_inferred: set[str] = set()
        self.bundles_by_scope = defaultdict(list)  # (asset_id, target_id, goal_id) -> [bundle ids]

        self.assets: dict[str, dict] = {}
        self.asset_origin: dict[str, str] = {}
        self.contacts: dict[str, dict] = {}
        self.disease_synonyms = defaultdict(list)
        self.disease_records: dict[str, dict] = {}
        self.disease_record_source: dict[str, str] = {}
        self.manifest: dict = {}
        self.graph_coverage: dict = {}
        self.overlay_meta = {"loaded": False, "path": None, "sha256": None,
                             "coverage_note": None, "counts": {}, "merge_notes": [],
                             "schema_checked": False}
        self._problems: list[str] = []

        self._load_base()
        self._load_overlay()
        if self._problems:
            raise DataError(self._problems)
        self._index_edges()

    # ------------------------------------------------------------------ helpers
    def _problem(self, text):
        self._problems.append(text)

    def _add_source(self, canonical, source, origin, *, strict=True):
        """Register a source and its aliases; flag inconsistent redefinitions."""
        record = dict(source)
        record.setdefault("aliases", [])
        record.setdefault("published_on", None)
        record.setdefault("source_kind", "unspecified")
        record.setdefault("note", "")
        record.setdefault("title", canonical)
        if not record.get("url"):
            self._problem(f"source {canonical} ({origin}) has no URL")
            return
        existing = self.sources.get(canonical)
        if existing is not None:
            same = (existing["url"], sorted(existing.get("aliases", []))) == (
                record["url"], sorted(record.get("aliases", [])))
            if not same:
                self._problem(
                    f"source {canonical} is defined differently by {self.source_origin[canonical]} "
                    f"and {origin} (url/aliases differ)")
            return
        for alias in [canonical, *record["aliases"]]:
            owner = self.source_alias.get(alias)
            if owner is not None and owner != canonical:
                self._problem(f"source alias {alias} maps to both {owner} and {canonical} ({origin})")
                return
        self.sources[canonical] = record
        self.source_origin[canonical] = origin
        for alias in [canonical, *record["aliases"]]:
            self.source_alias[alias] = canonical

    def _add_node(self, node, origin):
        node_id = node.get("id")
        if not node_id or not node.get("type") or not node.get("label"):
            self._problem(f"{origin} node is missing id/type/label: {node!r:.120}")
            return
        alias_owner = self.node_alias.get(node_id)
        if alias_owner is not None and alias_owner != node_id:
            self._problem(f"{origin} node {node_id} collides with an alias of node {alias_owner}")
            return
        existing = self.nodes.get(node_id)
        if existing is not None:
            if existing["type"] != node["type"]:
                self._problem(
                    f"{origin} node {node_id} has type {node['type']} but {self.node_origin[node_id]} "
                    f"already defines it as {existing['type']}")
                return
            added = [key for key in node if key not in existing]
            for key in added:
                existing[key] = copy.deepcopy(node[key])
            changed = [key for key in node if key in existing and key not in added
                       and existing[key] != node[key] and key != "id"]
            note = f"{origin} node {node_id} merged additively (new keys: {added or 'none'})"
            if changed:
                note += f"; differing existing keys kept unchanged: {changed}"
            self.overlay_meta["merge_notes"].append(note)
            return
        record = copy.deepcopy(node)
        self.nodes[node_id] = record
        self.node_origin[node_id] = origin
        for alias in record.get("aliases", []) if record["type"] == "publication" else []:
            owner = self.node_alias.get(alias)
            if alias in self.nodes and alias != node_id:
                self._problem(f"{origin} publication alias {alias} collides with existing node {alias}")
            elif owner is not None and owner != node_id:
                self._problem(f"{origin} publication alias {alias} maps to both {owner} and {node_id}")
            else:
                self.node_alias[alias] = node_id
        self.node_alias.setdefault(node_id, node_id)

    def _add_edge(self, edge, origin):
        edge_id = edge.get("id")
        if not edge_id:
            self._problem(f"{origin} edge without id")
            return
        if edge_id in self.edge_by_id:
            self._problem(f"{origin} edge {edge_id} duplicates an existing edge ID")
            return
        for end in ("source", "target"):
            if edge.get(end) not in self.nodes:
                self._problem(f"{origin} edge {edge_id}: {end} {edge.get(end)} is not a known node")
                return
        record = copy.deepcopy(edge)
        record["origin"] = origin
        for sid in record.get("source_ids", []):
            if sid not in self.source_alias:
                self._problem(f"{origin} edge {edge_id}: unknown source {sid}")
        self.edges.append(record)
        self.edge_by_id[edge_id] = record

    def _add_bundle(self, bundle, origin):
        bundle_id = bundle.get("id")
        if not bundle_id:
            self._problem(f"{origin} assessment bundle without id")
            return
        if bundle_id in self.bundles:
            self._problem(f"assessment ID {bundle_id} from {origin} already exists ({self.bundle_origin[bundle_id]})")
            return
        try:
            validate_bundle(bundle)
        except ValueError as exc:
            self._problem(f"assessment {bundle_id} ({origin}) rejected by the shared engine: {exc}")
            return
        target = bundle.get("target_disease", {}).get("id")
        if self.nodes.get(target, {}).get("type") != "disease":
            self._problem(f"assessment {bundle_id} targets unknown disease {target}")
            return
        for canonical, source in bundle.get("sources", {}).items():
            self._add_source(canonical, source, f"assessment {bundle_id}")
        goal_id = bundle.get("goal_id")
        if not goal_id:
            # Base bundles predate goal_id; their goal text is the natural-history goal.
            goal_id = "natural_history"
            self.bundle_goal_inferred.add(bundle_id)
        self.bundles[bundle_id] = copy.deepcopy(bundle)
        self.bundle_origin[bundle_id] = origin
        self.bundle_goal[bundle_id] = goal_id
        asset_id = bundle["asset"]["id"]
        self.bundles_by_scope[(asset_id, target, goal_id)].append(bundle_id)
        if asset_id not in self.assets:
            self.assets[asset_id] = copy.deepcopy(bundle["asset"])
            self.asset_origin[asset_id] = f"assessment {bundle_id}"

    # ---------------------------------------------------------------- base load
    def _load_base(self):
        graph = _read_json(self.data_dir / "graph.json")
        self.manifest = graph.get("source_manifest") or _read_json(self.data_dir / "source-manifest.json")
        self.graph_coverage = graph.get("coverage", {})
        for node in graph["nodes"]:
            self._add_node(node, "dismech_snapshot")

        # Upstream DisMech records as citable sources (what an imported edge came from).
        for item in self.manifest.get("files", []):
            name = Path(item["local_path"]).name
            self._add_source(f"DISMECH:{name}", {
                "title": f"DisMech AI-curated disease record ({name})",
                "url": item["source_url"],
                "aliases": [],
                "published_on": None,
                "source_kind": "ai_curated_record",
                "note": ("Imported annotation, pending independent source review. Disease Mechanisms "
                         "Knowledge Base (DisMech), Monarch Initiative contributors, CC-BY-4.0. "
                         f"Snapshot commit {self.manifest.get('snapshot_commit')}."),
                "content_license": self.manifest.get("content_license"),
                "snapshot_commit": self.manifest.get("snapshot_commit"),
            }, "dismech_snapshot")

        # Publications cited inside the upstream records.
        for node in graph["nodes"]:
            if node["type"] == "publication":
                self._add_source(node["id"], {
                    "title": node.get("label", node["id"]),
                    "url": node.get("url") or f"https://pubmed.ncbi.nlm.nih.gov/{node['id'].split(':', 1)[-1]}/",
                    "aliases": [],
                    "published_on": None,
                    "source_kind": "publication_cited_by_upstream_record",
                    "note": ("Cited by an upstream DisMech record. RareBridge has not checked that this "
                             "publication supports the attached claim."),
                }, "dismech_snapshot")

        for edge in graph["edges"]:
            record = dict(edge)
            source_file = edge.get("provenance", {}).get("source_file")
            record.setdefault("source_ids", [f"DISMECH:{source_file}"] if source_file else [])
            record.setdefault("claim_origin", "imported")
            record.setdefault("confidence_label",
                              PENDING_LABEL if edge.get("review_status") == "pending" else CHECKED_LABEL)
            explanation = IMPORTED_EXPLANATIONS.get(edge["relation"],
                                                    "Imported from the upstream disease record; pending review.")
            if edge["relation"] == "annotates_claim" and edge.get("polarity"):
                explanation = f"Upstream evidence label '{edge['polarity']}'. " + explanation
            record.setdefault("explanation", explanation)
            self._add_edge(record, "dismech_snapshot")

        for entry in _read_json(self.data_dir / "disorders.json"):
            record = entry["record"]
            disease_id = record["disease_term"]["term"]["id"]
            self.disease_records[disease_id] = record
            self.disease_record_source[disease_id] = f"DISMECH:{entry['source_file']}"

        for path in sorted(self.data_dir.glob("assessment-*.json")):
            self._add_bundle(_read_json(path), f"base bundle {path.name}")

    # ------------------------------------------------------------- overlay load
    def _load_overlay(self):
        path = self.overlay_path
        if path is None or not path.exists():
            self.overlay_meta["path"] = str(path) if path else None
            return
        try:
            overlay = _read_json(path)
        except json.JSONDecodeError as exc:
            self._problem(f"overlay {path} is not valid JSON: {exc}")
            return
        self._schema_check(overlay, path)
        if self._problems:
            return
        origin = "curation_overlay"
        for canonical, source in overlay.get("sources", {}).items():
            self._add_source(canonical, source, origin)
        for node in overlay.get("nodes", []):
            self._add_node(node, origin)
        for edge in overlay.get("edges", []):
            self._add_edge(edge, origin)
        for disease_id, names in overlay.get("disease_synonyms", {}).items():
            if self.nodes.get(disease_id, {}).get("type") != "disease":
                self._problem(f"overlay disease_synonyms key {disease_id} is not a known disease")
                continue
            self.disease_synonyms[disease_id].extend(names)
        for asset in overlay.get("assets", []):
            if asset["id"] in self.assets and self.asset_origin[asset["id"]] == origin:
                self._problem(f"overlay asset {asset['id']} listed twice")
                continue
            for sid in asset.get("source_ids", []):
                if sid not in self.source_alias:
                    self._problem(f"overlay asset {asset['id']}: unknown source {sid}")
            for disease_id in asset.get("target_disease_ids", []):
                if self.nodes.get(disease_id, {}).get("type") != "disease":
                    self._problem(f"overlay asset {asset['id']}: unknown target disease {disease_id}")
            self.assets[asset["id"]] = copy.deepcopy(asset)
            self.asset_origin[asset["id"]] = origin
        for contact in overlay.get("contacts", []):
            if contact["id"] in self.contacts:
                self._problem(f"overlay contact {contact['id']} listed twice")
                continue
            if "@" in contact.get("url", ""):
                self._problem(f"overlay contact {contact['id']}: store a public page URL, not an email address")
            for sid in contact.get("source_ids", []):
                if sid not in self.source_alias:
                    self._problem(f"overlay contact {contact['id']}: unknown source {sid}")
            self.contacts[contact["id"]] = copy.deepcopy(contact)
        for bundle in overlay.get("assessment_bundles", []):
            self._add_bundle(bundle, origin)
        review_counts = defaultdict(int)
        for entry in overlay.get("review_log", []):
            review_counts[entry.get("review_status", "pending")] += 1
        self.overlay_meta.update({
            "loaded": True,
            "path": str(path),
            "sha256": _sha256(path),
            "coverage_note": overlay.get("coverage_note"),
            "counts": {key: len(overlay.get(key, [])) for key in
                       ("nodes", "edges", "assets", "contacts", "assessment_bundles", "review_log")},
            "review_log_status": dict(review_counts),
            "pending_edges": sum(1 for e in overlay.get("edges", []) if e.get("review_status") == "pending"),
        })

    def _schema_check(self, overlay, path):
        if self.schema_path is None:
            self.overlay_meta["merge_notes"].append("overlay schema not found; structural schema check skipped")
            return
        try:
            import jsonschema
        except ImportError:
            self.overlay_meta["merge_notes"].append("jsonschema not installed; structural schema check skipped")
            return
        schema = _read_json(self.schema_path)
        errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(overlay),
                        key=lambda err: list(err.path))
        for err in errors[:25]:
            location = "/".join(map(str, err.path)) or "(root)"
            self._problem(f"overlay {path.name} schema: {location}: {err.message}")
        self.overlay_meta["schema_checked"] = True

    def _index_edges(self):
        for edge in self.edges:
            self.out_edges[edge["source"]].append(edge)
            self.in_edges[edge["target"]].append(edge)

    # ---------------------------------------------------------------- queries
    @property
    def snapshot_commit(self):
        return self.manifest.get("snapshot_commit", "unknown")

    @property
    def data_origin(self):
        return "dismech_snapshot+curation_overlay" if self.overlay_meta["loaded"] else "dismech_snapshot"

    def disease_ids(self):
        return sorted(node_id for node_id, node in self.nodes.items() if node["type"] == "disease")

    def canonical_source(self, source_id):
        """Exact alias match first; then a case-insensitive match on the prefix."""
        if source_id in self.source_alias:
            return self.source_alias[source_id]
        lowered = source_id.strip().lower()
        for alias, canonical in self.source_alias.items():
            if alias.lower() == lowered:
                return canonical
        if not lowered.startswith("doi:") and lowered.startswith("10."):
            return self.canonical_source("DOI:" + source_id.strip())
        return None

    def source_record(self, canonical):
        record = copy.deepcopy(self.sources[canonical])
        for key in SOURCE_REQUIRED:
            record.setdefault(key, None if key == "published_on" else "")
        return record

    def sources_for(self, source_ids):
        out = {}
        for sid in source_ids:
            canonical = self.canonical_source(sid)
            if canonical:
                out[canonical] = self.source_record(canonical)
        return out

    def bundle(self, bundle_id):
        """Deep copy so no caller can mutate stored evidence."""
        return copy.deepcopy(self.bundles[bundle_id])

    def bundle_source_ids(self, bundle_id):
        return sorted(self.bundles[bundle_id].get("sources", {}).keys())

    def disease_label(self, disease_id):
        return self.nodes[disease_id]["label"]

    def disease_names(self, disease_id):
        node = self.nodes[disease_id]
        names = [node["label"], *node.get("synonyms", []), *self.disease_synonyms.get(disease_id, [])]
        for bundle in self.bundles.values():
            if bundle["target_disease"]["id"] == disease_id:
                names.append(bundle["target_disease"]["label"])
        seen, out = set(), []
        for name in names:
            key = name.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(name)
        return out

    def neighbors(self, node_id):
        for edge in self.out_edges.get(node_id, []):
            yield edge, edge["target"]
        for edge in self.in_edges.get(node_id, []):
            yield edge, edge["source"]

    # Shared ontology terms, genes and publications are hubs: walking through them
    # would associate a node with every disease that happens to share the term.
    BARRIER_TYPES = frozenset({"disease", "phenotype", "process", "function", "cell_type",
                               "anatomy", "gene", "publication"})

    def associated_diseases(self, node_id, max_depth=3):
        """Disease IDs reachable from a node without walking through a hub node.

        The start node may be any type; traversal never continues through another
        disease, ontology term, gene or publication.
        """
        node_id = self.node_alias.get(node_id, node_id)
        node = self.nodes.get(node_id)
        if node is None:
            return []
        if node["type"] == "disease":
            return [node_id]
        found, frontier, seen = set(), [node_id], {node_id}
        for _ in range(max_depth):
            nxt = []
            for current in frontier:
                for _edge, other in self.neighbors(current):
                    if other in seen:
                        continue
                    seen.add(other)
                    other_type = self.nodes[other]["type"]
                    if other_type == "disease":
                        found.add(other)
                    elif other_type not in self.BARRIER_TYPES:
                        nxt.append(other)
            frontier = nxt
        return sorted(found)

    def total_counts(self):
        return {"total_nodes": len(self.nodes), "total_edges": len(self.edges)}
