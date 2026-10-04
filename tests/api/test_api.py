"""Consequential API and data-contract checks for the backend lane.

Run from the repository root:
    python -m pytest tests/api -q

Tests that need a modified overlay write a temporary copy; the real
curation/atlas-overlay.json is never edited. Simulated sign-offs are labelled
SYNTHETIC and assert software behavior only, not any biomedical fact.
"""

import copy
import json
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rarebridge.api.app import create_app
from rarebridge.services.ai_bridge import AIBridge
from rarebridge.services.registry import DEFAULT_OVERLAY, DataError, Registry

ROOT = Path(__file__).resolve().parents[2]
STXBP1, SYNGAP1, SCN2A = "MONDO:0012812", "MONDO:0012960", "MONDO:0013388"
ANCHOR_DOI, ANCHOR_PMID = "DOI:10.1002/epi.70374", "PMID:42446932"
HAS_OVERLAY = DEFAULT_OVERLAY.exists()
needs_overlay = pytest.mark.skipif(not HAS_OVERLAY, reason="curation/atlas-overlay.json not present")


def client_for(overlay_path=None, ai_module="rarebridge.ai.service_not_installed_for_tests"):
    return TestClient(create_app(Registry(overlay_path=overlay_path), AIBridge(module_name=ai_module)))


@pytest.fixture(scope="module")
def client():
    return client_for(None)


@pytest.fixture(scope="module")
def base_client():
    return client_for("off")


def evaluate(client, assessment_id, withdrawn=()):
    response = client.post("/api/assessments/evaluate",
                           json={"assessment_id": assessment_id, "withdrawn_source_ids": list(withdrawn)})
    return response


def check(result, check_id):
    return next(row for row in result["checks"] if row["id"] == check_id)


def overlay_copy(tmp_path, mutate):
    data = json.loads(DEFAULT_OVERLAY.read_text())
    mutate(data)
    path = tmp_path / "overlay.json"
    path.write_text(json.dumps(data))
    return path


# ----------------------------------------------------------------- health
def test_health_reports_actual_capabilities(client, base_client):
    body = client.get("/api/health").json()
    assert body["schema_version"] == "rarebridge.handoff.v1"
    assert body["capabilities"]["curation_overlay"] is HAS_OVERLAY
    assert body["capabilities"]["ai_extraction"] is False
    assert body["capabilities"]["ai_explanation"] is False
    assert body["data_snapshot"] == "3426c0eec2ade9297b6aadefe95e5dc7cd3806e6"
    assert base_client.get("/api/health").json()["capabilities"]["curation_overlay"] is False


# ----------------------------------------------------------------- search
def test_real_disease_search_resolves_stable_ids(client):
    body = client.get("/api/search", params={"q": "syngap1"}).json()
    assert body["items"][0]["id"] == SYNGAP1 and body["items"][0]["type"] == "disease"
    gene = next(item for item in body["items"] if item["type"] == "gene")
    assert gene["id"] == "hgnc:11497" and gene["disease_ids"] == [SYNGAP1]


def test_unmatched_query_is_honest_empty_result(client):
    response = client.get("/api/search", params={"q": "not-in-this-slice"})
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [] and body["coverage"]["disease_count"] == 3
    assert "not" in body["coverage"]["scope_note"].lower()


def test_non_disease_search_returns_disease_ids_for_the_journey(client):
    for query, expected in [("STXBP1", STXBP1), ("Nav1.2", SCN2A), ("chemical synaptic transmission", STXBP1)]:
        items = client.get("/api/search", params={"q": query}).json()["items"]
        assert any(expected in item["disease_ids"] for item in items if item["type"] != "disease"), query


@needs_overlay
def test_organization_and_study_alias_search(client):
    org = client.get("/api/search", params={"q": "STXBP1 Foundation"}).json()["items"][0]
    assert org["id"] == "org:stxbp1-foundation" and org["disease_ids"] == [STXBP1]
    study = client.get("/api/search", params={"q": "PRoMiSS"}).json()["items"][0]
    assert study["id"] == "study:prommis" and study["disease_ids"] == [SYNGAP1]


def test_exact_ids_are_matched_and_never_rewritten(client):
    item = client.get("/api/search", params={"q": "mondo:0012812"}).json()["items"][0]
    assert item["id"] == STXBP1


def test_search_limit_is_clamped(client):
    assert len(client.get("/api/search", params={"q": "seizure", "limit": 500}).json()["items"]) <= 25
    assert len(client.get("/api/search", params={"q": "seizure", "limit": 0}).json()["items"]) == 1


