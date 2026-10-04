"""Strict model schemas and application-side evidence checks.

EXTRACTION_SCHEMA describes raw model extraction; EXPLANATION_SCHEMA describes
the validated explanation after recorded ledger fields are bound. The contextual
explanation generation schema lets the model write prose and select check IDs.
Schema adherence does not establish scientific correctness. Extraction is always
pending source review, and generated explanations cannot change assessment facts.
No function in this module fetches a URL or performs an API request.
"""

from copy import deepcopy
from datetime import date
import re
from urllib.parse import urlsplit


ENTITY_TYPES = (
    "disease", "gene", "variant", "phenotype", "mechanism", "study", "asset",
    "organization", "researcher",
)
RELATIONS = (
    "associated_with", "involves_gene", "has_phenotype", "has_mechanism",
    "studies", "uses_resource", "describes_resource", "provides_resource",
    "conducted_by", "affiliated_with", "offers_access_to", "has_access_requirement",
)
EVIDENCE_TYPES = (
    "human_observational", "experimental_model", "reported_association",
    "study_method", "access_requirement", "source_statement",
)
CHECK_STATUSES = (
    "supported", "refuted", "conflicting", "needs_source_review", "unknown",
)
MAX_SOURCE_TEXT = 24_000
MAX_ENTITIES = 20
MAX_CLAIMS = 12
MAX_KNOWN_ENTITIES = 500


def _object(properties):
    """Every field is required; nullable fields represent optional values."""
    return {
        "type": "object", "properties": properties,
        "required": list(properties), "additionalProperties": False,
    }


def _string():
    return {"type": "string"}


def _strings():
    return {"type": "array", "items": _string()}


EXTRACTION_SCHEMA = _object({
    "entities": {"type": "array", "items": _object({
        "id": _string(), "type": {"type": "string", "enum": list(ENTITY_TYPES)},
        "label": _string(),
    })},
    "claims": {"type": "array", "items": _object({
        "id": _string(), "subject_id": _string(),
        "relation": {"type": "string", "enum": list(RELATIONS)},
        "object_id": _string(), "source_id": _string(),
        "source_location": _string(), "source_excerpt": _string(),
        "rationale": _string(),
        "review_status": {"type": "string", "enum": ["pending"]},
        "evidence_type": {"type": "string", "enum": list(EVIDENCE_TYPES)},
        "qualifiers": _object({
            "variant": {"type": ["string", "null"]},
            "experimental_context": {"type": ["string", "null"]},
            "proposed_use": {"type": ["string", "null"]},
        }),
    })},
    "limitations": _strings(),
})

EXPLANATION_SCHEMA = _object({
    "summary": _string(),
    "check_explanations": {"type": "array", "items": _object({
        "check_id": _string(),
        "status": {"type": "string", "enum": list(CHECK_STATUSES)},
        "explanation": _string(), "source_ids": _strings(),
    })},
    "next_steps": {"type": "array", "items": _object({
        "check_id": _string(), "question": _string(), "contact_role": _string(),
    })},
    "cited_source_ids": _strings(), "draft_message": _string(),
})


def _text(value, name, limit, *, allow_empty=False):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    result = value.strip()
    if not allow_empty and not result:
        raise ValueError(f"{name} must not be empty")
    if len(result) > limit:
        raise ValueError(f"{name} exceeds {limit} characters")
    if "\x00" in result:
        raise ValueError(f"{name} must not contain a null character")
    return result


def _id(value, name):
    result = _text(value, name, 300)
    if any(char.isspace() or ord(char) < 32 for char in result):
        raise ValueError(f"{name} must not contain whitespace or control characters")
    return result


def _array(value, name, limit):
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    if len(value) > limit:
        raise ValueError(f"{name} exceeds {limit} items")
    return value


def _keys(value, required, name, *, optional=()):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f"{name} has missing {sorted(missing)} or unexpected {sorted(extra)} fields")


def _flat(value):
    return " ".join(value.split())


def _identity(value):
    return _flat(value).casefold()


