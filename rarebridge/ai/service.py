"""Async AI integration for Srinath's API, with source-bound validation and cache."""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .config import KEY_NAMES, WORKSPACE_ROOT, load_config
from .contracts import (
    EXTRACTION_SCHEMA, validate_source_payload, validate_extraction,
    explanation_generation_schema, bind_explanation_selection,
    validate_explanation_selection,
)
from .prompts import extraction_messages, explanation_messages
from .transport import AIServiceError, structured_response


SCHEMA_VERSION = "rarebridge.handoff.v1"
PROMPT_VERSION = "rarebridge.ai.v1"
MAX_CACHE_BYTES = 2_000_000
RESPONSE_PREFIXES = {"openai": "resp_", "anthropic": "msg_"}
VALIDATION = {
    "status": "passed",
    "checks": ["schema", "status_alignment", "citation_scope", "required_followups"],
    "meaning": "Structural and recorded-evidence consistency checks; not scientific or clinical validation.",
}


def _json_hash(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _matches_provider(provenance, config):
    """A cache or transport envelope must identify the selected provider."""
    if not isinstance(provenance, dict) or config.provider not in RESPONSE_PREFIXES:
        return False
    response_id = provenance.get("response_id")
    return (provenance.get("provider") == config.provider
            and isinstance(response_id, str)
            and response_id.startswith(RESPONSE_PREFIXES[config.provider])
            and len(response_id) > len(RESPONSE_PREFIXES[config.provider])
            and isinstance(provenance.get("model"), str)
            and bool(provenance["model"]))


def _validation_check(exc):
    """Classify local validation failures without returning model-authored text."""
    reason = str(exc)
    if "literal excerpt" in reason:
        return "literal_source_excerpt"
    if "Known entity" in reason or "candidate:" in reason or "entity endpoint" in reason:
        return "entity_identity"
    if "Duplicate" in reason or "conflicting claim ID" in reason:
        return "unique_identifiers"
    if "explanation check" in reason or "every recorded check" in reason:
        return "explanation_check_coverage"
    if "explanation selection" in reason or "check prose selection" in reason:
        return "explanation_selection_shape"
    if "unregistered or unavailable URL" in reason:
        return "unregistered_prose_url"
    if "unregistered or unavailable publication ID" in reason:
        return "unavailable_prose_publication"
    if "unregistered contact email" in reason:
        return "unregistered_contact"
    if "source_id" in reason or "source ID" in reason or "citation" in reason:
        return "source_binding"
    if "status" in reason or "pending" in reason:
        return "recorded_status"
    if "next" in reason or "followup" in reason or "question" in reason:
        return "required_followups"
    if "medical" in reason or "treatment" in reason or "clinical" in reason:
        return "prose_safety"
    return "output_shape"


def known_entities():
    """Read the existing identity catalogue without promoting imported claims."""
    graph_path = WORKSPACE_ROOT / "rarebridge" / "data" / "graph.json"
    overlay_path = WORKSPACE_ROOT / "curation" / "atlas-overlay.json"
    items = []
    for path in (graph_path, overlay_path):
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for node in data.get("nodes", []):
            kind = node.get("type")
            if kind == "claim" and node.get("claim_type") == "mechanism":
                kind = "mechanism"
            if kind not in {"disease", "gene", "variant", "phenotype", "mechanism", "study", "asset", "organization", "researcher"}:
                continue
            items.append({
                "id": node["id"], "type": kind, "label": node["label"],
                "synonyms": node.get("synonyms", []), "aliases": node.get("aliases", []),
            })
        for asset in data.get("assets", []):
            items.append({"id": asset["id"], "type": "asset", "label": asset["label"]})
    for path in sorted((WORKSPACE_ROOT / "rarebridge" / "data").glob("assessment-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        asset = data.get("asset", {})
        if asset.get("id") and asset.get("label"):
            items.append({"id": asset["id"], "type": "asset", "label": asset["label"]})
    by_id = {}
    for item in items:
        prior = by_id.get(item["id"])
        if prior and (prior["type"], prior["label"]) != (item["type"], item["label"]):
            raise ValueError("Identity catalogue has conflicting labels or types for one ID")
        by_id[item["id"]] = item
    return sorted(by_id.values(), key=lambda item: item["id"])


def _merge_identity_hints(catalog, supplied):
    """Caller hints may extend the catalogue, never redefine known identities."""
    def normalized(value):
        return " ".join(value.split()).casefold()

    by_id = {item["id"]: deepcopy(item) for item in catalog}
    known_names = {}
    for item in catalog:
        for name in [item["label"], *item.get("aliases", []), *item.get("synonyms", [])]:
            known_names.setdefault(normalized(name), []).append(item)
    for item in supplied:
        names = [item["label"], *item.get("aliases", []), *item.get("synonyms", [])]
        for name in names:
            for existing in known_names.get(normalized(name), []):
                if (existing["type"] == item["type"] or existing["type"] in {"gene", "disease", "variant"}) and existing["id"] != item["id"]:
                    raise ValueError("Supplied identity duplicates or redefines an existing catalogue identity")
        existing = by_id.get(item["id"])
        if existing:
            allowed = {normalized(name) for name in [existing["label"], *existing.get("aliases", []), *existing.get("synonyms", [])]}
            if item["type"] != existing["type"] or normalized(item["label"]) not in allowed:
                raise ValueError("Supplied identity conflicts with an existing catalogue ID")
            for field in ("aliases", "synonyms"):
                existing[field] = sorted(set(existing.get(field, []) + item.get(field, [])))
        else:
            if item["id"].casefold().startswith(("mondo:", "hgnc:", "hp:", "doi:", "pmid:")):
                raise ValueError("Caller hints cannot invent external biomedical identifiers")
            by_id[item["id"]] = deepcopy(item)
    return by_id


def _canonical_source_id(source_id):
    """Unify identifiers only when a local record explicitly declares an alias."""
    aliases = {}
    source_maps = []
    for path in sorted((WORKSPACE_ROOT / "rarebridge" / "data").glob("assessment-*.json")):
        source_maps.append(json.loads(path.read_text(encoding="utf-8")).get("sources", {}))
    overlay = WORKSPACE_ROOT / "curation" / "atlas-overlay.json"
    if overlay.is_file():
        source_maps.append(json.loads(overlay.read_text(encoding="utf-8")).get("sources", {}))
    for sources in source_maps:
        for canonical, item in sources.items():
            for alias in [canonical, *item.get("aliases", [])]:
                if alias in aliases and aliases[alias] != canonical:
                    raise ValueError("Source catalogue has an ambiguous publication alias")
                aliases[alias] = canonical
    return aliases.get(source_id, source_id)


def _validate_assessment_input(assessment, sources):
    if isinstance(assessment, dict) and "after" in assessment:
        assessment = assessment["after"]
    if not isinstance(assessment, dict) or not isinstance(sources, dict):
        raise ValueError("Explanation needs an assessment result and a source map")
    for name in ("assessment_id", "target_disease", "goal", "asset", "outcome", "checks", "followup_questions", "withdrawn_sources"):
        if name not in assessment:
            raise ValueError("Assessment is missing " + name)
    if not isinstance(assessment["checks"], list) or not assessment["checks"]:
        raise ValueError("Assessment needs its recorded check results")
    identifiers = []
    for check in assessment["checks"]:
        if not isinstance(check, dict) or check.get("status") not in {"supported", "refuted", "conflicting", "unknown", "needs_source_review"}:
            raise ValueError("Assessment contains an invalid check status")
        identifiers.append(check.get("id"))
    if not all(isinstance(item, str) and item for item in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("Assessment check IDs must be present and unique")
    # Copy through JSON prevents generation from modifying caller-owned values.
    return json.loads(json.dumps(assessment)), json.loads(json.dumps(sources))


def _render_explanation(raw, sources):
    lines = [raw["summary"], ""]
    for check in raw["check_explanations"]:
        citations = " ".join("[" + item + "]" for item in check["source_ids"])
        lines.append(check["explanation"] + (" " + citations if citations else ""))
    if raw["next_steps"]:
        lines.extend(["", "Questions for the next discussion:"])
        for step in raw["next_steps"]:
            lines.append("- " + step["question"] + " (" + step["contact_role"] + ")")
    if raw["cited_source_ids"]:
        lines.extend(["", "Sources:"])
        for source_id in raw["cited_source_ids"]:
            item = sources[source_id]
            lines.append("- " + item.get("title", source_id) + ": " + item["url"])
    return "\n".join(lines).strip()


class AIService:
    """Injectable transport supports offline integration tests without fake demos."""

    def __init__(self, config=None, transport=None):
        self.config = config or load_config()
        self.transport = transport or structured_response

    def _request_spec(self, operation, messages, schema):
        return {
            "operation": operation, "prompt_version": PROMPT_VERSION,
            "model": self.config.model, "messages": messages, "schema": schema,
            "provider": self.config.provider,
            "workspace_id": self.config.anthropic_workspace_id if self.config.provider == "anthropic" else None,
            "max_output_tokens": self.config.max_output_tokens,
        }

    def _read_cache(self, operation, digest):
        path = self.config.cache_dir / (operation + "-" + digest + ".json")
        if not path.is_file():
            return None
        try:
            if path.stat().st_size > MAX_CACHE_BYTES:
                raise ValueError("cache size")
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or not isinstance(record.get("provenance"), dict):
                raise ValueError("cache envelope")
            provenance = record["provenance"]
            if (record.get("operation") != operation or record.get("request_sha256") != digest
                    or not _matches_provider(provenance, self.config)
                    or provenance.get("request_sha256") != digest
                    or provenance.get("requested_model") != self.config.model
                    or provenance.get("prompt_version") != PROMPT_VERSION
                    or not isinstance(record.get("output"), dict)):
                raise ValueError("cache provenance")
            return record
        except (OSError, ValueError, KeyError, TypeError):
            raise AIServiceError("cache_invalid", "A matching cache record is invalid; regenerate it in live mode.", 503) from None

    def _write_cache(self, operation, digest, output, provenance):
        directory = self.config.cache_dir
        temporary = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, prefix=".pending-", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({
                    "cache_version": 1, "operation": operation,
                    "request_sha256": digest, "output": output, "provenance": provenance,
                }, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, directory / (operation + "-" + digest + ".json"))
            return True
        except OSError:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            return False

    async def _generate(self, operation, messages, schema, validator):
        config = self.config
        if config.mode == "off":
            raise AIServiceError("model_unavailable", "AI generation is disabled by configuration.")
        digest = _json_hash(self._request_spec(operation, messages, schema))
        if config.mode in {"auto", "cache"}:
            cached = self._read_cache(operation, digest)
            if cached:
                try:
                    output = validator(deepcopy(cached["output"]))
                except (ValueError, KeyError, TypeError):
                    raise AIServiceError("cache_invalid", "Cached output no longer passes source and assessment checks.", 503) from None
                return output, "cached", deepcopy(cached["provenance"])
        if config.mode == "cache":
            raise AIServiceError("cache_miss", "No genuine cached response matches this exact source or assessment state.")
        if not config.api_key:
            raise AIServiceError("model_unavailable", "Configure " + KEY_NAMES[config.provider] + "; no matching genuine cached response is available.")
        raw, provider_metadata = await asyncio.to_thread(
            self.transport, config, messages, schema, "rarebridge_" + operation,
        )
        if not _matches_provider(provider_metadata, config):
            raise AIServiceError("generation_invalid", "Provider response provenance is incomplete; nothing was accepted.", 502)
        try:
            output = validator(raw)
        except (ValueError, KeyError, TypeError) as exc:
            raise AIServiceError("generation_invalid", "AI output failed source, identifier or recorded-assessment checks; nothing was accepted.", 502,
                                 [{"validation_check": _validation_check(exc), "operation": operation}]) from None
        provenance = {
            **provider_metadata, "prompt_version": PROMPT_VERSION,
            "request_sha256": digest, "generated_at": _utc_now(),
            "requested_model": config.model,
        }
        provenance["cache_saved"] = self._write_cache(operation, digest, output, provenance)
        return output, "live", provenance

    async def extract_source(self, payload):
        try:
            normalized = validate_source_payload(payload)
            supplied_source_id = normalized["source_id"]
            normalized["source_id"] = _canonical_source_id(supplied_source_id)
            catalog = known_entities()
            supplied_entities = normalized.get("known_entities", [])
            catalog_ids = _merge_identity_hints(catalog, supplied_entities)
            catalog = sorted(catalog_ids.values(), key=lambda item: item["id"])
        except (ValueError, KeyError, TypeError, OSError):
            raise AIServiceError("invalid_input", "Source input or identity catalogue is invalid; supply a public source and valid identifiers.", 422) from None
        output, mode, provenance = await self._generate(
            "extract", extraction_messages(normalized, catalog), EXTRACTION_SCHEMA,
            lambda raw: validate_extraction(raw, normalized, known_entities=catalog),
        )
        # A raw claim may reuse a known identity without repeating its node.
        # Return the referenced known nodes so a standalone preview has no
        # dangling edges. This enriches identity metadata, not scientific claims.
        output = deepcopy(output)
        returned_ids = {item["id"] for item in output["entities"]}
        endpoints = {claim[field] for claim in output["claims"] for field in ("subject_id", "object_id")}
        for identifier in sorted(endpoints - returned_ids):
            item = catalog_ids[identifier]
            output["entities"].append({key: item[key] for key in ("id", "type", "label")})
        source_hash = hashlib.sha256(normalized["text"].encode("utf-8")).hexdigest()
        result = {
            "schema_version": SCHEMA_VERSION, "source_id": normalized["source_id"],
            "generation_mode": mode, "model": provenance["model"],
            **output,
            "provenance": {**provenance, "source_sha256": source_hash,
                           "supplied_source_id": supplied_source_id},
            "source": {key: normalized.get(key) for key in ("source_id", "title", "url", "published_on")},
            "validation": {
                "status": "passed", "checks": ["schema", "source_binding", "literal_excerpts", "entity_references"],
                "meaning": "Claims remain pending factual review; extraction is not verification.",
            },
        }
        from .preview import build_graph_preview
        result["graph_preview"] = build_graph_preview(result)
        return result

    async def explain_assessment(self, assessment, sources):
        try:
            assessment, sources = _validate_assessment_input(assessment, sources)
            messages = explanation_messages(assessment, sources)
        except (ValueError, KeyError, TypeError):
            raise AIServiceError("invalid_input", "Explanation needs a complete recorded assessment and its source registry.", 422) from None
        output, mode, provenance = await self._generate(
            "explain", messages, explanation_generation_schema(assessment, sources),
            lambda raw: validate_explanation_selection(raw, assessment, sources),
        )
        output = bind_explanation_selection(output, assessment, sources)
        return {
            "generation_mode": mode, "text": _render_explanation(output, sources),
            "cited_source_ids": output["cited_source_ids"], "model": provenance["model"],
            "assessment_id": assessment["assessment_id"],
            "draft_message": output["draft_message"],
            "check_explanations": output["check_explanations"],
            "next_steps": output["next_steps"], "validation": deepcopy(VALIDATION),
            "provenance": {**provenance, "assessment_sha256": _json_hash(assessment),
                           "source_binding": "reviewed_active_sources_of_recorded_checks",
                           "status_binding": "exact_recorded_check_statuses",
                           "followup_binding": "exact_required_recorded_questions_and_roles"},
        }


async def extract_source(payload):
    """Backend handoff function; raises AIServiceError with a safe API envelope."""
    try:
        return await AIService().extract_source(payload)
    except ValueError:
        raise AIServiceError("configuration_invalid", "Check the AI mode, model, timeout and cache configuration.", 503) from None


async def explain_assessment(assessment, sources):
    """Pass the current after assessment, so withheld sources stay withheld."""
    try:
        return await AIService().explain_assessment(assessment, sources)
    except ValueError:
        raise AIServiceError("configuration_invalid", "Check the AI mode, model, timeout and cache configuration.", 503) from None


def capabilities():
    """Availability, not a claim that a live request has succeeded."""
    try:
        config = load_config()
    except ValueError:
        return {"ai_extraction": False, "ai_explanation": False, "mode": "invalid", "configuration_error": True}
    cached = {"extract": 0, "explain": 0}
    for operation in cached:
        if config.cache_dir.is_dir():
            for path in config.cache_dir.glob(operation + "-*.json"):
                try:
                    if path.stat().st_size > MAX_CACHE_BYTES:
                        continue
                    record = json.loads(path.read_text(encoding="utf-8"))
                    if (isinstance(record, dict)
                            and isinstance(record.get("provenance"), dict)
                            and record.get("operation") == operation
                            and _matches_provider(record["provenance"], config)
                            and record["provenance"].get("requested_model") == config.model
                            and record["provenance"].get("request_sha256") == record.get("request_sha256")
                            and record.get("provenance", {}).get("prompt_version") == PROMPT_VERSION):
                        cached[operation] += 1
                except (OSError, ValueError, TypeError):
                    continue
    can_try_live = bool(config.api_key) and config.mode in {"auto", "live"}
    enabled = config.mode != "off"
    return {
        "ai_extraction": enabled and (can_try_live or config.mode in {"auto", "cache"} and bool(cached["extract"])),
        "ai_explanation": enabled and (can_try_live or config.mode in {"auto", "cache"} and bool(cached["explain"])),
        "mode": config.mode, "model": config.model, "api_key_configured": bool(config.api_key),
        "provider": config.provider,
        "can_attempt_live": can_try_live, "matching_cache_required": config.mode in {"auto", "cache"},
        "cached_response_counts": cached,
        "note": "Configured credentials do not prove working model access; cache availability depends on the exact request.",
    }
