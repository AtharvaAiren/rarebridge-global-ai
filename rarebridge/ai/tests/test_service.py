"""Offline integration tests. Simulated provider outputs never become demo data."""

import asyncio
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib import error

from rarebridge.assessment import assess
from rarebridge.ai.brief import build_collaboration_brief
from rarebridge.ai.config import AIConfig, WORKSPACE_ROOT, load_config, read_dotenv
from rarebridge.ai.contracts import explanation_context, explanation_generation_schema, bind_explanation_selection
from rarebridge.ai.preview import build_graph_preview
from rarebridge.ai.service import AIService, AIServiceError, capabilities
from rarebridge.ai.transport import _NoRedirect, structured_response


SOURCE = {
    "source_id": "URL:https://example.org/public-source", "title": "Synthetic test source",
    "url": "https://example.org/public-source", "published_on": None,
    "text": "SYNGAP1 is studied using a synthetic research framework.",
}


def extraction_raw(messages):
    source = json.loads(messages[1]["content"])["source_data"]
    return {
        "entities": [{"id": "candidate:test-framework", "type": "asset", "label": "Synthetic test framework"}],
        "claims": [{
            "id": "candidate:test-claim", "subject_id": "hgnc:11497", "relation": "uses_resource",
            "object_id": "candidate:test-framework", "source_id": source["source_id"],
            "source_location": "supplied excerpt", "source_excerpt": source["text"],
            "rationale": "The supplied synthetic test sentence mentions the framework.",
            "review_status": "pending", "evidence_type": "source_statement",
            "qualifiers": {"variant": None, "experimental_context": None, "proposed_use": None},
        }], "limitations": ["Synthetic software test input; no biomedical assertion."],
    }


def explanation_raw(messages):
    context = json.loads(messages[1]["content"])["assessment_data"]
    rows = []
    for check in context["checks"]:
        rows.append({
            "check_id": check["id"], "explanation": "Recorded check: " + check["question"],
        })
    return {
        "summary": "This proposed research use needs review and clarification.",
        "check_explanations": rows,
        "draft_message": "Dear research team, could we discuss the recorded open questions before deciding whether this resource fits our proposed study?",
    }


class FakeTransport:
    """A mock used only within isolated temporary test directories."""
    def __init__(self):
        self.calls = []

    def __call__(self, config, messages, schema, name):
        self.calls.append(name)
        output = extraction_raw(messages) if name.endswith("extract") else explanation_raw(messages)
        return output, {"provider": "openai", "response_id": "resp_SYNTHETIC_UNIT_TEST_ONLY",
                        "model": config.model, "request_id": "test-only", "usage": {}}


