Collaboration brief adapter

Import:
    from rarebridge.ai.brief import build_collaboration_brief
    brief = build_collaboration_brief(assessment_response)

Input is the rarebridge.handoff.v1 assessment response, with after, sources,
contacts, coverage, explanation and data_origin. before is intentionally not used
for current facts. The input is never changed. Empty sources are valid for a
source-free assessment with unknown checks. Unknown references, ambiguous aliases,
or an after state still citing withdrawn sources raise ValueError.

Output is an additive rarebridge.brief.v1 object:
  assessment_id, target_disease, target_subgroup, goal, asset, proposed_use,
  outcome, outcome_explanation, recorded_support, unanswered_checks,
  followup_questions, documented_differences, excluded_differences, sources,
  excluded_sources, public_collaborator_routes, excluded_collaborator_routes,
  coverage, assumptions, next_milestone, generation_mode, draft_origin,
  explanation_text, provenance, draft_message, text_export.

sources is a canonical-ID dictionary containing only active source records used
in checks, routes, differences or accepted generated prose. Aliases resolve to
one record. excluded_sources is separate metadata, not support. Withdrawn paper
URLs are withheld from resource and collaborator links as well as citations.
text_export shows the current outcome, support, negative/unknown checks, questions,
source titles/URLs, public routes, exclusions, coverage and a reviewable draft.
Structured excluded-source metadata retains its URL for provenance, but the
plain-text exclusion list does not print that URL as a usable reference.

Follow-up questions remain proposals. Optional checks are retained and labelled
additional; unresolved required checks remain prominent. A public contact route
does not establish current ownership, availability or willingness to collaborate.
If contacts are absent, explicitly recorded asset routes can be shown as
unreviewed. No contact is fabricated or contacted. Access permissions, instrument
licenses, clinical suitability and treatment benefit are never inferred.

Optional proposed_use can be a string or object on after/the response. Optional
documented_differences accepts objects with text, source_ids and review_status;
unreviewed differences are labelled, and withdrawn backing removes the assertion
from the current export. target_subgroup is copied when available and otherwise
shown as not specified.

AI draft integration:
    brief = build_collaboration_brief(response, explanation=validated_explanation)

Only live/cached explanations with the lead service marker are accepted:
    validation = {
      "status": "passed",
      "checks": ["schema", "status_alignment", "citation_scope",
                 "required_followups"]
    }
The explanation also supplies draft_message, cited_source_ids, text and model.
It must include provenance.assessment_sha256 matching the exact current after
assessment: SHA256 of json.dumps(after, ensure_ascii=False, sort_keys=True,
separators=(',', ':')).encode('utf-8'). A changed status, subgroup or other scope
field invalidates old generated prose even if the assessment ID and citations
are unchanged. Missing fingerprints cause the deterministic fallback too.
Citation IDs must resolve to active sources. Stale/unvalidated generated prose
falls back to a deterministic template with generation_mode='none' and a rejection
reason in provenance. An unknown source reference raises ValueError even if a
validation marker is supplied. This marker is an internal service assertion;
the web client should not be permitted to self-certify generated prose.

The brief adapter does not make model calls, validate biology, or change assessment
statuses. Source/context validation belongs to the assessment and lead AI service.
Rendering and browser print/save-PDF remain Saanvi's responsibility.

Run from the workspace root:
    python3 -m unittest rarebridge.ai.tests.test_brief -v

Tests use the actual shared fixtures plus explicitly synthetic adverse cases.
They check software provenance and export behavior, not biomedical correctness.