# ---------------------------------------------------------------- overview
@needs_overlay
def test_syngap1_overview_has_recorded_route_to_stxbp1_and_its_community(client):
    body = client.get(f"/api/diseases/{SYNGAP1}/overview").json()
    related = {item["id"]: item for item in body["related_diseases"]}
    assert body["related_diseases"][0]["id"] == STXBP1
    route = related[STXBP1]
    assert route["relation_kind"] == "published_co_study"
    assert ANCHOR_DOI in route["source_ids"]
    assert "not shared biology" in route["reason"]
    overlay = json.loads(DEFAULT_OVERLAY.read_text())
    edge = next(e for e in overlay["edges"] if e["id"] == "edge:overlay:syngap1-stxbp1-shared-framework")
    assert route["review_status"] == edge["review_status"]   # follows the person's sign-off, never ahead of it
    assert "org:stxbp1-foundation" in [org["id"] for org in route["organizations"]]
    assert related[SCN2A]["relation_kind"] == "shared_upstream_annotations"
    assert related[SCN2A]["candidate_score"] < 1 and related[SCN2A]["basis_claim_ids"]
    assessments = [opp["assessment_id"] for opp in body["opportunities"]]
    assert "framework-for-syngap1" in assessments and "citizen-dataset-for-syngap1" in assessments
    assert all(opp["candidate_score"] is None for opp in body["opportunities"])
    assert "org:cure-syngap1" in [c["id"] for c in body["organizations"]]


@needs_overlay
def test_assessment_scope_includes_target_disease(client):
    body = client.get(f"/api/diseases/{STXBP1}/overview").json()
    assessments = [opp["assessment_id"] for opp in body["opportunities"]]
    assert assessments == ["framework-for-stxbp1"]
    assert "framework-for-syngap1" not in json.dumps(body["opportunities"])


def test_missing_target_bundle_is_a_reported_gap_not_a_substitute(base_client):
    body = base_client.get(f"/api/diseases/{STXBP1}/overview").json()
    assert body["opportunities"] == []
    gaps = " ".join(body["coverage"]["gaps"])
    assert "framework-for-syngap1" in gaps and "not substituted" in gaps


def test_scn2a_keeps_unknown_target_evidence(client):
    body = client.get(f"/api/diseases/{SCN2A}/overview").json()
    opp = next(o for o in body["opportunities"] if o["assessment_id"] == "framework-for-scn2a")
    assert "target-observed" in opp["open_required_check_ids"]
    result = evaluate(client, "framework-for-scn2a").json()["before"]
    assert check(result, "target-observed")["status"] == "unknown"
    assert result["outcome"] == "needs_information"


def test_overview_errors_use_the_envelope(client):
    missing = client.get("/api/diseases/MONDO:0000000/overview")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "unknown_disease"
    bad_goal = client.get(f"/api/diseases/{SYNGAP1}/overview", params={"goal": "treatment"})
    assert bad_goal.status_code == 422 and bad_goal.json()["error"]["code"] == "unknown_goal"


# --------------------------------------------------------------- assessment
def test_empty_withdrawal_returns_identical_before_and_after(client):
    body = evaluate(client, "framework-for-syngap1").json()
    assert body["before"] == body["after"] and body["changed_checks"] == []
    assert body["before"]["outcome"] == "needs_information"
    assert body["explanation"] == {"generation_mode": "none", "text": None, "cited_source_ids": [], "model": None}
    assert ANCHOR_DOI in body["sources"] and ANCHOR_PMID in body["sources"][ANCHOR_DOI]["aliases"]


def test_doi_and_pmid_withdrawal_remove_the_same_paper(client):
    by_pmid = evaluate(client, "framework-for-syngap1", [ANCHOR_PMID]).json()
    by_doi = evaluate(client, "framework-for-syngap1", [ANCHOR_DOI]).json()
    assert by_pmid["after"]["checks"] == by_doi["after"]["checks"]
    assert by_pmid["after"]["withdrawn_sources"] == [ANCHOR_DOI]
    assert {c["check_id"] for c in by_pmid["changed_checks"]} == {"documented-framework", "target-observed"}
    assert by_pmid["after"]["outcome"] == by_pmid["before"]["outcome"] == "needs_information"


def test_withdrawal_and_reset_are_nondestructive(client):
    stored = copy.deepcopy(client.app.state.services.registry.bundles["framework-for-syngap1"])
    original = evaluate(client, "framework-for-syngap1").json()["before"]
    evaluate(client, "framework-for-syngap1", [ANCHOR_PMID])
    reset = evaluate(client, "framework-for-syngap1", []).json()
    assert reset["after"] == original
    assert client.app.state.services.registry.bundles["framework-for-syngap1"] == stored


def test_invalid_withdrawal_and_unknown_assessment(client):
    bad = evaluate(client, "framework-for-syngap1", ["PMID:00000000"])
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_withdrawal"
    assert bad.json()["error"]["details"]
    missing = evaluate(client, "no-such-assessment")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "unknown_assessment"


