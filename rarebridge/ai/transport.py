"""Bounded standard-library transports for OpenAI Responses and Claude Messages."""

import json
import re
import socket
from urllib import error, request


RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MAX_RESPONSE_BYTES = 2_000_000
QUOTA_CODES = {"insufficient_quota", "credit_balance_exhausted",
               "organization_spend_limit_exceeded", "project_spend_limit_exceeded",
               "organization_usage_limit_exceeded"}
RATE_CODES = {"rate_limit_exceeded", "slow_down", "rate_limit_error"}


class AIServiceError(Exception):
    """Safe public error; never includes raw provider text, prompts or credentials."""

    def __init__(self, code, message, status_code=503, details=None):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code
        self.details = details or []

    def to_dict(self):
        return {
            "schema_version": "rarebridge.handoff.v1",
            "error": {"code": self.code, "message": self.message, "details": self.details},
        }


class _NoRedirect(request.HTTPRedirectHandler):
    # The credential must never follow an unexpected redirected provider URL.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def structured_response(config, messages, schema, schema_name):
    """Dispatch without switching providers or models after a failed request."""
    provider = getattr(config, "provider", "openai")
    if provider == "openai":
        return _openai_response(config, messages, schema, schema_name)
    if provider == "anthropic":
        return _anthropic_response(config, messages, schema, schema_name)
    raise AIServiceError("configuration_invalid", "Select an available AI provider.", 503)


def _openai_response(config, messages, schema, schema_name):
    if not config.api_key:
        raise AIServiceError("model_unavailable", "Configure OPENAI_API_KEY for a live OpenAI request.")
    body = {
        "model": config.model, "input": messages, "store": False,
        "max_output_tokens": config.max_output_tokens,
        "text": {"format": {
            "type": "json_schema", "name": schema_name,
            "strict": True, "schema": schema,
        }},
    }
    req = request.Request(
        RESPONSES_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST", headers={
            "Authorization": "Bearer " + config.api_key,
            "Content-Type": "application/json", "User-Agent": "RareBridge/0.1",
        },
    )
    opener = request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=config.timeout_seconds) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
            request_id = response.headers.get("x-request-id")
    except error.HTTPError as exc:
        code = exc.code
        # Inspect only a bounded structured code, never expose the provider's
        # free-form error message or response body in logs/API diagnostics.
        provider_code = None
        try:
            problem = json.loads(exc.read(16_384))
            if isinstance(problem, dict) and isinstance(problem.get("error"), dict):
                candidate = problem["error"].get("code") or problem["error"].get("type")
                if candidate in QUOTA_CODES | RATE_CODES:
                    provider_code = candidate
                elif problem["error"].get("type") == "insufficient_quota":
                    provider_code = "insufficient_quota"
        except (ValueError, OSError, TypeError):
            pass
        exc.close()
        if code in {401, 403}:
            raise AIServiceError("upstream_authentication_failed", "OpenAI rejected the API credentials or model access.", 503) from None
        if code == 429:
            if provider_code in QUOTA_CODES:
                raise AIServiceError("upstream_quota_exhausted", "OpenAI API credits or quota are unavailable; check the API project's billing.", 429,
                                     [{"provider_code": provider_code}]) from None
            details = [{"provider_code": provider_code}] if provider_code else []
            raise AIServiceError("upstream_rate_limited", "OpenAI rate or quota limit reached; retry when available.", 429, details) from None
        raise AIServiceError("upstream_unavailable", "OpenAI did not accept the generation request.", 502) from None
    except (TimeoutError, socket.timeout):
        raise AIServiceError("upstream_timeout", "The OpenAI request timed out.", 504) from None
    except error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise AIServiceError("upstream_timeout", "The OpenAI request timed out.", 504) from None
        raise AIServiceError("upstream_unavailable", "The OpenAI endpoint could not be reached.", 502) from None
    except OSError:
        raise AIServiceError("upstream_unavailable", "The OpenAI request could not be completed.", 502) from None
    if len(data) > MAX_RESPONSE_BYTES:
        raise AIServiceError("generation_invalid", "OpenAI response exceeded the size limit.", 502)
    try:
        provider = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise AIServiceError("generation_invalid", "OpenAI returned an unreadable response.", 502) from None
    if not isinstance(provider, dict):
        raise AIServiceError("generation_invalid", "OpenAI response has an invalid envelope.", 502)
    if provider.get("status") != "completed":
        raise AIServiceError("model_incomplete", "OpenAI generation did not complete; no claims were accepted.", 502)
    chunks = []
    items = provider.get("output", [])
    if not isinstance(items, list):
        raise AIServiceError("generation_invalid", "OpenAI response has an invalid output list.", 502)
    for item in items:
        if not isinstance(item, dict):
            raise AIServiceError("generation_invalid", "OpenAI response has an invalid output item.", 502)
        if item.get("type") != "message":
            continue
        contents = item.get("content", [])
        if not isinstance(contents, list):
            raise AIServiceError("generation_invalid", "OpenAI response has an invalid message content list.", 502)
        for content in contents:
            if not isinstance(content, dict):
                raise AIServiceError("generation_invalid", "OpenAI response has an invalid message content item.", 502)
            if content.get("type") == "refusal":
                raise AIServiceError("model_refused", "OpenAI declined this generation; no claims were accepted.", 502)
            if content.get("type") == "output_text":
                if not isinstance(content.get("text"), str):
                    raise AIServiceError("generation_invalid", "OpenAI response has invalid structured text.", 502)
                chunks.append(content["text"])
    try:
        output = json.loads("".join(chunks))
    except (ValueError, TypeError):
        raise AIServiceError("generation_invalid", "OpenAI output did not contain the required structured data.", 502) from None
    response_id = provider.get("id")
    if not isinstance(response_id, str) or not response_id.startswith("resp_"):
        raise AIServiceError("generation_invalid", "OpenAI response has no usable response identifier.", 502)
    return output, {
        "provider": "openai", "response_id": response_id, "request_id": request_id,
        "model": provider.get("model", config.model),
        "provider_created_at": provider.get("created_at"), "usage": provider.get("usage", {}),
    }


