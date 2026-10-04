"""Provider isolation tests; all credentials and model responses are synthetic."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rarebridge.ai.brief import build_collaboration_brief
from rarebridge.ai.config import AIConfig, WORKSPACE_ROOT, load_config
from rarebridge.ai.service import AIService, AIServiceError, capabilities
from rarebridge.ai.__main__ import assessment_response
from rarebridge.ai.tests.test_service import SOURCE, extraction_raw, explanation_raw


class ProviderTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, config, messages, schema, name):
        self.calls.append(config.provider)
        output = extraction_raw(messages) if name.endswith("extract") else explanation_raw(messages)
        prefix = "msg_" if config.provider == "anthropic" else "resp_"
        return output, {
            "provider": config.provider, "response_id": prefix + "SYNTHETIC_UNIT_TEST_ONLY",
            "model": config.model, "usage": {},
        }


class ProviderConfigTests(unittest.TestCase):
    def test_selected_provider_uses_its_key_and_model_default_only(self):
        absent = Path("/nonexistent-rarebridge-env")
        values = {"OPENAI_API_KEY": "openai-test-secret", "ANTHROPIC_API_KEY": "anthropic-test-secret"}
        openai = load_config(values, absent)
        claude = load_config(dict(values, RAREBRIDGE_AI_PROVIDER="anthropic"), absent)
        self.assertEqual((openai.api_key, openai.model), ("openai-test-secret", "gpt-4o-mini"))
        self.assertEqual((claude.api_key, claude.model), ("anthropic-test-secret", "claude-sonnet-4-6"))
        self.assertNotIn("test-secret", repr(claude))
        self.assertNotIn("test-secret", json.dumps(claude.diagnostics()))
        no_claude = load_config({"RAREBRIDGE_AI_PROVIDER": "anthropic", "OPENAI_API_KEY": "openai-test-secret"}, absent)
        self.assertEqual(no_claude.api_key, "")

    def test_wrong_provider_model_and_header_injection_are_rejected(self):
        for values in (
            {"RAREBRIDGE_AI_PROVIDER": "unrecognized"},
            {"RAREBRIDGE_AI_PROVIDER": "anthropic", "RAREBRIDGE_AI_MODEL": "gpt-4o-mini"},
            {"RAREBRIDGE_AI_PROVIDER": "openai", "RAREBRIDGE_AI_MODEL": "claude-sonnet-4-6"},
            {"ANTHROPIC_WORKSPACE_ID": "wrkspc_test\nInjected: value"},
        ):
            with self.assertRaises(ValueError):
                load_config(values, Path("/nonexistent-rarebridge-env"))


class ProviderServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.config = AIConfig(
            "anthropic-synthetic-test-key", model="claude-sonnet-4-6", mode="live",
            provider="anthropic", cache_dir=Path(directory.name),
        )
        self.transport = ProviderTransport()

    async def test_claude_response_can_replay_without_key_and_preserves_pending(self):
        result = await AIService(self.config, self.transport).extract_source(SOURCE)
        replay = await AIService(replace(self.config, api_key="", mode="cache"), self.transport).extract_source(SOURCE)
        self.assertEqual(replay["generation_mode"], "cached")
        self.assertEqual(replay["claims"], result["claims"])
        self.assertEqual(replay["provenance"]["provider"], "anthropic")
        self.assertTrue(all(claim["review_status"] == "pending" for claim in replay["claims"]))
        self.assertEqual(self.transport.calls, ["anthropic"])

    async def test_cache_does_not_cross_provider_or_anthropic_workspace(self):
        await AIService(self.config, self.transport).extract_source(SOURCE)
        for changed in (
            replace(self.config, provider="openai", mode="cache"),
            replace(self.config, anthropic_workspace_id="wrkspc_other", mode="cache"),
        ):
            with self.assertRaises(AIServiceError) as caught:
                await AIService(changed, self.transport).extract_source(SOURCE)
            self.assertEqual(caught.exception.code, "cache_miss")
        with patch("rarebridge.ai.service.load_config", return_value=replace(self.config, provider="openai", api_key="", mode="cache")):
            self.assertEqual(capabilities()["cached_response_counts"], {"extract": 0, "explain": 0})

    async def test_wrong_provider_or_response_prefix_never_accepted_or_cached(self):
        for provider, response_id in (("openai", "resp_test"), ("anthropic", "resp_test"), ("anthropic", "msg_")):
            def invalid(config, messages, schema, name):
                output, metadata = self.transport(config, messages, schema, name)
                metadata.update(provider=provider, response_id=response_id)
                return output, metadata
            with self.assertRaises(AIServiceError) as caught:
                await AIService(self.config, invalid).extract_source(SOURCE)
            self.assertEqual(caught.exception.code, "generation_invalid")
        self.assertFalse(list(self.config.cache_dir.glob("*.json")))

    async def test_corrupted_request_or_model_provenance_cannot_replay(self):
        await AIService(self.config, self.transport).extract_source(SOURCE)
        path = next(self.config.cache_dir.glob("extract-*.json"))
        original = json.loads(path.read_text())
        for field, value in (("request_sha256", "another-request"), ("requested_model", "another-model")):
            record = deepcopy(original)
            record["provenance"][field] = value
            path.write_text(json.dumps(record))
            with self.assertRaises(AIServiceError) as caught:
                await AIService(replace(self.config, mode="cache"), self.transport).extract_source(SOURCE)
            self.assertEqual(caught.exception.code, "cache_invalid")

    async def test_claude_explanation_stays_bound_to_current_assessment(self):
        bundle = json.loads((WORKSPACE_ROOT / "rarebridge/data/assessment-syngap1.json").read_text())
        response = assessment_response(bundle)
        response["explanation"] = await AIService(self.config, self.transport).explain_assessment(response["after"], response["sources"])
        self.assertEqual(build_collaboration_brief(response)["generation_mode"], "live")
        withdrawn = assessment_response(bundle, ["PMID:42446932"])
        withdrawn["explanation"] = deepcopy(response["explanation"])
        self.assertEqual(build_collaboration_brief(withdrawn)["generation_mode"], "none")
        with self.assertRaises(AIServiceError) as caught:
            await AIService(replace(self.config, mode="cache"), self.transport).explain_assessment(withdrawn["after"], withdrawn["sources"])
        self.assertEqual(caught.exception.code, "cache_miss")


if __name__ == "__main__":
    unittest.main()