def _known_entities(values):
    """Keep only known entity identities and names, without arbitrary prompt data."""
    if isinstance(values, tuple):
        values = list(values)
    entities = []
    seen = set()
    for item in _array(values, "known_entities", MAX_KNOWN_ENTITIES):
        if not isinstance(item, dict):
            raise ValueError("known_entities entries must be objects")
        entity = {
            "id": _id(item.get("id"), "known entity id"),
            "type": _text(item.get("type"), "known entity type", 80),
            "label": _text(item.get("label"), "known entity label", 500),
        }
        if entity["id"] in seen:
            raise ValueError(f"Duplicate known entity ID: {entity['id']}")
        seen.add(entity["id"])
        for field in ("aliases", "synonyms"):
            entity[field] = [
                _text(value, f"known entity {field}", 500)
                for value in _array(item.get(field, []), field, 50)
            ]
        entities.append(entity)
    return entities


def validate_source_payload(payload):
    """Validate an excerpt submitted by the caller; do not fetch its URL.

    Returns source_id/title/url/text/published_on and normalized known_entities.
    Unknown fields are rejected so caller-controlled metadata cannot become
    hidden prompt instructions. The URL is attribution, never a fetch target.
    """
    _keys(payload, ("source_id", "title", "url", "text"), "source payload",
          optional=("published_on", "known_entities"))
    normalized = {
        "source_id": _id(payload["source_id"], "source_id"),
        "title": _text(payload["title"], "title", 500),
        "url": _text(payload["url"], "url", 2_048),
        "text": _text(payload["text"], "text", MAX_SOURCE_TEXT),
    }
    url = normalized["url"]
    if any(char.isspace() or ord(char) < 32 for char in url) or "\\" in url:
        raise ValueError("url must not contain whitespace, controls or backslashes")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("url is malformed") from exc
    if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or (port is not None and not 1 <= port <= 65_535)):
        raise ValueError("url must be an HTTP(S) URL with a host and no credentials")
    published_on = payload.get("published_on")
    if published_on is not None:
        published_on = _text(published_on, "published_on", 10)
        try:
            parsed_date = date.fromisoformat(published_on)
        except ValueError as exc:
            raise ValueError("published_on must be an ISO date or null") from exc
        if parsed_date.isoformat() != published_on:
            raise ValueError("published_on must use YYYY-MM-DD")
    normalized["published_on"] = published_on
    normalized["known_entities"] = _known_entities(payload.get("known_entities", []))
    return normalized


