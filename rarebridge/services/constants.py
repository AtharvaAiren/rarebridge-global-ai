"""Shared constants for the backend lane. Values mirror the frozen contract."""

SCHEMA_VERSION = "rarebridge.handoff.v1"

# Only goal required for the MVP. Unknown goals receive HTTP 422.
SUPPORTED_GOALS = {
    "natural_history": "Plan or inform a natural-history study",
}
DEFAULT_GOAL = "natural_history"

EVIDENCE_REVIEW_STATES = ("pending", "source_checked")
CHECK_STATES = ("supported", "refuted", "conflicting", "unknown", "needs_source_review")
OUTCOMES = (
    "candidate_for_expert_review",
    "needs_information",
    "needs_source_review",
    "needs_expert_review",
    "not_supported_for_stated_use",
)

PENDING_LABEL = "Unassessed \u2014 source review pending"
CHECKED_LABEL = "Narrow source fact checked (not clinical validation)"
INFERRED_PENDING_LABEL = "Inferred navigation link \u2014 source review pending"

# Relations that would assert therapeutic or eligibility transfer. The graph
# must never serve them; tests assert their absence.
FORBIDDEN_RELATIONS = {
    "can_share_treatment",
    "can_reuse_asset",
    "eligible_for_trial",
    "treats",
    "shares_treatment_with",
}

SEARCH_LIMIT_MIN, SEARCH_LIMIT_MAX, SEARCH_LIMIT_DEFAULT = 1, 25, 10
GRAPH_NODES_MIN, GRAPH_NODES_MAX, GRAPH_NODES_DEFAULT = 5, 150, 40