@needs_overlay
def test_known_source_not_cited_by_this_assessment_is_ignored_not_rejected(client):
    body = evaluate(client, "framework-for-syngap1", ["WEB:stxbp1-foundation-starr"]).json()
    assert body["changed_checks"] == []
    assert body["withdrawn_source_ids_ignored"][0]["canonical_id"] == "WEB:stxbp1-foundation-starr"


@needs_overlay
def test_pending_overlay_evidence_stays_pending(tmp_path):
    """SYNTHETIC: resets a temp copy to unsigned, so this holds before and after real sign-off."""
    def unsign_everything(data):
        for entry in data["review_log"]:
            entry["review_status"] = "pending"
        for bundle in data["assessment_bundles"]:
            for chk in bundle["checks"]:
                for item in chk["evidence"]:
                    item["review_status"] = "pending"
        for edge in data["edges"]:
            edge.update(review_status="pending", confidence_label="Unassessed \u2014 source review pending")
    unsigned = client_for(overlay_copy(tmp_path, unsign_everything))
    for assessment_id in ("framework-for-stxbp1", "citizen-dataset-for-syngap1"):
        result = evaluate(unsigned, assessment_id).json()["before"]
        assert result["outcome"] == "needs_source_review"
        assert all(row["supporting_sources"] == [] for row in result["checks"])
    route = unsigned.get(f"/api/diseases/{SYNGAP1}/overview").json()["related_diseases"][0]
    assert route["review_status"] == "pending"


@needs_overlay
def test_simulated_signoff_moves_overlay_assessments_to_needs_information(tmp_path):
    """SYNTHETIC: marks every overlay item source_checked in a temp copy to test the engine path."""
    def sign_everything(data):
        for entry in data["review_log"]:
            entry.update(review_status="source_checked", checked_by="SYNTHETIC TEST, not a review")
        for bundle in data["assessment_bundles"]:
            for chk in bundle["checks"]:
                for item in chk["evidence"]:
                    item["review_status"] = "source_checked"
        for edge in data["edges"]:
            edge.update(review_status="source_checked", confidence_label="Source checked (SYNTHETIC)")
    signed = client_for(overlay_copy(tmp_path, sign_everything))
    for assessment_id in ("framework-for-stxbp1", "citizen-dataset-for-syngap1"):
        assert evaluate(signed, assessment_id).json()["before"]["outcome"] == "needs_information"
    route = signed.get(f"/api/diseases/{SYNGAP1}/overview").json()["related_diseases"][0]
    assert route["id"] == STXBP1 and route["review_status"] == "source_checked"


@needs_overlay
def test_contacts_are_public_routes_with_review_status(client):
    body = evaluate(client, "framework-for-stxbp1").json()
    ids = [c["id"] for c in body["contacts"]]
    assert ids[0] == "org:stxbp1-foundation" and "org:cure-syngap1" not in ids
    for contact in body["contacts"]:
        assert "@" not in contact["url"] and contact["review_status"] in ("pending", "source_checked")
    scn2a = evaluate(client, "framework-for-scn2a").json()["contacts"]
    assert {c["id"] for c in scn2a} == {"researcher:ingo-helbig", "researcher:jillian-mckee"}


# -------------------------------------------------------------------- graph
@pytest.mark.parametrize("params", [
    {"disease_id": SYNGAP1}, {"disease_id": STXBP1, "assessment_id": "framework-for-stxbp1"},
    {"assessment_id": "framework-for-scn2a"}, {"disease_id": SYNGAP1, "max_nodes": 8},
])
def test_graph_edges_have_provenance_and_valid_endpoints(client, params):
    if "framework-for-stxbp1" in params.values() and not HAS_OVERLAY:
        pytest.skip("overlay bundle")
    body = client.get("/api/graph", params=params).json()
    node_ids = {node["id"] for node in body["nodes"]}
    assert len(body["nodes"]) <= params.get("max_nodes", 40)
    assert body["coverage"]["total_nodes"] >= len(body["nodes"])
    for edge in body["edges"]:
        assert edge["source"] in node_ids and edge["target"] in node_ids
        assert edge["provenance"]["source_url"] and edge["review_status"] in ("pending", "source_checked")
        assert edge["source_ids"] and edge["confidence_label"] and edge["explanation"]
        assert edge["relation"] not in {"can_share_treatment", "can_reuse_asset", "eligible_for_trial", "treats"}
        if edge["claim_origin"] == "imported":
            assert edge["review_status"] == "pending"
            assert edge["confidence_label"] == "Unassessed \u2014 source review pending"
        for sid in edge["source_ids"]:
            assert sid in body["sources"] or any(sid in s["aliases"] for s in body["sources"].values())


