"""Thin, optional bridge to the lead's AI service (rarebridge/ai/service.py).

The backend only wires the service. The lead owns extraction/explanation logic,
source-to-graph import and any source-review promotion. If the module or a
function is missing, or the module's own capabilities() reports it unavailable,
the API answers HTTP 503 model_unavailable. Nothing is mocked.

Expected lead interface:
    async def extract_source(payload: dict) -> dict      # extraction.schema.json
    async def explain_assessment(assessment: dict, sources: dict) -> dict  # Explanation
    def capabilities() -> dict   # OPTIONAL: {"ai_extraction": bool, "ai_explanation": bool}
    class AIServiceError(Exception)     # safe code/status_code/to_dict error envelope
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import importlib
import inspect
import json
import os
import sys
from pathlib import Path

SERVICE_MODULE = "rarebridge.ai.service"
ROOT = Path(__file__).resolve().parents[2]
EXTRACTION_SCHEMA_CANDIDATES = (
    ROOT / "handoffs" / "contracts" / "extraction.schema.json",
    ROOT / "contracts" / "extraction.schema.json",
)


class AIUnavailable(RuntimeError):
    pass


class AIServiceError(RuntimeError):
    def __init__(self, code, message, details=None, status_code=502):
        self.code, self.details, self.status_code = code, details or [], status_code
        super().__init__(message)


class AIBridge:
    def __init__(self, module_name=SERVICE_MODULE, timeout=None):
        self.module_name = module_name
        self.timeout = float(timeout or os.environ.get("RAREBRIDGE_AI_TIMEOUT", "90"))
        self.last_error = None

    def _module(self):
        """Import on demand so a service added after startup is picked up."""
        if self.module_name in sys.modules:
            return sys.modules[self.module_name]
        try:
            module = importlib.import_module(self.module_name)
            self.last_error = None
            return module
        except ModuleNotFoundError as exc:
            missing = exc.name or ""
            if self.module_name.startswith(missing) or missing.startswith("rarebridge.ai"):
                self.last_error = "AI service module not installed"
            else:
                self.last_error = f"AI service import failed: missing dependency {missing}"
            return None
        except Exception as exc:  # report the type without exposing exception content
            self.last_error = f"AI service import failed: {type(exc).__name__}"
            return None

    def capabilities(self):
        module = self._module()
        caps = {"ai_extraction": False, "ai_explanation": False}
        if module is None:
            return caps, self.last_error
        caps["ai_extraction"] = inspect.iscoroutinefunction(getattr(module, "extract_source", None))
        caps["ai_explanation"] = inspect.iscoroutinefunction(getattr(module, "explain_assessment", None))
        reported = getattr(module, "capabilities", None)
        if callable(reported):
            try:
                declared = reported() or {}
                for key in caps:
                    caps[key] = caps[key] and bool(declared.get(key, False))
            except Exception as exc:
                self.last_error = f"AI capabilities() failed: {type(exc).__name__}"
                return {key: False for key in caps}, self.last_error
        return caps, None if any(caps.values()) else (self.last_error or "AI service reports no capability")

    async def _call(self, capability, function_name, *args):
        caps, reason = self.capabilities()
        if not caps.get(capability):
            raise AIUnavailable(reason or "Model unavailable")
        module = self._module()
        unavailable_type = getattr(module, "ModelUnavailable", None)
        service_error_type = getattr(module, "AIServiceError", None)
        try:
            return await asyncio.wait_for(getattr(module, function_name)(*args), timeout=self.timeout)
        except asyncio.TimeoutError as exc:
            raise AIServiceError("ai_timeout", f"AI service did not answer within {self.timeout:.0f}s",
                                 status_code=504) from exc
        except Exception as exc:
            if isinstance(service_error_type, type) and isinstance(exc, service_error_type):
                # The lead's error envelope is explicitly safe for public use.
                safe = exc.to_dict().get("error", {})
                status = getattr(exc, "status_code", 502)
                if (isinstance(safe.get("code"), str) and isinstance(safe.get("message"), str)
                        and isinstance(status, int) and 400 <= status <= 599):
                    raise AIServiceError(safe["code"], safe["message"], safe.get("details", []),
                                         status_code=status) from None
            if isinstance(unavailable_type, type) and isinstance(exc, unavailable_type):
                raise AIUnavailable("Model unavailable") from None
            raise AIServiceError("ai_service_error", "The AI service could not complete this request.") from None

    async def extract(self, payload):
        result = await self._call("ai_extraction", "extract_source", payload)
        problems = self._validate_extraction(result, payload["source_id"])
        if problems:
            raise AIServiceError("ai_output_invalid", "Extraction output failed the shared schema/rules.", problems)
        return result

    async def explain(self, assessment, sources):
        result = await self._call("ai_explanation", "explain_assessment", assessment, sources)
        problems = []
        if not isinstance(result, dict):
            problems.append({"msg": "Explanation must be an object"})
        else:
            if result.get("generation_mode") not in ("live", "cached"):
                problems.append({"msg": "generation_mode must be 'live' or 'cached' for a model explanation"})
            if not isinstance(result.get("text"), str) or not result.get("text", "").strip():
                problems.append({"msg": "text must be a non-empty string"})
            cited = result.get("cited_source_ids", [])
            if not isinstance(cited, list):
                problems.append({"msg": "cited_source_ids must be a list"})
            else:
                aliases = {alias: canonical for canonical, source in sources.items()
                           for alias in [canonical, *source.get("aliases", [])]}
                unknown = [sid for sid in cited if not isinstance(sid, str) or sid not in aliases]
                if unknown:
                    problems.append({"msg": "Explanation cites sources outside this assessment"})
                withdrawn = set(assessment.get("withdrawn_sources", []))
                if any(isinstance(sid, str) and aliases.get(sid) in withdrawn for sid in cited):
                    problems.append({"msg": "Explanation cites a withdrawn publication"})
            provenance = result.get("provenance")
            if isinstance(provenance, dict) and "assessment_sha256" in provenance:
                fingerprint = hashlib.sha256(json.dumps(assessment, sort_keys=True,
                    separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
                if provenance["assessment_sha256"] != fingerprint:
                    problems.append({"msg": "Explanation belongs to a different assessment state"})
        if problems:
            raise AIServiceError("ai_output_invalid", "Explanation output failed validation.", problems)
        # Preserve validated draft/provenance fields so current-state briefs can
        # verify the assessment fingerprint instead of dropping the AI message.
        return deepcopy(result)

    @staticmethod
    def _validate_extraction(result, source_id):
        problems = []
        if not isinstance(result, dict):
            return [{"msg": "Extraction must be an object"}]
        schema_path = next((p for p in EXTRACTION_SCHEMA_CANDIDATES if p.exists()), None)
        if schema_path is not None:
            try:
                import jsonschema
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                for err in jsonschema.Draft202012Validator(schema).iter_errors(result):
                    problems.append({"loc": list(err.path), "msg": err.message})
            except ImportError:
                problems.append({"msg": "jsonschema not installed; cannot validate extraction output"})
        if result.get("source_id") != source_id:
            problems.append({"msg": "Extraction source_id differs from the requested source"})
        for claim in result.get("claims", []) if isinstance(result.get("claims"), list) else []:
            if claim.get("review_status") != "pending":
                problems.append({"msg": "Every extracted relationship must stay pending", "value": claim.get("id")})
        return problems