def validate_extraction(raw, payload, known_entities=()):
    """Validate raw model extraction without repairing identities or evidence.

    Any unknown endpoint, duplicate identity, fabricated excerpt or reviewed
    claim fails the entire extraction. Return a new object; callers can attach
    the transport envelope after validation.
    """
    payload = validate_source_payload(payload)
    known = _known_entities(list(known_entities)) if known_entities else payload["known_entities"]
    known_by_id = {entity["id"]: entity for entity in known}
    known_names = {}
    for entity in known:
        for name in [entity["label"], *entity["aliases"], *entity["synonyms"]]:
            known_names.setdefault((entity["type"], _identity(name)), set()).add(entity["id"])
    _keys(raw, ("entities", "claims", "limitations"), "extraction")
    entities, claims = [], []
    used_ids = set()
    for item in _array(raw["entities"], "entities", MAX_ENTITIES):
        _keys(item, ("id", "type", "label"), "entity")
        entity = {
            "id": _id(item["id"], "entity id"),
            "type": _text(item["type"], "entity type", 80),
            "label": _text(item["label"], "entity label", 500),
        }
        if entity["type"] not in ENTITY_TYPES:
            raise ValueError(f"Unknown entity type: {entity['type']}")
        if entity["id"] == payload["source_id"]:
            raise ValueError("The publication source_id cannot be reused as an entity ID")
        if entity["id"] in used_ids:
            raise ValueError(f"Duplicate entity ID: {entity['id']}")
        used_ids.add(entity["id"])
        named_ids = known_names.get((entity["type"], _identity(entity["label"])), set())
        if named_ids and entity["id"] not in named_ids:
            raise ValueError(f"Known entity label requires its existing ID: {entity['label']}")
        existing = known_by_id.get(entity["id"])
        if existing:
            valid_names = {_identity(name) for name in [existing["label"], *existing["aliases"], *existing["synonyms"]]}
            if entity["type"] != existing["type"] or _identity(entity["label"]) not in valid_names:
                raise ValueError(f"Known entity ID conflicts with identity: {entity['id']}")
        elif not entity["id"].startswith("candidate:") or entity["id"] == "candidate:":
            raise ValueError("New entities require local candidate: IDs, never invented external identifiers")
        entities.append(entity)
    valid_endpoints = used_ids | known_by_id.keys()
    for item in _array(raw["claims"], "claims", MAX_CLAIMS):
        _keys(item, EXTRACTION_SCHEMA["properties"]["claims"]["items"]["required"], "claim")
        claim = {
            "id": _id(item["id"], "claim id"),
            "subject_id": _id(item["subject_id"], "claim subject_id"),
            "relation": _text(item["relation"], "claim relation", 80),
            "object_id": _id(item["object_id"], "claim object_id"),
            "source_id": _id(item["source_id"], "claim source_id"),
            "source_location": _text(item["source_location"], "source_location", 500),
            "source_excerpt": _text(item["source_excerpt"], "source_excerpt", 3_000),
            "rationale": _text(item["rationale"], "rationale", 1_500),
            "review_status": item["review_status"],
            "evidence_type": _text(item["evidence_type"], "evidence_type", 80),
        }
        if claim["id"] in used_ids or claim["id"] in known_by_id:
            raise ValueError(f"Duplicate or conflicting claim ID: {claim['id']}")
        if claim["id"] == payload["source_id"]:
            raise ValueError("The publication source_id cannot be reused as a claim ID")
        used_ids.add(claim["id"])
        if claim["subject_id"] not in valid_endpoints or claim["object_id"] not in valid_endpoints:
            raise ValueError("Claim has an unresolved entity endpoint")
        if claim["source_id"] != payload["source_id"]:
            raise ValueError("Claim source_id must exactly match the supplied source_id")
        if _flat(claim["source_excerpt"]) not in _flat(payload["text"]):
            raise ValueError("Claim source_excerpt is not a literal excerpt of the supplied text")
        if claim["relation"] not in RELATIONS:
            raise ValueError(f"Unknown relation: {claim['relation']}")
        if claim["evidence_type"] not in EVIDENCE_TYPES:
            raise ValueError(f"Unknown evidence_type: {claim['evidence_type']}")
        if claim["review_status"] != "pending":
            raise ValueError("Extracted claims must remain pending")
        _keys(item["qualifiers"], ("variant", "experimental_context", "proposed_use"), "qualifiers")
        claim["qualifiers"] = {
            key: None if value is None else _text(value, f"qualifier {key}", 1_000)
            for key, value in item["qualifiers"].items()
        }
        claims.append(claim)
    limitations = [_text(item, "limitation", 1_000)
                   for item in _array(raw["limitations"], "limitations", 12)]
    return {"entities": entities, "claims": claims, "limitations": limitations}


def _source_aliases(sources):
    if not isinstance(sources, dict):
        raise ValueError("sources must be an object keyed by canonical source ID")
    aliases = {}
    for source_id, source in sources.items():
        _id(source_id, "canonical source ID")
        if not isinstance(source, dict):
            raise ValueError("source records must be objects")
        source_aliases = _array(source.get("aliases", []), "source aliases", 50)
        for value in [source_id, *source_aliases]:
            alias = _id(value, "source alias")
            if alias in aliases and aliases[alias] != source_id:
                raise ValueError(f"Ambiguous source alias: {alias}")
            aliases[alias] = source_id
    return aliases