def _anthropic_messages(messages):
    """Claude uses a top-level system field, not a system conversation role."""
    if not isinstance(messages, list) or not messages:
        raise AIServiceError("invalid_input", "AI messages must contain a text conversation.", 422)
    system, conversation = [], []
    for item in messages:
        if not isinstance(item, dict) or not isinstance(item.get("content"), str):
            raise AIServiceError("invalid_input", "AI messages must contain text content.", 422)
        role = item.get("role")
        if role == "system":
            system.append(item["content"])
        elif role in {"user", "assistant"}:
            conversation.append({"role": role, "content": item["content"]})
        else:
            raise AIServiceError("invalid_input", "Claude messages contain an unsupported role.", 422)
    if not conversation or conversation[-1]["role"] != "user":
        raise AIServiceError("invalid_input", "Structured Claude generation must end with a user message.", 422)
    return "\n\n".join(system), conversation


def _anthropic_http_error(exc):
    """Expose only documented categories, never the provider's free-form text."""
    code = exc.code
    allowed_types = {
        "invalid_request_error", "authentication_error", "billing_error",
        "permission_error", "not_found_error", "request_too_large",
        "rate_limit_error", "api_error", "timeout_error", "overloaded_error",
    }
    provider_type = None
    diagnostic_category = None
    try:
        problem = json.loads(exc.read(16_384))
        if isinstance(problem, dict) and isinstance(problem.get("error"), dict):
            provider_error = problem["error"]
            value = provider_error.get("type")
            if isinstance(value, str) and value in allowed_types:
                provider_type = value
            # Messages are inspected only for a bounded set of troubleshooting
            # categories. The original text is never returned, logged or cached.
            message = provider_error.get("message")
            if isinstance(message, str):
                message = message[:8_000].casefold()
                if ("credit balance" in message or "billing credit" in message
                        or re.search(r"(?:insufficient|exhausted|low|no|purchase)\s+(?:api\s+)?credits", message)):
                    diagnostic_category = "quota_exhausted"
                elif ("anthropic-workspace-id" in message or "workspace id" in message) and any(
                        phrase in message for phrase in ("required", "missing", "must", "not provided")):
                    diagnostic_category = "workspace_required"
                elif any(phrase in message for phrase in (
                        "api-key", "api key", "authentication", "invalid auth", "invalid token")):
                    diagnostic_category = "credentials_rejected"
                elif "model" in message and any(phrase in message for phrase in (
                        "not valid", "invalid model", "not found", "does not exist", "not available",
                        "not supported", "unknown model")):
                    diagnostic_category = "model_unavailable"
                elif any(phrase in message for phrase in (
                        "output_config", "unsupported schema", "json schema", "schema is too complex")):
                    diagnostic_category = "schema_rejected"
    except (ValueError, OSError, TypeError):
        pass
    finally:
        exc.close()
    details = [{"provider_error_type": provider_type}] if provider_type else []
    if diagnostic_category:
        details.append({"diagnostic_category": diagnostic_category})
    if code in {401, 403}:
        return AIServiceError("upstream_authentication_failed", "Anthropic rejected the credentials, workspace or model access.", 503, details)
    if code == 402 or provider_type == "billing_error" or diagnostic_category == "quota_exhausted":
        return AIServiceError("upstream_quota_exhausted", "Anthropic billing is unavailable; check the API workspace's credits and billing.", 429, details)
    if diagnostic_category == "workspace_required":
        return AIServiceError("upstream_request_rejected", "Anthropic requires a workspace ID for this key; configure ANTHROPIC_WORKSPACE_ID.", 503, details)
    if diagnostic_category == "credentials_rejected":
        return AIServiceError("upstream_authentication_failed", "Anthropic rejected the API credentials.", 503, details)
    if diagnostic_category == "model_unavailable":
        return AIServiceError("upstream_model_unavailable", "Anthropic could not use the configured model.", 503, details)
    if diagnostic_category == "schema_rejected":
        return AIServiceError("upstream_request_rejected", "Anthropic rejected the structured-output configuration or schema.", 502, details)
    if code == 429:
        return AIServiceError("upstream_rate_limited", "Anthropic rate or spend limit reached; retry when access is available.", 429, details)
    if code == 504 or provider_type == "timeout_error":
        return AIServiceError("upstream_timeout", "The Anthropic request timed out.", 504, details)
    if code == 529 or provider_type == "overloaded_error":
        return AIServiceError("upstream_overloaded", "Anthropic is temporarily overloaded; retry later.", 503, details)
    if code == 404:
        return AIServiceError("upstream_model_unavailable", "Anthropic could not find the configured model or resource.", 503, details)
    if code in {400, 413}:
        return AIServiceError("upstream_request_rejected", "Anthropic rejected the request; check the schema, model, workspace and spend settings.", 502, details)
    return AIServiceError("upstream_unavailable", "Anthropic did not accept the generation request.", 502, details)


