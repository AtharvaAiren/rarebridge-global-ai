"""Lead/backend boundary tests with injected synthetic services only.

No .env reads, provider requests or real curation writes are made by these tests.
Synthetic AI output is confined to test modules and is never runtime cache data.
"""

import copy
import hashlib
import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

from rarebridge.ai.brief import build_collaboration_brief
from rarebridge.ai.transport import AIServiceError as LeadAIServiceError
from rarebridge.api.app import create_app
from rarebridge.services.ai_bridge import AIBridge
from rarebridge.services.registry import Registry


ANCHOR_DOI = "DOI:10.1002/epi.70374"
ANCHOR_PMID = "PMID:42446932"
ASSESSMENT = "framework-for-syngap1"
MARKER = "SYNTHETIC_PRIVATE_EXCEPTION_DO_NOT_EXPOSE"


def install_service(monkeypatch, explain, *, extract=None, capabilities=None):
    module = types.ModuleType("rarebridge_synthetic_backend_ai_test")

    async def empty_extraction(payload):
        return {"schema_version": "rarebridge.handoff.v1", "source_id": payload["source_id"],
                "generation_mode": "cached", "model": "SYNTHETIC_TEST_ONLY",
                "entities": [], "claims": [], "limitations": ["Synthetic test output."]}

    module.explain_assessment = explain
    module.extract_source = extract or empty_extraction
    module.AIServiceError = LeadAIServiceError
    if capabilities:
        module.capabilities = capabilities
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module


def client_for(module, registry=None):
    return TestClient(create_app(registry or Registry(overlay_path="off"),
                                AIBridge(module_name=module.__name__)))