def test_graph_reports_truncation_and_errors(client):
    small = client.get("/api/graph", params={"disease_id": SYNGAP1, "max_nodes": 8}).json()
    assert small["coverage"]["truncated"] is True and small["coverage"]["omitted_relevant_nodes"] > 0
    assert client.get("/api/graph", params={"disease_id": "MONDO:1"}).status_code == 404
    assert client.get("/api/graph").status_code == 422


def test_graph_with_assessment_includes_asset_and_scope(base_client):
    body = base_client.get("/api/graph", params={"assessment_id": "framework-for-syngap1"}).json()
    ids = {node["id"] for node in body["nodes"]}
    assert "DOI:10.1002/epi.70374#framework" in ids
    scope = next(e for e in body["edges"] if e["relation"] == "assessment_scope")
    assert scope["source"] == SYNGAP1 and "not an approval" in scope["confidence_label"]


# ------------------------------------------------------------------ sources
@pytest.mark.parametrize("path", ["DOI:10.1002/epi.70374", "DOI%3A10.1002%2Fepi.70374", "PMID%3A42446932"])
def test_source_paths_with_slash_and_aliases_resolve(client, path):
    body = client.get(f"/api/sources/{path}")
    assert body.status_code == 200 and body.json()["canonical_id"] == ANCHOR_DOI


def test_unknown_source_is_404(client):
    response = client.get("/api/sources/DOI%3A10.9999%2Fnope")
    assert response.status_code == 404 and response.json()["error"]["code"] == "unknown_source"


# ------------------------------------------------------------------ overlay
def test_missing_overlay_file_does_not_prevent_startup(tmp_path):
    body = client_for(tmp_path / "absent.json").get("/api/health").json()
    assert body["status"] == "ok" and body["capabilities"]["curation_overlay"] is False


@needs_overlay
def test_conflicting_source_alias_is_rejected_clearly(tmp_path):
    def hijack_alias(data):
        data["sources"]["DOI:10.0000/conflict"] = {
            "title": "conflict", "url": "https://example.org/x", "aliases": [ANCHOR_PMID],
            "published_on": None, "source_kind": "test", "note": "SYNTHETIC"}
    with pytest.raises(DataError, match="PMID:42446932"):
        Registry(overlay_path=overlay_copy(tmp_path, hijack_alias))


@needs_overlay
def test_node_type_collision_and_duplicate_assessment_are_rejected(tmp_path):
    def collide(data):
        data["nodes"].append({"id": SYNGAP1, "type": "gene", "label": "wrong type"})
        data["assessment_bundles"].append(copy.deepcopy(data["assessment_bundles"][0]))
    with pytest.raises(DataError) as info:
        Registry(overlay_path=overlay_copy(tmp_path, collide))
    text = str(info.value)
    assert SYNGAP1 in text and "framework-for-stxbp1" in text


# ----------------------------------------------------------------------- AI
def test_ai_endpoints_report_model_unavailable(client):
    response = client.post("/api/ai/explain", json={"assessment_id": "framework-for-syngap1"})
    assert response.status_code == 503 and response.json()["error"]["code"] == "model_unavailable"
    response = client.post("/api/ai/extract", json={"source_id": ANCHOR_DOI, "title": "t", "url": "https://x",
                                                    "text": "body"})
    assert response.status_code == 503


def test_ai_explanation_is_wired_and_validated_when_a_service_exists(monkeypatch):
    fake = types.ModuleType("rarebridge_fake_ai_for_tests")

    async def explain_assessment(assessment, sources):
        return {"generation_mode": "live", "text": "SYNTHETIC test text.", "model": "fake",
                "cited_source_ids": sorted(sources)}

    async def extract_source(payload):
        return {}

    fake.explain_assessment, fake.extract_source = explain_assessment, extract_source
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    client = client_for("off", ai_module=fake.__name__)
    assert client.get("/api/health").json()["capabilities"]["ai_explanation"] is True
    body = client.post("/api/ai/explain", json={"assessment_id": "framework-for-syngap1"}).json()
    assert body["explanation"]["generation_mode"] == "live" and body["explanation"]["model"] == "fake"
    invalid = client.post("/api/ai/extract", json={"source_id": ANCHOR_DOI, "title": "t", "url": "https://x",
                                                   "text": "body"})
    assert invalid.status_code == 502 and invalid.json()["error"]["code"] == "ai_output_invalid"


# --------------------------------------------------------------- data hygiene
def test_runtime_code_never_reads_heldout_evaluation_cases():
    for folder in ("rarebridge/api", "rarebridge/services"):
        for path in (ROOT / folder).glob("*.py"):
            text = path.read_text()
            assert "heldout" not in text and "evaluation/" not in text, path