def _anthropic_response(config, messages, schema, schema_name):
    """Direct non-streaming Messages API with schema-constrained JSON output.

    API shape: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
    Header/error shapes: https://platform.claude.com/docs/en/api/overview
    No beta header, SDK, source fetch, tool invocation or provider fallback.
    """
    if not config.api_key:
        raise AIServiceError("model_unavailable", "Configure ANTHROPIC_API_KEY for a live Claude request.")
    system, conversation = _anthropic_messages(messages)
    body = {
        "model": config.model, "max_tokens": config.max_output_tokens,
        "messages": conversation,
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }
    if system:
        body["system"] = system
    headers = {
        "Authorization": "Bearer " + config.api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json", "User-Agent": "RareBridge/0.1",
    }
    workspace = getattr(config, "anthropic_workspace_id", "")
    if workspace:
        if not isinstance(workspace, str) or any(ord(char) < 33 or ord(char) > 126 for char in workspace):
            raise AIServiceError("configuration_invalid", "Anthropic workspace ID has an invalid format.", 503)
        headers["anthropic-workspace-id"] = workspace
    req = request.Request(
        ANTHROPIC_MESSAGES_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST", headers=headers,
    )
    opener = request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=config.timeout_seconds) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
            request_id = response.headers.get("request-id")
    except error.HTTPError as exc:
        raise _anthropic_http_error(exc) from None
    except (TimeoutError, socket.timeout):
        raise AIServiceError("upstream_timeout", "The Anthropic request timed out.", 504) from None
    except error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise AIServiceError("upstream_timeout", "The Anthropic request timed out.", 504) from None
        raise AIServiceError("upstream_unavailable", "The Anthropic endpoint could not be reached.", 502) from None
    except (OSError, ValueError):
        raise AIServiceError("upstream_unavailable", "The Anthropic request could not be completed.", 502) from None
    if len(data) > MAX_RESPONSE_BYTES:
        raise AIServiceError("generation_invalid", "Anthropic response exceeded the size limit.", 502)
    try:
        provider = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise AIServiceError("generation_invalid", "Anthropic returned an unreadable response.", 502) from None
    if not isinstance(provider, dict) or provider.get("type") != "message" or provider.get("role") != "assistant":
        raise AIServiceError("generation_invalid", "Anthropic response has an invalid message envelope.", 502)
    stop = provider.get("stop_reason")
    if stop == "refusal":
        raise AIServiceError("model_refused", "Claude declined this generation; no claims were accepted.", 502)
    if stop == "max_tokens":
        raise AIServiceError("model_incomplete", "Claude reached the output-token limit; no claims were accepted.", 502,
                             [{"stop_reason": "max_tokens"}])
    if stop != "end_turn":
        raise AIServiceError("model_incomplete", "Claude generation did not finish normally; no claims were accepted.", 502)
    contents = provider.get("content")
    if not isinstance(contents, list):
        raise AIServiceError("generation_invalid", "Anthropic response has an invalid content list.", 502)
    chunks = []
    for item in contents:
        if not isinstance(item, dict):
            raise AIServiceError("generation_invalid", "Anthropic response has an invalid content item.", 502)
        kind = item.get("type")
        if kind == "text":
            if not isinstance(item.get("text"), str):
                raise AIServiceError("generation_invalid", "Anthropic response has invalid structured text.", 502)
            chunks.append(item["text"])
        elif kind not in {"thinking", "redacted_thinking"}:
            raise AIServiceError("generation_invalid", "Anthropic response has unsupported content.", 502)
    try:
        output = json.loads("".join(chunks))
    except (ValueError, TypeError):
        raise AIServiceError("generation_invalid", "Claude output did not contain the required structured data.", 502) from None
    response_id, model = provider.get("id"), provider.get("model")
    if not isinstance(output, dict):
        raise AIServiceError("generation_invalid", "Claude output must contain a JSON object.", 502)
    if not isinstance(response_id, str) or not response_id.startswith("msg_") or len(response_id) <= 4:
        raise AIServiceError("generation_invalid", "Anthropic response has no usable message identifier.", 502)
    if not isinstance(model, str) or not model.strip():
        raise AIServiceError("generation_invalid", "Anthropic response has no usable model identifier.", 502)
    usage = provider.get("usage", {})
    if not isinstance(usage, dict):
        raise AIServiceError("generation_invalid", "Anthropic response has invalid usage metadata.", 502)
    return output, {
        "provider": "anthropic", "response_id": response_id, "request_id": request_id,
        "model": model, "provider_created_at": provider.get("created_at"), "usage": usage,
        "stop_reason": "end_turn",
    }