def fingerprint(assessment):
    return hashlib.sha256(json.dumps(assessment, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def synthetic_explanation(assessment):
    return {
        "generation_mode": "cached", "text": "SYNTHETIC TEST explanation.",
        "model": "SYNTHETIC_TEST_ONLY", "assessment_id": assessment["assessment_id"],
        "cited_source_ids": [] if assessment["withdrawn_sources"] else [ANCHOR_DOI],
        "draft_message": "SYNTHETIC TEST draft: could we discuss the recorded open questions?",
        "check_explanations": [], "next_steps": copy.deepcopy(assessment["followup_questions"]),
        "validation": {"status": "passed", "checks": ["schema", "status_alignment",
                                                        "citation_scope", "required_followups"]},
        "provenance": {"provider": "SYNTHETIC_TEST_ONLY", "response_id": "TEST_NOT_A_PROVIDER_RESPONSE",
                       "assessment_sha256": fingerprint(assessment)},
    }


@pytest.mark.parametrize("code,status", [("upstream_quota_exhausted", 429),
                                       ("model_unavailable", 503), ("upstream_timeout", 504)])
def test_lead_safe_errors_keep_http_status_and_code(monkeypatch, code, status):
    async def explain(assessment, sources):
        raise LeadAIServiceError(code, "Safe provider failure.", status,
                                 [{"provider_code": "test_failure"}])

    client = client_for(install_service(monkeypatch, explain))
    response = client.post("/api/ai/explain", json={"assessment_id": ASSESSMENT})
    assert response.status_code == status
    assert response.json()["error"] == {"code": code, "message": "Safe provider failure.",
                                       "details": [{"provider_code": "test_failure"}]}


def test_unexpected_ai_exception_content_is_not_public(monkeypatch):
    async def explain(assessment, sources):
        raise RuntimeError(MARKER)

    response = client_for(install_service(monkeypatch, explain)).post(
        "/api/ai/explain", json={"assessment_id": ASSESSMENT})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_service_error"
    assert MARKER not in response.text


def test_health_does_not_expose_capability_exception_content(monkeypatch):
    async def explain(assessment, sources):
        return synthetic_explanation(assessment)

    def capabilities():
        raise ValueError(MARKER)

    body = client_for(install_service(monkeypatch, explain, capabilities=capabilities)).get("/api/health")
    assert body.status_code == 200
    assert body.json()["capabilities"]["ai_explanation"] is False
    assert MARKER not in body.text


def test_validated_message_and_provenance_survive_bridge_for_current_brief(monkeypatch):
    async def explain(assessment, sources):
        return synthetic_explanation(assessment)

    client = client_for(install_service(monkeypatch, explain))
    response = client.post("/api/assessments/evaluate", json={"assessment_id": ASSESSMENT}).json()
    result = client.post("/api/ai/explain", json={"assessment_id": ASSESSMENT})
    assert result.status_code == 200
    explanation = result.json()["explanation"]
    assert explanation["draft_message"].startswith("SYNTHETIC TEST")
    assert explanation["provenance"]["assessment_sha256"] == fingerprint(response["after"])
    brief = build_collaboration_brief(response, explanation=explanation)
    assert brief["draft_origin"] == "ai_service_validated"
    assert brief["draft_message"] == explanation["draft_message"]


def test_bridge_rejects_explanation_bound_to_different_assessment_state(monkeypatch):
    async def explain(assessment, sources):
        result = synthetic_explanation(assessment)
        result["provenance"]["assessment_sha256"] = "0" * 64
        return result

    response = client_for(install_service(monkeypatch, explain)).post(
        "/api/ai/explain", json={"assessment_id": ASSESSMENT})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_output_invalid"


def test_bridge_rejects_withdrawn_publication_even_through_alias(monkeypatch):
    async def explain(assessment, sources):
        result = synthetic_explanation(assessment)
        result["cited_source_ids"] = [ANCHOR_PMID]
        return result

    response = client_for(install_service(monkeypatch, explain)).post(
        "/api/ai/explain", json={"assessment_id": ASSESSMENT,
                                "withdrawn_source_ids": [ANCHOR_DOI]})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_output_invalid"


def test_recorded_use_context_is_copied_into_assessment_and_ai_fingerprint(monkeypatch):
    registry = Registry(overlay_path="off")
    context = {"proposed_use": "SYNTHETIC scoped project.",
               "target_subgroup": {"description": "SYNTHETIC proposed cohort."},
               "documented_differences": [], "assumptions": ["SYNTHETIC local-capacity assumption."]}
    registry.bundles[ASSESSMENT].update(copy.deepcopy(context))
    received = []

    async def explain(assessment, sources):
        received.append(copy.deepcopy(assessment))
        return synthetic_explanation(assessment)

    client = client_for(install_service(monkeypatch, explain), registry)
    result = client.post("/api/assessments/evaluate", json={"assessment_id": ASSESSMENT}).json()
    for key, value in context.items():
        assert result["before"][key] == result["after"][key] == value
    ai_result = client.post("/api/ai/explain", json={"assessment_id": ASSESSMENT})
    assert ai_result.status_code == 200
    assert received[0] == result["after"]
    assert ai_result.json()["explanation"]["provenance"]["assessment_sha256"] == fingerprint(result["after"])
    assert registry.bundles[ASSESSMENT]["target_subgroup"] == context["target_subgroup"]


def test_known_publication_alias_is_canonicalized_before_extraction(monkeypatch):
    received = []

    async def explain(assessment, sources):
        return synthetic_explanation(assessment)

    async def extract(payload):
        received.append(copy.deepcopy(payload))
        return {"schema_version": "rarebridge.handoff.v1", "source_id": payload["source_id"],
                "generation_mode": "cached", "model": "SYNTHETIC_TEST_ONLY",
                "entities": [], "claims": [], "limitations": ["Synthetic test output."]}

    client = client_for(install_service(monkeypatch, explain, extract=extract))
    response = client.post("/api/ai/extract", json={"source_id": ANCHOR_PMID,
        "title": "Synthetic input", "url": "https://example.org/source", "text": "Synthetic excerpt."})
    assert response.status_code == 200
    assert received[0]["source_id"] == ANCHOR_DOI
    assert response.json()["requested_source_id"] == ANCHOR_PMID
    assert response.json()["extraction"]["source_id"] == ANCHOR_DOI
    assert response.json()["import_status"] == "not_imported"