def explanation_context(assessment, sources):
    """Return minimal source-scoped context shared by prompts and validation.

    Withdrawn/pending evidence never appears in the citable source set. Withdrawn
    source IDs and removed-evidence counts stay visible to explain lost support.
    """
    if not isinstance(assessment, dict):
        raise ValueError("assessment must be an object")
    aliases = _source_aliases(sources)
    withdrawn = set()
    for value in assessment.get("withdrawn_sources", []):
        if value not in aliases:
            raise ValueError(f"Unknown withdrawn source: {value}")
        withdrawn.add(aliases[value])
    checks = []
    check_ids = set()
    for row in _array(assessment.get("checks"), "assessment checks", 50):
        if not isinstance(row, dict):
            raise ValueError("assessment checks must be objects")
        check_id = _id(row.get("id"), "assessment check ID")
        if check_id in check_ids:
            raise ValueError(f"Duplicate assessment check ID: {check_id}")
        check_ids.add(check_id)
        status = row.get("status")
        if status not in CHECK_STATUSES:
            raise ValueError(f"Unknown assessment check status: {status}")
        evidence = []
        for item in row.get("active_evidence", []):
            if not isinstance(item, dict):
                raise ValueError("active_evidence entries must be objects")
            source_id = aliases.get(item.get("source_id"))
            if source_id is None:
                raise ValueError("Assessment refers to an unknown source")
            if source_id not in withdrawn and item.get("review_status") == "source_checked":
                evidence.append({"source_id": source_id, "polarity": item.get("polarity"),
                                 "rationale": item.get("rationale", "")})
        checks.append({
            "id": check_id, "question": row.get("question", ""),
            "status": status, "required": row.get("required", True),
            "reviewed_active_evidence": evidence,
            "allowed_source_ids": sorted({item["source_id"] for item in evidence}),
            "pending_evidence_count": sum(item.get("review_status") == "pending"
                                           for item in row.get("active_evidence", [])),
            "withdrawn_evidence_count": len(row.get("withdrawn_evidence", [])),
            "next_question": row.get("next_question", ""),
            "contact_role": row.get("contact_role", "research collaborator"),
        })
    if not checks:
        raise ValueError("assessment must contain checks")
    followups = []
    for row in checks:
        if row["required"] and row["status"] != "supported":
            followups.append({"check_id": row["id"], "question": row["next_question"],
                              "contact_role": row["contact_role"]})
    cited = {source_id for row in checks for source_id in row["allowed_source_ids"]}
    context = {
        "assessment_id": assessment.get("assessment_id"),
        "target_disease": deepcopy(assessment.get("target_disease", {})),
        "goal": assessment.get("goal", ""),
        "asset": deepcopy(assessment.get("asset", {})),
        "outcome": assessment.get("outcome", ""),
        "checks": checks, "required_next_steps": followups,
        "withdrawn_sources": sorted(withdrawn),
        "sources": {source_id: {"title": sources[source_id].get("title", ""),
                                "url": sources[source_id].get("url", "")}
                    for source_id in sorted(cited)},
        "limitations": assessment.get("limitations", ""),
    }
    # Scope metadata stays data, never evidence or an additional approval.
    # The assessor's status/citation rules remain unchanged when a curator
    # supplies a participant subgroup, proposed use or documented differences.
    for field in ("proposed_use", "target_subgroup", "documented_differences", "assumptions"):
        if field in assessment:
            context[field] = deepcopy(assessment[field])
    return context


