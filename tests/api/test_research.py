"""Research endpoints use injected synthetic transports, never live providers."""

from copy import deepcopy
from dataclasses import replace
import json

from fastapi.testclient import TestClient
import pytest

from rarebridge.ai.config import AIConfig
from rarebridge.ai.research import ResearchService
from rarebridge.ai.service import AIService
from rarebridge.ai.tests.test_research import synthetic_transport
from rarebridge.api.app import create_app
from rarebridge.services.ai_bridge import AIBridge
from rarebridge.services.registry import Registry


SYNGAP1 = "MONDO:0012960"
ASSESSMENT = "framework-for-syngap1"
DOI = "DOI:10.1002/epi.70374"


@pytest.fixture
def research_client(tmp_path):
    registry = Registry(overlay_path="off")
    calls = []
    config = AIConfig(api_key="SYNTHETIC_test_only", provider="anthropic", model="claude-sonnet-4-6",
                      mode="auto", cache_dir=tmp_path)
    research = ResearchService(registry, AIService(config, synthetic_transport(calls)))
    client = TestClient(create_app(registry, AIBridge(module_name="rarebridge.ai.not_connected_for_tests"), research))
    return client, research, calls


def test_discovery_is_model_generated_pending_and_never_merges(research_client):
    client, service, calls = research_client
    before = deepcopy(service.registry.edges)
    response = client.post("/api/ai/discover", json={"disease_id": SYNGAP1, "goal_id": "natural_history"})
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "rarebridge.handoff.v1"
    assert body["import_status"] == "not_imported"
    assert body["discovery"]["hypotheses"][0]["review_status"] == "pending"
    assert body["discovery"]["provider"] == "anthropic"
    assert body["discovery"]["sources"]
    assert calls == ["rarebridge_discover"]
    assert service.registry.edges == before


def test_discovery_unknown_disease_and_goal_do_not_call_model(research_client):
    client, _, calls = research_client
    assert client.post("/api/ai/discover", json={"disease_id": "MONDO:unknown"}).status_code == 404
    assert client.post("/api/ai/discover", json={"disease_id": SYNGAP1, "goal_id": "treatment"}).status_code == 422
    assert calls == []


def test_ask_preserves_current_fingerprint_and_withdrawn_sources(research_client):
    client, _, calls = research_client
    current = client.post("/api/ai/ask", json={"assessment_id": ASSESSMENT, "question": "What is supported?", "mode": "patient"})
    assert current.status_code == 200
    assert current.json()["answer"]["cited_source_ids"] == [DOI]
    hidden = client.post("/api/ai/ask", json={"assessment_id": ASSESSMENT, "question": "What is supported?",
                                             "withdrawn_source_ids": ["PMID:42446932"], "mode": "patient"})
    assert hidden.status_code == 200
    assert hidden.json()["withdrawn_source_ids"] == [DOI]
    assert hidden.json()["answer"]["cited_source_ids"] == []
    assert hidden.json()["answer"]["evidence_state"] == "insufficient_evidence"
    assert current.json()["answer"]["provenance"]["assessment_sha256"] != hidden.json()["answer"]["provenance"]["assessment_sha256"]
    assert calls == ["rarebridge_ask", "rarebridge_ask"]


def test_invalid_questions_modes_and_withdrawals_do_not_call_model(research_client):
    client, _, calls = research_client
    for payload in ({"assessment_id": ASSESSMENT, "question": "x" * 1_201},
                    {"assessment_id": ASSESSMENT, "question": "Question", "mode": "fiction"},
                    {"assessment_id": ASSESSMENT, "question": "Question", "withdrawn_source_ids": ["invented:source"]},
                    {"assessment_id": ASSESSMENT, "question": " "}):
        assert client.post("/api/ai/ask", json=payload).status_code == 422
    assert client.post("/api/ai/ask", json={"assessment_id": "missing", "question": "Question"}).status_code == 404
    assert calls == []


def test_health_uses_research_config_and_operation_caches(research_client):
    client, service, _ = research_client
    assert client.get("/api/health").json()["capabilities"]["ai_discovery"] is True
    assert client.get("/api/health").json()["capabilities"]["ai_assistant"] is True
    client.post("/api/ai/discover", json={"disease_id": SYNGAP1})
    service.ai_service.config = replace(service.ai_service.config, api_key="", mode="cache")
    caps = client.get("/api/health").json()["capabilities"]
    assert caps["ai_discovery"] is True
    assert caps["ai_assistant"] is False
    body = client.get("/api/health").json()
    assert "SYNTHETIC_test_only" not in json.dumps(body)


def test_unavailable_provider_returns_safe_503_and_cache_does_not_fake_answer(research_client):
    client, service, calls = research_client
    service.ai_service.config = replace(service.ai_service.config, api_key="", mode="cache")
    response = client.post("/api/ai/ask", json={"assessment_id": ASSESSMENT, "question": "What should we check?"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "cache_miss"
    assert calls == []


def test_invalid_model_output_is_not_accepted_or_cached(research_client):
    client, service, _ = research_client
    def bad_transport(config, messages, schema, name):
        return {"hypotheses": [{"made_up": "bad"}]}, {"provider": "anthropic", "response_id": "msg_SYNTHETIC_test_only", "model": config.model}
    service.ai_service.transport = bad_transport
    response = client.post("/api/ai/discover", json={"disease_id": SYNGAP1})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "generation_invalid"
    assert not list(service.ai_service.config.cache_dir.glob("discover-*.json"))
