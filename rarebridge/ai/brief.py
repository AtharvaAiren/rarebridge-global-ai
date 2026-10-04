"""Assemble an inspectable collaboration proposal from the current assessment.

This is a deterministic adapter, not another assessment engine. It preserves
recorded statuses, resolves publication aliases once, and excludes withdrawn
evidence. Generated prose is optional; the facts and questions remain recorded
data. This module uses only the Python 3.10+ standard library.
"""

from copy import deepcopy
import hashlib
import ipaddress
import json
import re
from urllib.parse import unquote, urlsplit


SCHEMA_VERSION = "rarebridge.brief.v1"
_STATUSES = {"supported", "unknown", "needs_source_review", "refuted", "conflicting"}
_OUTCOMES = {
    "needs_information": "More information is needed before a feasibility decision.",
    "needs_source_review": "Recorded evidence needs source review before a feasibility decision.",
    "needs_expert_review": "Conflicting recorded evidence requires expert review.",
    "not_supported_for_stated_use": "Recorded checks do not support the stated use.",
    "candidate_for_expert_review": "The recorded checks support consideration by an expert; suitability and access are not approved.",
}
_AI_CHECKS = {"schema", "status_alignment", "citation_scope", "required_followups"}


def _assessment_hash(assessment):
    encoded = json.dumps(assessment, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _object(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _list(value, name):
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value.strip()


def _public_url(value):
    """Recognize displayable public routes; this function never fetches a URL."""
    if not isinstance(value, str) or any(char.isspace() for char in value):
        return False
    try:
        parsed = urlsplit(value)
        if parsed.scheme == "mailto":
            return not parsed.query and bool(re.fullmatch(r"[^@/?#]+@[^@/?#]+\.[^@/?#]+", parsed.path))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username or parsed.password:
            return False
        hostname = parsed.hostname.lower()
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
            return False
        try:
            return ipaddress.ip_address(hostname).is_global
        except ValueError:
            return "." in hostname
    except ValueError:
        return False


def _source_index(sources):
    sources = _object(sources, "sources")
    aliases = {}
    for source_id, raw in sources.items():
        _text(source_id, "source ID")
        source = _object(raw, f"source {source_id}")
        _text(source.get("title"), f"source {source_id} title")
        if not _public_url(source.get("url")) or source["url"].startswith("mailto:"):
            raise ValueError(f"Source {source_id} needs a public HTTP(S) URL")
        names = [source_id, *_list(source.get("aliases", []), f"source {source_id} aliases")]
        for alias in names:
            _text(alias, f"source {source_id} alias")
            previous = aliases.setdefault(alias, source_id)
            if previous != source_id:
                raise ValueError(f"Ambiguous source alias: {alias}")
    return aliases


def _resolve_ids(values, aliases, name):
    result = set()
    for value in _list(values, name):
        if not isinstance(value, str) or value not in aliases:
            raise ValueError(f"Unknown source in {name}: {value!r}")
        result.add(aliases[value])
    return sorted(result)


def _publication_for_url(url, aliases):
    """Resolve common DOI/PubMed identity links without discovering new aliases."""
    if not isinstance(url, str):
        return None
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    path = unquote(parsed.path).strip("/")
    candidates = []
    if host in {"doi.org", "www.doi.org", "dx.doi.org"}:
        candidates = ["DOI:" + path]
    elif host == "pubmed.ncbi.nlm.nih.gov" and path.isdigit():
        candidates = ["PMID:" + path]
    elif host in {"ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"} and path.startswith("pubmed/"):
        candidates = ["PMID:" + path.removeprefix("pubmed/")]
    folded = {key.lower(): value for key, value in aliases.items()}
    return next((folded[item.lower()] for item in candidates if item.lower() in folded), None)


def _check_rows(after, aliases, withdrawn):
    rows, seen = [], set()
    for raw in _list(after.get("checks"), "after.checks"):
        check = _object(raw, "check")
        check_id = _text(check.get("id"), "check ID")
        if check_id in seen:
            raise ValueError(f"Duplicate check ID: {check_id}")
        seen.add(check_id)
        status = check.get("status")
        if status not in _STATUSES:
            raise ValueError(f"Unrecognized recorded check status: {status!r}")
        support = _resolve_ids(check.get("supporting_sources", []), aliases, f"{check_id} supporting_sources")
        refute = _resolve_ids(check.get("refuting_sources", []), aliases, f"{check_id} refuting_sources")
        evidence = []
        for raw_item in _list(check.get("active_evidence", []), f"{check_id} active_evidence"):
            item = deepcopy(_object(raw_item, f"{check_id} evidence"))
            item["source_id"] = _resolve_ids([item.get("source_id")], aliases, f"{check_id} evidence")[0]
            if item["source_id"] in withdrawn:
                raise ValueError(f"Current check {check_id} still cites a withdrawn source")
            if item.get("polarity") not in {"support", "refute", "uncertain"}:
                raise ValueError(f"Unrecognized evidence polarity for {check_id}")
            if item.get("review_status") not in {"pending", "source_checked"}:
                raise ValueError(f"Unrecognized evidence review status for {check_id}")
            _text(item.get("rationale"), f"{check_id} evidence rationale")
            if item not in evidence:
                evidence.append(item)
        if set(support + refute) & withdrawn:
            raise ValueError(f"Current check {check_id} still cites a withdrawn source")
        if status == "supported" and not support:
            raise ValueError(f"Supported check {check_id} has no active supporting source")
        if status in {"refuted", "conflicting"} and not refute:
            raise ValueError(f"Negative/conflicting check {check_id} has no active refuting source")
        if status == "conflicting" and not support:
            raise ValueError(f"Conflicting check {check_id} has no active supporting source")
        rows.append({
            "check_id": check_id,
            "question": _text(check.get("question"), f"{check_id} question"),
            "required": check.get("required", True),
            "category": check.get("category", "research"),
            "status": status,
            "supporting_source_ids": support,
            "refuting_source_ids": refute,
            "source_ids": sorted(set(support + refute + [item["source_id"] for item in evidence])),
            "recorded_evidence": evidence,
            "next_question": check.get("next_question") or f"What evidence or confirmation is needed to resolve: {check['question']}",
            "contact_role": check.get("contact_role") or "research collaborator",
            "fact_origin": "recorded_assessment",
        })
    if not rows:
        raise ValueError("The current assessment needs at least one recorded check")
    return rows


def _followups(after, rows):
    by_id = {row["check_id"]: row for row in rows}
    supplied = {}
    for raw in _list(after.get("followup_questions", []), "after.followup_questions"):
        item = _object(raw, "follow-up question")
        check_id = item.get("check_id")
        if check_id not in by_id:
            raise ValueError(f"Follow-up references unknown check: {check_id!r}")
        if by_id[check_id]["status"] == "supported":
            continue
        if check_id in supplied:
            raise ValueError(f"Duplicate follow-up for check: {check_id}")
        supplied[check_id] = item
    questions = []
    for row in rows:
        if row["status"] == "supported":
            continue
        item = supplied.get(row["check_id"], {})
        questions.append({
            "check_id": row["check_id"],
            "question": _text(item.get("question", row["next_question"]), "follow-up question"),
            "contact_role": item.get("contact_role") or row["contact_role"],
            "reason": row["status"],
            "required": row["required"],
            "question_origin": "proposed_followup",
        })
    return questions


def _contacts(response, asset, aliases, withdrawn, excluded_urls):
    contacts, excluded, seen = [], [], set()
    candidates = deepcopy(_list(response.get("contacts", []), "contacts"))
    if not candidates:
        # These are recorded public links, not inferred owners or verified contacts.
        for raw in _list(asset.get("public_researcher_routes", []), "asset.public_researcher_routes"):
            item = _object(raw, "public researcher route")
            candidates.append({
                "id": item.get("id"), "label": item.get("name", item.get("label")),
                "url": item.get("url"), "kind": "researcher",
                "role": item.get("role", "Recorded public researcher route; ownership and availability unconfirmed"),
                "source_ids": item.get("source_ids", []), "review_status": "pending",
                "last_checked": item.get("last_checked"),
            })
    for raw in candidates:
        item = _object(raw, "contact")
        label = item.get("label") or item.get("name")
        if not isinstance(label, str) or not label.strip() or not _public_url(item.get("url")):
            excluded.append({"id": item.get("id"), "label": label, "reason": "invalid_public_route"})
            continue
        source_ids = _resolve_ids(item.get("source_ids", []), aliases, f"contact {label} source_ids")
        active = sorted(set(source_ids) - withdrawn)
        publication = _publication_for_url(item["url"], aliases)
        if (source_ids and not active) or item["url"] in excluded_urls or publication in withdrawn:
            excluded.append({"id": item.get("id"), "label": label, "reason": "source_backing_withdrawn", "excluded_source_ids": source_ids})
            continue
        identity = (item.get("id") or label, item["url"])
        if identity in seen:
            continue
        seen.add(identity)
        review = item.get("review_status", "pending")
        if review not in {"pending", "source_checked"}:
            raise ValueError(f"Unrecognized contact review status for {label}")
        contacts.append({
            "id": item.get("id"), "label": label.strip(), "url": item["url"],
            "kind": item.get("kind", "researcher"), "role": item.get("role", "Public collaborator route"),
            "source_ids": active, "review_status": review, "last_checked": item.get("last_checked"),
            "source_backed": bool(active),
            "status_for_brief": "source_checked" if active and review == "source_checked" else "unreviewed",
            "availability": "Current ownership, availability and willingness to collaborate require confirmation.",
        })
    return contacts, excluded


def _differences(response, after, aliases, withdrawn):
    result, excluded = [], []
    raw_differences = after.get("documented_differences", response.get("documented_differences", []))
    for raw in _list(raw_differences, "documented_differences"):
        item = {"text": raw, "source_ids": [], "review_status": "pending"} if isinstance(raw, str) else deepcopy(_object(raw, "difference"))
        text = _text(item.get("text", item.get("description")), "difference text")
        ids = _resolve_ids(item.get("source_ids", []), aliases, "difference source_ids")
        active = sorted(set(ids) - withdrawn)
        if ids and not active:
            excluded.append({"text": text, "reason": "source_backing_withdrawn", "excluded_source_ids": ids})
            continue
        review = item.get("review_status", "pending")
        if review not in {"pending", "source_checked"}:
            raise ValueError("Unrecognized difference review status")
        result.append({"text": text, "source_ids": active, "review_status": review,
                       "status_for_brief": "source_checked" if active and review == "source_checked" else "unreviewed"})
    return result, excluded


def _accepted_explanation(raw, after, aliases, withdrawn, allowed_urls):
    if raw is None:
        return None, None
    raw = _object(raw, "explanation")
    mode = raw.get("generation_mode", "none")
    if mode == "none":
        return None, None
    validation = raw.get("validation")
    if mode not in {"live", "cached"} or not isinstance(validation, dict):
        return None, "Generated draft lacked service validation."
    checks = validation.get("checks")
    if (validation.get("status") != "passed" or not isinstance(checks, list)
            or not all(isinstance(item, str) for item in checks) or not _AI_CHECKS.issubset(set(checks))):
        return None, "Generated draft lacked service validation."
    if raw.get("assessment_id", after["assessment_id"]) != after["assessment_id"]:
        return None, "Generated draft referred to a different assessment."
    provenance = raw.get("provenance")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("assessment_sha256"), str):
        return None, "Generated draft lacked a fingerprint of the current assessment."
    if provenance["assessment_sha256"] != _assessment_hash(after):
        return None, "Generated draft was prepared for a different assessment state."
    ids = _resolve_ids(raw.get("cited_source_ids", []), aliases, "explanation cited_source_ids")
    if set(ids) & withdrawn:
        return None, "Generated draft cited an excluded source."
    draft = raw.get("draft_message")
    if not isinstance(draft, str) or not draft.strip():
        return None, "Generated explanation did not supply a validated draft message."
    text = raw.get("text")
    if text is not None and not isinstance(text, str):
        return None, "Generated explanation text was malformed."
    # A validated wrapper cannot make an unlisted external URL into a citation.
    for part in (draft, text or ""):
        for url in re.findall(r"https?://[^\s<>\]\)]+", part):
            if url.rstrip(".,;") not in allowed_urls:
                return None, "Generated draft contained an unapproved source or route URL."
        if any(source_id in part for source_id in aliases if aliases[source_id] in withdrawn):
            return None, "Generated draft mentioned an excluded source identifier."
    return dict(deepcopy(raw), cited_source_ids=ids), None


def _citation(ids, numbers):
    return " " + " ".join(f"[{numbers[item]}]" for item in ids) if ids else ""


def _readable_value(value):
    if isinstance(value, dict):
        return "; ".join(f"{key.replace('_', ' ').capitalize()}: {_readable_value(item)}" for key, item in value.items())
    if isinstance(value, list):
        return ", ".join(_readable_value(item) for item in value)
    if value is None:
        return "Not specified"
    return str(value)


def _default_draft(brief, numbers):
    lines = [f"Subject: Research feasibility discussion — {brief['target_disease']['label']}", "", "Hello,", "",
             f"[Organization name] is exploring this goal for {brief['target_disease']['label']}: {brief['goal']}.",
             f"We would like expert guidance on the proposed use of {brief['asset']['label']}.",
             _OUTCOMES[brief["outcome"]]]
    if brief["recorded_support"]:
        lines.extend(["", "The recorded evidence supports these specific checks:"])
        for row in brief["recorded_support"]:
            lines.append(f"- {row['question']}" + _citation(row["supporting_source_ids"], numbers))
    if brief["outcome"] == "not_supported_for_stated_use":
        lines.append("We would like to understand whether an alternative resource or a materially different scope would be appropriate.")
    if brief["followup_questions"]:
        lines.extend(["", "Questions we would like to resolve:"])
        for index, item in enumerate(brief["followup_questions"], 1):
            optional = " (additional question)" if not item["required"] else ""
            lines.append(f"{index}. {item['question']}{optional}")
    lines.extend(["", "Our proposed next milestone is an expert-reviewed natural-history feasibility decision, with an agreed scope and remaining requirements.",
                  "Could you help resolve these questions or direct us to the appropriate team?", "", "Best wishes,", "[Your name / organization]"])
    return "\n".join(lines)


def _export(brief, numbers):
    asset = brief["asset"]
    lines = ["RareBridge — collaboration brief", "", f"Target: {brief['target_disease']['label']} ({brief['target_disease']['id']})",
             f"Goal: {brief['goal']}", f"Resource: {asset['label']} ({asset['id']})"]
    if asset.get("url"):
        lines.append(f"Resource link: {asset['url']}")
    elif asset.get("url_excluded"):
        lines.append("Resource publication link withheld with the excluded evidence.")
    lines.extend([f"Recorded outcome: {brief['outcome']}", _OUTCOMES[brief["outcome"]],
                  f"Access: {asset.get('access_status') or 'Access conditions not recorded.'}", "",
                  "Proposed use (proposal, not an established result):",
                  _readable_value(brief["proposed_use"]),
                  "Target subgroup: " + _readable_value(brief["target_subgroup"])])
    if brief.get("explanation_text"):
        lines.extend(["", "AI explanation (service-validated):", brief["explanation_text"]])
    lines.extend(["", "Recorded support:"])
    if not brief["recorded_support"]:
        lines.append("No supported checks remain in this recorded assessment.")
    for row in brief["recorded_support"]:
        lines.append(f"- {row['question']} — supported" + _citation(row["supporting_source_ids"], numbers))
        for item in row["recorded_evidence"]:
            if item["polarity"] == "support" and item["review_status"] == "source_checked":
                lines.append("  Recorded rationale: " + item["rationale"] + _citation([item["source_id"]], numbers))
    lines.extend(["", "Unresolved or negative checks:"])
    if not brief["unanswered_checks"]:
        lines.append("No unresolved recorded checks; expert review is still the next milestone.")
    for row in brief["unanswered_checks"]:
        importance = "required" if row["required"] else "additional"
        lines.append(f"- {row['question']} — {row['status']} ({importance})" + _citation(row["source_ids"], numbers))
        for item in row["recorded_evidence"]:
            lines.append(f"  Recorded {item['polarity']} rationale ({item['review_status']}): {item['rationale']}" + _citation([item["source_id"]], numbers))
    if brief["documented_differences"]:
        lines.extend(["", "Recorded differences:"])
        for item in brief["documented_differences"]:
            lines.append(f"- {item['text']} ({item['status_for_brief']})" + _citation(item["source_ids"], numbers))
    lines.extend(["", "Questions for collaboration (proposed next actions):"])
    for index, item in enumerate(brief["followup_questions"], 1):
        lines.append(f"{index}. {item['question']} — ask a {item['contact_role']}.")
    lines.extend(["", "Public collaborator routes:"])
    if not brief["public_collaborator_routes"]:
        lines.append("No usable public collaborator route is recorded in the current evidence slice. Ask a relevant patient organization or study team to identify a suitable contact.")
    for item in brief["public_collaborator_routes"]:
        lines.append(f"- {item['label']}: {item['url']} ({item['status_for_brief']})" + _citation(item["source_ids"], numbers))
        lines.append(f"  {item['role']}. {item['availability']}")
    if brief["excluded_collaborator_routes"]:
        lines.append(f"{len(brief['excluded_collaborator_routes'])} recorded route(s) withheld because their backing was excluded or the public route was invalid.")
    lines.extend(["", "Proposed next milestone:", brief["next_milestone"]["description"], "", "Sources used (distinct records; aliases counted once):"])
    if not brief["sources"]:
        lines.append("No active source is cited in this brief.")
    for source_id, source in brief["sources"].items():
        lines.append(f"[{numbers[source_id]}] {source['title']} — {source['url']} ({source_id})")
    if brief["excluded_sources"]:
        lines.extend(["", "Excluded sources (not supporting this brief):"])
        for source in brief["excluded_sources"]:
            lines.append(f"- {source['title']} ({source['canonical_id']}) — withdrawn for this assessment view.")
    lines.extend(["", "Coverage:", brief["coverage"], "", "Assumptions and limits:"])
    lines.extend(f"- {item}" for item in brief["assumptions"])
    lines.extend(["", f"Data origin: {brief['provenance']['data_origin']}",
                  f"Draft generation: {brief['generation_mode']} ({brief['draft_origin']})",
                  "", "Draft message — review before use:", brief["draft_message"]])
    return "\n".join(lines) + "\n"


def build_collaboration_brief(assessment_response: dict, *, explanation: dict | None = None) -> dict:
    """Return an additive brief from an API assessment envelope without mutation.

    The ``after`` assessment is authoritative even when every source is hidden.
    Invalid references raise ValueError; stale or unvalidated generated prose is
    replaced by a clearly labelled deterministic draft. A public link identifies
    a possible route, never ownership, permission or willingness to collaborate.
    """
    response = _object(assessment_response, "assessment_response")
    after = _object(response.get("after"), "after")
    _text(after.get("assessment_id"), "assessment_id")
    target = deepcopy(_object(after.get("target_disease"), "target_disease"))
    _text(target.get("id"), "target disease ID")
    _text(target.get("label"), "target disease label")
    goal = _text(after.get("goal"), "goal")
    raw_asset = _object(after.get("asset"), "asset")
    asset = {key: deepcopy(raw_asset[key]) for key in ("id", "label", "type", "url", "access_status") if key in raw_asset}
    _text(asset.get("id"), "asset ID")
    _text(asset.get("label"), "asset label")
    outcome = after.get("outcome")
    if outcome not in _OUTCOMES:
        raise ValueError(f"Unrecognized recorded outcome: {outcome!r}")
    sources = _object(response.get("sources"), "sources")
    aliases = _source_index(sources)
    withdrawn = set(_resolve_ids(after.get("withdrawn_sources", []), aliases, "withdrawn_sources"))
    excluded_urls = {sources[source_id]["url"] for source_id in withdrawn}
    rows = _check_rows(after, aliases, withdrawn)
    followups = _followups(after, rows)
    contacts, excluded_contacts = _contacts(response, raw_asset, aliases, withdrawn, excluded_urls)
    differences, excluded_differences = _differences(response, after, aliases, withdrawn)
    if asset.get("url") in excluded_urls or _publication_for_url(asset.get("url"), aliases) in withdrawn:
        asset["url"] = None
        asset["url_excluded"] = True
    elif asset.get("url") and not _public_url(asset["url"]):
        asset["url"] = None
        asset["url_invalid"] = True
    allowed_urls = {source["url"] for source_id, source in sources.items() if source_id not in withdrawn}
    allowed_urls.update(item["url"] for item in contacts)
    accepted, rejected_reason = _accepted_explanation(
        explanation if explanation is not None else response.get("explanation"), after,
        aliases, withdrawn, allowed_urls,
    )
    used = {source_id for row in rows for source_id in row["source_ids"]}
    used.update(source_id for item in contacts + differences for source_id in item["source_ids"])
    if accepted:
        used.update(accepted["cited_source_ids"])
    active_sources = {source_id: deepcopy(sources[source_id]) for source_id in sorted(used)}
    numbers = {source_id: number for number, source_id in enumerate(active_sources, 1)}
    proposed_use = after.get("proposed_use", response.get("proposed_use"))
    if proposed_use is None:
        proposed_use = f"Explore whether {asset['label']} can support this goal for {target['label']}: {goal}."
    if not isinstance(proposed_use, (str, dict)):
        raise ValueError("proposed_use must be a string or object")
    coverage = response.get("coverage") or "Only the supplied assessment and source records are covered; completeness is not established."
    _text(coverage, "coverage")
    recorded_assumptions = after.get("assumptions", response.get("assumptions", []))
    assumptions = [_text(item, "assumption") for item in _list(recorded_assumptions, "assumptions")]
    assumptions.extend([
        "Proposed participants, subgroup, sites and local capacity require confirmation unless explicitly recorded.",
        "Publication or public-web access does not grant permission to use study materials, datasets or licensed instruments.",
        "Recorded support is scoped to each check; it does not establish treatment benefit or approval to implement the resource.",
    ])
    brief = {
        "schema_version": SCHEMA_VERSION, "assessment_id": after["assessment_id"],
        "target_disease": target, "goal": goal, "asset": asset, "outcome": outcome,
        "outcome_explanation": _OUTCOMES[outcome], "proposed_use": deepcopy(proposed_use),
        "target_subgroup": deepcopy(after.get("target_subgroup", target.get("subgroup"))),
        "recorded_support": [row for row in rows if row["status"] == "supported"],
        "unanswered_checks": [row for row in rows if row["status"] != "supported"],
        "followup_questions": followups, "documented_differences": differences,
        "excluded_differences": excluded_differences,
        "sources": active_sources,
        "excluded_sources": [dict(deepcopy(sources[source_id]), canonical_id=source_id, reason="withdrawn") for source_id in sorted(withdrawn)],
        "public_collaborator_routes": contacts, "excluded_collaborator_routes": excluded_contacts,
        "coverage": coverage,
        "assumptions": list(dict.fromkeys(assumptions)),
        "next_milestone": {
            "id": "expert_reviewed_natural_history_feasibility_decision",
            "status": "proposed",
            "description": "An expert-reviewed natural-history feasibility decision: agree the target population, assess this resource and alternatives, resolve access and implementation requirements, and record whether to proceed, adapt the scope, or seek another resource.",
            "success_criteria": ["Unresolved required checks reviewed with appropriate collaborators.",
                                 "Proposed population and study capacity explicitly scoped.",
                                 "Access conditions and any outstanding approvals identified.",
                                 "Decision and remaining questions documented."],
        },
        "generation_mode": accepted["generation_mode"] if accepted else "none",
        "draft_origin": "ai_service_validated" if accepted else "deterministic_template",
        "explanation_text": accepted.get("text") if accepted else None,
        "provenance": {
            "assessment_state": "after", "data_origin": response.get("data_origin", "unspecified"),
            "assessment_sha256": _assessment_hash(after),
            "generation_mode": accepted["generation_mode"] if accepted else "none",
            "model": accepted.get("model") if accepted else None,
            "provider": accepted["provenance"].get("provider") if accepted else None,
            "response_id": accepted["provenance"].get("response_id") if accepted else None,
            "validation": deepcopy(accepted["validation"]) if accepted else None,
            "ai_rejection_reason": rejected_reason,
            "distinct_sources_used": len(active_sources), "withdrawn_source_ids": sorted(withdrawn),
            "source_coverage": "Distinct source records used for checks or routes; no claim of a complete literature search.",
        },
    }
    brief["draft_message"] = accepted["draft_message"].strip() if accepted else _default_draft(brief, numbers)
    brief["text_export"] = _export(brief, numbers)
    return brief