def _no_obvious_overclaims(text):
    """Reject a small set of clear positive medical/access overclaims.

    This is a guard for obvious errors, not a semantic truth or safety classifier.
    Negated statements such as 'not clinically validated' remain permitted.
    """
    patterns = (
        r"\b(?:will|can|guaranteed to) cure\b",
        r"\bclinically validated\b", r"\bsafe and effective\b",
        r"\bapproved for (?:reuse|use|our study)\b",
        r"\bno (?:further|additional|expert) review (?:is )?(?:needed|required)\b",
        r"\b(?:should|must) (?:start|take|administer) (?:a |the )?(?:drug|treatment|medication)\b",
        r"\bcan be directly transferred\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            prefix = text[max(0, match.start() - 100):match.start()]
            # Keep negation local to the same sentence and immediate phrase.
            local = re.split(r"[.!?;\n]", prefix)[-1]
            if re.search(r"\b(?:not|never|cannot|can't|doesn't|isn't|hasn't)\b(?:\W+\w+){0,4}\W*$", local, re.I):
                continue
            raise ValueError("Explanation contains an unsupported medical or access overclaim")


def _strings_in(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings_in(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings_in(item)


def _prose_references(text, sources, aliases, active_ids):
    """Check explicit URLs, publication IDs and emails in generated prose.

    Names and biomedical meaning cannot be fully checked by a syntax validator.
    The frontend should render authoritative source links from its registry.
    """
    active_aliases = {value.casefold() for value, source_id in aliases.items()
                      if source_id in active_ids}
    allowed_urls = {sources[source_id].get("url") for source_id in active_ids}
    email_pattern = r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
    allowed_emails = {
        email.casefold() for source_id in active_ids
        for value in _strings_in(sources[source_id])
        for email in re.findall(email_pattern, value)
    }
    for value in re.findall(r"https?://[^\s<>\"'\]]+", text, re.I):
        # Sentence and Markdown punctuation is not part of the supplied URL.
        if value not in allowed_urls and value.rstrip(".,;:!?)}") not in allowed_urls:
            raise ValueError("Generated prose contains an unregistered or unavailable URL")
    for value in re.findall(r"\b(?:DOI:[^\s<>\"'\]\)]+|PMID:\d+)" , text, re.I):
        if value.rstrip(".,;:!?").casefold() not in active_aliases:
            raise ValueError("Generated prose contains an unregistered or unavailable publication ID")
    for value in re.findall(email_pattern, text):
        if value.casefold() not in allowed_emails:
            raise ValueError("Generated prose contains an unregistered contact email")


def validate_explanation(raw, assessment, sources):
    """Validate generated prose against the assessment without changing statuses.

    All checks occur once. Citations must belong to a check's active reviewed
    evidence; withdrawn and pending-only publications cannot be cited. All
    required follow-ups retain the recorded question and collaborator role.
    """
    _keys(raw, EXPLANATION_SCHEMA["required"], "explanation")
    context = explanation_context(assessment, sources)
    by_id = {row["id"]: row for row in context["checks"]}
    aliases = _source_aliases(sources)

    def canonical_ids(values, name, allowed):
        result = []
        for value in _array(values, name, 50):
            value = _id(value, name)
            canonical = aliases.get(value)
            if canonical not in allowed:
                raise ValueError(f"{name} contains an unavailable or unassociated source: {value}")
            if canonical in result:
                raise ValueError(f"{name} repeats a publication or alias: {value}")
            result.append(canonical)
        return result

    rows, seen = [], set()
    for item in _array(raw["check_explanations"], "check_explanations", 50):
        _keys(item, ("check_id", "status", "explanation", "source_ids"), "check explanation")
        check_id = _id(item["check_id"], "check_id")
        if check_id not in by_id or check_id in seen:
            raise ValueError(f"Unknown or repeated explanation check: {check_id}")
        seen.add(check_id)
        check = by_id[check_id]
        if item["status"] != check["status"]:
            raise ValueError(f"Explanation must preserve recorded status for {check_id}")
        explanation = _text(item["explanation"], "check explanation", 2_000)
        _no_obvious_overclaims(explanation)
        source_ids = canonical_ids(item["source_ids"], "check source_ids", set(check["allowed_source_ids"]))
        if check["status"] in {"supported", "refuted", "conflicting"} and not source_ids:
            raise ValueError(f"Evidence-backed status needs a citation: {check_id}")
        for polarity in ("support", "refute"):
            if (check["status"] == "conflicting"
                    or check["status"] == {"support": "supported", "refute": "refuted"}[polarity]):
                relevant = {entry["source_id"] for entry in check["reviewed_active_evidence"]
                            if entry["polarity"] == polarity}
                if not relevant.intersection(source_ids):
                    raise ValueError(f"Check {check_id} needs a {polarity} citation")
        _prose_references(explanation, sources, aliases, set(check["allowed_source_ids"]))
        rows.append({"check_id": check_id, "status": item["status"],
                     "explanation": explanation, "source_ids": source_ids})
    if seen != by_id.keys():
        raise ValueError("Explanation must cover every recorded check exactly once")
    steps, seen_steps = [], set()
    for item in _array(raw["next_steps"], "next_steps", 50):
        _keys(item, ("check_id", "question", "contact_role"), "next step")
        check_id = _id(item["check_id"], "next step check_id")
        if check_id not in by_id or check_id in seen_steps:
            raise ValueError(f"Unknown or repeated next-step check: {check_id}")
        seen_steps.add(check_id)
        question = _text(item["question"], "next-step question", 2_000)
        role = _text(item["contact_role"], "next-step contact_role", 300)
        check = by_id[check_id]
        if _flat(question) != _flat(check["next_question"]) or _flat(role) != _flat(check["contact_role"]):
            raise ValueError("Next steps must preserve the recorded question and contact role")
        steps.append({"check_id": check_id, "question": question, "contact_role": role})
    required_steps = {row["check_id"] for row in context["required_next_steps"]}
    if not required_steps <= seen_steps:
        raise ValueError("Explanation is missing a required follow-up")
    cited = canonical_ids(raw["cited_source_ids"], "cited_source_ids", set(context["sources"]))
    used = {source_id for row in rows for source_id in row["source_ids"]}
    if set(cited) != used:
        raise ValueError("cited_source_ids must match the publications cited by check explanations")
    summary = _text(raw["summary"], "summary", 3_000)
    draft = _text(raw["draft_message"], "draft_message", 5_000)
    _no_obvious_overclaims(summary)
    _no_obvious_overclaims(draft)
    _prose_references(summary, sources, aliases, set(context["sources"]))
    _prose_references(draft, sources, aliases, set(context["sources"]))
    return {"summary": summary, "check_explanations": rows, "next_steps": steps,
            "cited_source_ids": cited, "draft_message": draft}


def explanation_generation_schema(assessment, sources):
    """Model prose fields only; recorded ledger fields are bound by the server."""
    context = explanation_context(assessment, sources)
    return _object({
        "summary": _string(),
        "check_explanations": {"type": "array", "items": _object({
            "check_id": {"type": "string", "enum": [row["id"] for row in context["checks"]]},
            "explanation": _string(),
        })},
        "draft_message": _string(),
    })


def bind_explanation_selection(raw, assessment, sources):
    """Bind exact ledger fields, then apply the unchanged public validator.

    The generated prose cannot assign statuses, fabricate publication identifiers
    or rewrite recorded follow-up questions. References identify evidence attached
    to each recorded check, not independent verification of the generated prose.
    """
    _keys(raw, ("summary", "check_explanations", "draft_message"), "explanation selection")
    context = explanation_context(assessment, sources)
    by_id = {row["id"]: row for row in context["checks"]}
    rows, seen = [], set()
    for item in _array(raw["check_explanations"], "check_explanations", 50):
        _keys(item, ("check_id", "explanation"), "check prose selection")
        check_id = _id(item["check_id"], "check_id")
        if check_id not in by_id or check_id in seen:
            raise ValueError("Unknown or repeated explanation check")
        seen.add(check_id)
        check = by_id[check_id]
        rows.append({"check_id": check_id, "status": check["status"],
                     "explanation": item["explanation"],
                     "source_ids": list(check["allowed_source_ids"])})
    if seen != by_id.keys():
        raise ValueError("Explanation must cover every recorded check exactly once")
    bound = {
        "summary": raw["summary"], "check_explanations": rows,
        "next_steps": deepcopy(context["required_next_steps"]),
        "cited_source_ids": sorted({source_id for row in rows for source_id in row["source_ids"]}),
        "draft_message": raw["draft_message"],
    }
    return validate_explanation(bound, assessment, sources)


def validate_explanation_selection(raw, assessment, sources):
    """Return only validated prose selections so cache validation is idempotent."""
    bound = bind_explanation_selection(raw, assessment, sources)
    return {
        "summary": bound["summary"],
        "check_explanations": [{"check_id": row["check_id"], "explanation": row["explanation"]}
                               for row in bound["check_explanations"]],
        "draft_message": bound["draft_message"],
    }