class ConfigTests(unittest.TestCase):
    def test_literal_dotenv_and_export_precedence_keep_secret_out_of_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('OPENAI_API_KEY="secret-test-only"\nRAREBRIDGE_AI_MODE=cache\nUNKNOWN=$(touch unsafe)\n', encoding="utf-8")
            config = load_config({"OPENAI_API_KEY": ""}, path)
            self.assertEqual(config.api_key, "")
            self.assertEqual(config.mode, "cache")
            self.assertNotIn("UNKNOWN", read_dotenv(path))
            self.assertNotIn("secret-test-only", repr(config))
            self.assertNotIn("secret-test-only", json.dumps(config.diagnostics()))

    def test_shell_syntax_in_value_is_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("OPENAI_API_KEY=$(touch should-not-exist)\n", encoding="utf-8")
            self.assertEqual(read_dotenv(path)["OPENAI_API_KEY"], "$(touch should-not-exist)")
            self.assertFalse((Path(directory) / "should-not-exist").exists())

    def test_bad_timeout_mode_and_output_bounds_are_rejected(self):
        for values in ({"RAREBRIDGE_AI_MODE": "mock"}, {"RAREBRIDGE_AI_TIMEOUT_SECONDS": "nan"},
                       {"RAREBRIDGE_AI_MAX_OUTPUT_TOKENS": "100000"}):
            with self.assertRaises(ValueError):
                load_config(values, Path("/nonexistent-rarebridge-env"))


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = AIConfig("test-key-not-real", mode="live", cache_dir=Path(self.directory.name))
        self.transport = FakeTransport()
        self.service = AIService(self.config, self.transport)
        self.bundle = json.loads((WORKSPACE_ROOT / "rarebridge/data/assessment-syngap1.json").read_text())

    async def test_known_endpoint_is_enriched_for_complete_pending_preview(self):
        result = await self.service.extract_source(SOURCE)
        self.assertEqual(result["generation_mode"], "live")
        self.assertIn("hgnc:11497", {item["id"] for item in result["entities"]})
        preview = build_graph_preview(result)
        nodes = {item["id"] for item in preview["nodes"]}
        self.assertTrue(all(edge["source"] in nodes and edge["target"] in nodes for edge in preview["edges"]))
        self.assertTrue(all(edge["review_status"] == "pending" for edge in preview["edges"]))

    async def test_matching_cache_replay_uses_no_transport_and_retains_provenance(self):
        live = await self.service.extract_source(SOURCE)
        cache_service = AIService(replace(self.config, api_key="", mode="cache"), self.transport)
        cached = await cache_service.extract_source(SOURCE)
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(cached["generation_mode"], "cached")
        self.assertEqual(live["provenance"]["response_id"], cached["provenance"]["response_id"])
        self.assertEqual(live["provenance"]["source_sha256"], cached["provenance"]["source_sha256"])

    async def test_changed_source_cannot_reuse_old_extraction(self):
        await self.service.extract_source(SOURCE)
        cache_service = AIService(replace(self.config, api_key="", mode="cache"), self.transport)
        changed = dict(SOURCE, text=SOURCE["text"] + " Additional context.")
        with self.assertRaises(AIServiceError) as caught:
            await cache_service.extract_source(changed)
        self.assertEqual(caught.exception.code, "cache_miss")
        self.assertEqual(len(self.transport.calls), 1)

    async def test_withdrawal_requires_its_own_explanation_cache_and_brief(self):
        before = assess(self.bundle)
        generated = await self.service.explain_assessment(before, self.bundle["sources"])
        after = assess(self.bundle, ["PMID:42446932"])
        cache_service = AIService(replace(self.config, api_key="", mode="cache"), self.transport)
        with self.assertRaises(AIServiceError) as caught:
            await cache_service.explain_assessment(after, self.bundle["sources"])
        self.assertEqual(caught.exception.code, "cache_miss")
        withdrawn = await self.service.explain_assessment(after, self.bundle["sources"])
        self.assertEqual(withdrawn["cited_source_ids"], [])
        brief = build_collaboration_brief({"after": after, "sources": self.bundle["sources"], "contacts": [],
                                          "coverage": self.bundle["coverage"], "explanation": withdrawn})
        self.assertEqual(brief["provenance"]["generation_mode"], "live")
        self.assertEqual(before["outcome"], after["outcome"])
        self.assertTrue(generated["cited_source_ids"])

    async def test_explanation_binds_ledger_fields_and_keyless_cache_idempotently(self):
        assessment = assess(self.bundle)
        result = await self.service.explain_assessment(assessment, self.bundle["sources"])
        cached = await AIService(replace(self.config, api_key="", mode="cache"), self.transport).explain_assessment(
            assessment, self.bundle["sources"])
        context = explanation_context(assessment, self.bundle["sources"])
        expected = {row["id"]: row for row in context["checks"]}
        for row in result["check_explanations"]:
            self.assertEqual(row["status"], expected[row["check_id"]]["status"])
            self.assertEqual(row["source_ids"], expected[row["check_id"]]["allowed_source_ids"])
        self.assertEqual(result["next_steps"], context["required_next_steps"])
        self.assertEqual(cached["next_steps"], result["next_steps"])
        self.assertEqual(cached["check_explanations"], result["check_explanations"])
        self.assertEqual(cached["provenance"]["response_id"], result["provenance"]["response_id"])
        self.assertEqual(cached["generation_mode"], "cached")
        self.assertEqual(len(self.transport.calls), 1)
        record = json.loads(next(Path(self.directory.name).glob("explain-*.json")).read_text())
        self.assertEqual(set(record["output"]), {"summary", "check_explanations", "draft_message"})
        self.assertEqual(set(record["output"]["check_explanations"][0]), {"check_id", "explanation"})

    def test_explanation_generation_schema_has_exact_ids_and_no_authored_ledger_fields(self):
        assessment = assess(self.bundle)
        schema = explanation_generation_schema(assessment, self.bundle["sources"])
        self.assertEqual(set(schema["properties"]), {"summary", "check_explanations", "draft_message"})
        item = schema["properties"]["check_explanations"]["items"]
        self.assertEqual(set(item["properties"]), {"check_id", "explanation"})
        self.assertEqual(item["properties"]["check_id"]["enum"], [row["id"] for row in assessment["checks"]])
        self.assertIs(item["additionalProperties"], False)

    async def test_hidden_explanation_bound_sources_empty_and_required_steps_exact(self):
        assessment = assess(self.bundle, ["PMID:42446932"])
        result = await self.service.explain_assessment(assessment, self.bundle["sources"])
        context = explanation_context(assessment, self.bundle["sources"])
        self.assertEqual(result["cited_source_ids"], [])
        self.assertTrue(all(row["source_ids"] == [] and row["status"] == "unknown"
                            for row in result["check_explanations"]))
        self.assertEqual(result["next_steps"], context["required_next_steps"])
        self.assertEqual(result["provenance"]["source_binding"], "reviewed_active_sources_of_recorded_checks")

    async def test_explanation_selection_guard_rejects_missing_ids_and_hidden_publication_prose(self):
        assessment = assess(self.bundle, ["PMID:42446932"])
        for change, diagnostic in (("missing", "explanation_check_coverage"),
                                   ("hidden_publication", "unavailable_prose_publication")):
            def bad(config, messages, schema, name):
                output, metadata = self.transport(config, messages, schema, name)
                if change == "missing":
                    output["check_explanations"].pop()
                else:
                    output["summary"] = "Reference DOI:10.1002/epi.70374 remains available."
                return output, metadata
            with self.assertRaises(AIServiceError) as caught:
                await AIService(self.config, bad).explain_assessment(assessment, self.bundle["sources"])
            self.assertEqual(caught.exception.details, [{"validation_check": diagnostic, "operation": "explain"}])
            self.assertFalse(list(Path(self.directory.name).glob("explain-*.json")))

    async def test_model_cannot_promote_claim_or_cache_invalid_output(self):
        def bad(config, messages, schema, name):
            output, metadata = self.transport(config, messages, schema, name)
            output["claims"][0]["review_status"] = "source_checked"
            return output, metadata
        with self.assertRaises(AIServiceError) as caught:
            await AIService(self.config, bad).extract_source(SOURCE)
        self.assertEqual(caught.exception.code, "generation_invalid")
        self.assertEqual(list(Path(self.directory.name).glob("*.json")), [])

    async def test_fabricated_quote_is_not_accepted_or_cached(self):
        def bad(config, messages, schema, name):
            output, metadata = self.transport(config, messages, schema, name)
            output["claims"][0]["source_excerpt"] = "A quote not present in the source."
            return output, metadata
        with self.assertRaises(AIServiceError) as caught:
            await AIService(self.config, bad).extract_source(SOURCE)
        self.assertEqual(caught.exception.code, "generation_invalid")
        self.assertEqual(caught.exception.details, [{"validation_check": "literal_source_excerpt", "operation": "extract"}])
        self.assertNotIn("A quote not present", json.dumps(caught.exception.to_dict()))
        self.assertFalse(list(Path(self.directory.name).glob("*.json")))

    async def test_caller_identity_hints_cannot_redefine_existing_genes(self):
        for hint in (
            {"id": "candidate:fake-syngap", "type": "gene", "label": "SYNGAP1"},
            {"id": "hgnc:11497", "type": "asset", "label": "SYNGAP1"},
            {"id": "HGNC:999999", "type": "gene", "label": "Invented gene"},
        ):
            with self.assertRaises(AIServiceError) as caught:
                await self.service.extract_source(dict(SOURCE, known_entities=[hint]))
            self.assertEqual(caught.exception.code, "invalid_input")
        self.assertEqual(self.transport.calls, [])

    async def test_known_source_alias_is_canonicalized_before_generation(self):
        result = await self.service.extract_source(dict(SOURCE, source_id="PMID:42446932"))
        self.assertEqual(result["source_id"], "DOI:10.1002/epi.70374")
        self.assertEqual(result["claims"][0]["source_id"], "DOI:10.1002/epi.70374")
        self.assertEqual(result["provenance"]["supplied_source_id"], "PMID:42446932")

    async def test_no_key_and_disabled_modes_return_clear_unavailable(self):
        for config in (replace(self.config, api_key="", mode="auto"), replace(self.config, mode="off")):
            with self.assertRaises(AIServiceError) as caught:
                await AIService(config, self.transport).extract_source(SOURCE)
            self.assertEqual(caught.exception.code, "model_unavailable")
            self.assertNotIn("test-key", str(caught.exception.to_dict()))
        self.assertEqual(self.transport.calls, [])

    async def test_model_status_rewrite_fails_without_changing_assessment(self):
        assessment = assess(self.bundle)
        old = deepcopy(assessment)
        def bad(config, messages, schema, name):
            output, metadata = self.transport(config, messages, schema, name)
            output["check_explanations"][-2]["status"] = "supported"
            return output, metadata
        with self.assertRaises(AIServiceError) as caught:
            await AIService(self.config, bad).explain_assessment(assessment, self.bundle["sources"])
        self.assertEqual(caught.exception.code, "generation_invalid")
        self.assertEqual(assessment, old)

    async def test_untrusted_or_corrupted_cache_is_never_replayed(self):
        await self.service.extract_source(SOURCE)
        path = next(Path(self.directory.name).glob("extract-*.json"))
        record = json.loads(path.read_text())
        record["provenance"]["provider"] = "fabricated"
        path.write_text(json.dumps(record))
        with self.assertRaises(AIServiceError) as caught:
            await AIService(replace(self.config, mode="cache"), self.transport).extract_source(SOURCE)
        self.assertEqual(caught.exception.code, "cache_invalid")

    async def test_malformed_matching_cache_provenance_returns_safe_error(self):
        await self.service.extract_source(SOURCE)
        path = next(Path(self.directory.name).glob("extract-*.json"))
        record = json.loads(path.read_text())
        record["provenance"] = []
        path.write_text(json.dumps(record))
        with self.assertRaises(AIServiceError) as caught:
            await AIService(replace(self.config, mode="cache"), self.transport).extract_source(SOURCE)
        self.assertEqual(caught.exception.code, "cache_invalid")

    def test_capabilities_ignore_malformed_cache_and_never_report_a_key(self):
        (Path(self.directory.name) / "extract-bad.json").write_text("[]")
        (Path(self.directory.name) / "explain-bad.json").write_text('{"provenance":[]}')
        with patch("rarebridge.ai.service.load_config", return_value=replace(self.config, api_key="")):
            result = capabilities()
        self.assertFalse(result["ai_extraction"])
        self.assertFalse(result["ai_explanation"])
        self.assertNotIn("test-key", json.dumps(result))


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.config = AIConfig("secret-transport-test")

    def _response(self, provider):
        response = io.BytesIO(json.dumps(provider).encode())
        response.headers = {"x-request-id": "req-test"}
        return response

    def test_official_request_is_strict_nonstored_and_parses_responses_envelope(self):
        provider = {"id": "resp_test", "model": self.config.model, "status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": '{"test":true}'}]},
        ]}
        with patch("rarebridge.ai.transport.request.build_opener") as builder:
            builder.return_value.open.return_value = self._response(provider)
            output, metadata = structured_response(self.config, [{"role": "user", "content": "test"}], {"type": "object"}, "test")
        req = builder.return_value.open.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(req.full_url, "https://api.openai.com/v1/responses")
        self.assertFalse(body["store"])
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(output, {"test": True})
        self.assertEqual(metadata["response_id"], "resp_test")
        self.assertNotIn("secret-transport-test", json.dumps(metadata))
        self.assertIsNone(_NoRedirect().redirect_request(req, None, 302, "redirect", {}, "https://elsewhere.example"))

    def test_refusal_incomplete_and_invalid_json_are_clear_errors(self):
        cases = [
            ({"id": "resp_test", "status": "incomplete", "output": []}, "model_incomplete"),
            ({"id": "resp_test", "status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "test"}]}]}, "model_refused"),
            ({"id": "resp_test", "status": "completed", "output": []}, "generation_invalid"),
        ]
        for provider, expected in cases:
            with patch("rarebridge.ai.transport.request.build_opener") as builder:
                builder.return_value.open.return_value = self._response(provider)
                with self.assertRaises(AIServiceError) as caught:
                    structured_response(self.config, [], {}, "test")
            self.assertEqual(caught.exception.code, expected)

    def test_malformed_nested_provider_envelopes_return_safe_error(self):
        for output in (None, [None], [{"type": "message", "content": None}],
                       [{"type": "message", "content": [None]}],
                       [{"type": "message", "content": [{"type": "output_text", "text": []}]}]):
            provider = {"id": "resp_test", "status": "completed", "output": output}
            with patch("rarebridge.ai.transport.request.build_opener") as builder:
                builder.return_value.open.return_value = self._response(provider)
                with self.assertRaises(AIServiceError) as caught:
                    structured_response(self.config, [], {}, "test")
            self.assertEqual(caught.exception.code, "generation_invalid")

    def test_http_auth_quota_and_network_errors_do_not_leak_provider_text(self):
        cases = [
            (error.HTTPError("https://api.openai.com", 401, "secret-transport-test", {}, io.BytesIO(b"private")), "upstream_authentication_failed"),
            (error.HTTPError("https://api.openai.com", 429, "secret-transport-test", {}, io.BytesIO(b"private")), "upstream_rate_limited"),
            (error.URLError("secret-transport-test"), "upstream_unavailable"),
            (TimeoutError("secret-transport-test"), "upstream_timeout"),
        ]
        for failure, expected in cases:
            with patch("rarebridge.ai.transport.request.build_opener") as builder:
                builder.return_value.open.side_effect = failure
                with self.assertRaises(AIServiceError) as caught:
                    structured_response(self.config, [], {}, "test")
            self.assertEqual(caught.exception.code, expected)
            self.assertNotIn("secret-transport-test", json.dumps(caught.exception.to_dict()))

    def test_insufficient_quota_is_distinguished_without_provider_message(self):
        body = json.dumps({"error": {"code": "insufficient_quota", "message": "secret-transport-test"}}).encode()
        failure = error.HTTPError("https://api.openai.com", 429, "test", {}, io.BytesIO(body))
        with patch("rarebridge.ai.transport.request.build_opener") as builder:
            builder.return_value.open.side_effect = failure
            with self.assertRaises(AIServiceError) as caught:
                structured_response(self.config, [], {}, "test")
        self.assertEqual(caught.exception.code, "upstream_quota_exhausted")
        self.assertEqual(caught.exception.details, [{"provider_code": "insufficient_quota"}])
        self.assertNotIn("secret-transport-test", json.dumps(caught.exception.to_dict()))

    def test_current_billing_and_spend_error_codes_are_distinguished(self):
        for code in ("credit_balance_exhausted", "organization_spend_limit_exceeded",
                     "project_spend_limit_exceeded", "organization_usage_limit_exceeded"):
            body = json.dumps({"error": {"code": code, "type": "insufficient_quota"}}).encode()
            failure = error.HTTPError("https://api.openai.com", 429, "test", {}, io.BytesIO(body))
            with patch("rarebridge.ai.transport.request.build_opener") as builder:
                builder.return_value.open.side_effect = failure
                with self.assertRaises(AIServiceError) as caught:
                    structured_response(self.config, [], {}, "test")
            self.assertEqual(caught.exception.code, "upstream_quota_exhausted")
            self.assertEqual(caught.exception.details, [{"provider_code": code}])


if __name__ == "__main__":
    unittest.main()
