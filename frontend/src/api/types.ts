/**
 * Response shapes from contracts/API_CONTRACT.txt (rarebridge.handoff.v1).
 * Fields marked optional are additive extras from the live API; demo files
 * may lack them, so always read them with optional chaining.
 */

export type ReviewStatus = 'pending' | 'source_checked'

export type CheckStatus =
  | 'supported'
  | 'refuted'
  | 'conflicting'
  | 'unknown'
  | 'needs_source_review'

export type AssessmentOutcome =
  | 'candidate_for_expert_review'
  | 'needs_information'
  | 'needs_source_review'
  | 'needs_expert_review'
  | 'not_supported_for_stated_use'

export interface ErrorEnvelope {
  schema_version: string
  error: {
    code: string
    message: string
    details: unknown[]
  }
}

export interface HealthResponse {
  schema_version: string
  status: string
  capabilities: {
    search: boolean
    assessment: boolean
    graph: boolean
    curation_overlay: boolean
    ai_extraction: boolean
    ai_explanation: boolean
    ai_discovery?: boolean
    ai_assistant?: boolean
  }
  data_snapshot: string
  data_origin?: string
  ai_status_note?: string
  goals?: string[]
}

export interface SearchItem {
  id: string
  type: string
  label: string
  matched_on: string
  disease_ids: string[]
  matched_text?: string
}

export interface SearchResponse {
  schema_version: string
  query: string
  items: SearchItem[]
  coverage: {
    disease_count: number
    scope_note: string
  }
  total_matches?: number
  limit?: number
}

export interface Contact {
  id: string
  label: string
  kind: 'organization' | 'researcher' | 'study_team'
  url: string
  role: string
  source_ids: string[]
  review_status: ReviewStatus
  last_checked: string | null
  relevance?: string
  additional_routes?: unknown[]
  all_sources_withdrawn?: boolean
}

export interface Source {
  title: string
  url: string
  aliases: string[]
  published_on: string | null
  source_kind: string
  note: string
  withdrawn_in_this_view?: boolean
  snapshot_commit?: string
  content_license?: string
}

export type SourceMap = Readonly<Record<string, Source>>

/** graph.json node shape: {id,type,label,...attributes}. */
export interface GraphNode {
  id: string
  type: string
  label: string
  review_status?: ReviewStatus
  origin?: string
  url?: string
  aliases?: string[]
  synonyms?: string[]
  asset_type?: string
  access_status?: string
  claim_type?: string
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  relation: string
  provenance: Readonly<Record<string, unknown>>
  review_status: ReviewStatus
  source_ids: string[]
  confidence_label: string
  explanation: string
  claim_origin?: ClaimOrigin
  assessment_id?: string
  check_id?: string
  check_status?: CheckStatus
}

export interface GraphResponse {
  schema_version: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  sources: SourceMap
  coverage: {
    scope_note: string
    truncated: boolean
    total_nodes: number
    total_edges: number
    shown_nodes?: number
    omitted_relevant_nodes?: number
    skipped_groups?: string[]
    max_nodes?: number
  }
  data_origin: string
}

export interface DiseaseSummary {
  id: string
  type: 'disease'
  label: string
  summary: string
  summary_note?: string
  synonyms?: string[]
  summary_source_ids?: string[]
  summary_review_status?: ReviewStatus
}

export type ClaimOrigin = 'imported' | 'recorded' | 'inferred'

export interface RecordedRoute {
  explanation: string
  kind?: string
  node_path?: string[]
  source_ids?: string[]
  review_status?: ReviewStatus
  claim_origin?: ClaimOrigin
  edge_ids?: string[]
}

export interface SharedTerm {
  id: string
  label: string
  type: string
}

export interface RelatedDisease {
  id: string
  label: string
  reason: string
  basis_claim_ids: string[]
  source_ids: string[]
  review_status: ReviewStatus
  ranking_method?: string
  recorded_routes?: RecordedRoute[]
  shared_terms?: SharedTerm[]
  organizations?: Contact[]
}

export interface Asset {
  id: string
  label: string
  type: string
  url: string
  access_status: string
}

export interface Opportunity {
  id: string
  asset: Asset
  assessment_id: string
  reason: string
  source_ids: string[]
  candidate_score: number | null
  ranking_method: string
  outcome?: AssessmentOutcome
  open_required_check_ids?: string[]
}

export interface UnassessedAsset {
  asset: Asset
  assessment_id: null
  reason: string
  source_ids?: string[]
  review_status?: ReviewStatus
}

export interface OverviewResponse {
  schema_version: string
  disease: DiseaseSummary
  goal_id: string
  goal_label?: string
  related_diseases: RelatedDisease[]
  opportunities: Opportunity[]
  unassessed_assets?: UnassessedAsset[]
  organizations: Contact[]
  coverage: {
    disease_count: number
    scope_note: string
    gaps?: string[]
  }
  data_origin: string
}

// ---------- Assessment evaluation (POST /api/assessments/evaluate) ----------

export interface EvidenceItem {
  source_id: string
  polarity: string
  review_status: ReviewStatus
  rationale: string
}

export interface AssessmentCheck {
  id: string
  question: string
  required: boolean
  status: CheckStatus
  active_evidence: EvidenceItem[]
  withdrawn_evidence: EvidenceItem[]
  next_question: string
  contact_role: string
  category?: string
}

export interface FollowupQuestion {
  check_id: string
  question: string
  contact_role: string
  reason?: string
}

/** The exact result shape of rarebridge.assessment.assess(). */
export interface Assessment {
  outcome: AssessmentOutcome
  checks: AssessmentCheck[]
  followup_questions: FollowupQuestion[]
  limitations: string
  withdrawn_sources: string[]
  assessment_id?: string
  target_disease?: { id: string; label: string }
  goal?: string
  asset?: Asset
}

export interface ChangedCheck {
  check_id: string
  before: string
  after: string
  remaining_support?: string[]
}

export interface Explanation {
  generation_mode: 'none' | 'live' | 'cached'
  text: string | null
  cited_source_ids: string[]
  model: string | null
}

export interface AssessmentResponse {
  schema_version: string
  before: Assessment
  after: Assessment
  changed_checks: ChangedCheck[]
  sources: SourceMap
  coverage: string
  contacts: Contact[]
  explanation: Explanation
  data_origin: string
  interpretation?: string
  goal_id?: string
  withdrawn_source_ids_applied?: string[]
  withdrawn_source_ids_ignored?: string[]
  source_roles?: Readonly<Record<string, string[]>>
  asset_context?: {
    description?: string
    documented_context?: string
    unverified?: string[]
    owner_status?: string
  }
  review_summary?: { evidence_items?: number; pending?: number; source_checked?: number; note?: string }
}

export interface ExplainResponse {
  schema_version: string
  assessment_id: string
  withdrawn_source_ids: string[]
  explanation: Explanation
  data_origin?: string
}

export interface ResearchHypothesis {
  id: string
  target_disease_id: string
  label: string
  rationale: string
  source_ids: string[]
  basis_edge_ids: string[]
  unresolved_questions: string[]
  proposed_next_step: string
  review_status: 'pending'
  claim_origin: 'inferred'
  basis_kind: 'known_route' | 'proposed_hypothesis'
}

export interface DiscoveryResponse {
  schema_version: string
  discovery: {
    generation_mode: 'live' | 'cached'
    model: string
    provider: string
    response_id: string
    hypotheses: ResearchHypothesis[]
    coverage_note: string
    sources?: SourceMap
    provenance: Readonly<Record<string, unknown>>
  }
}

export interface AskResponse {
  schema_version: string
  assessment_id: string
  withdrawn_source_ids: string[]
  answer: {
    generation_mode: 'live' | 'cached'
    model: string
    provider: string
    response_id: string
    text: string
    cited_source_ids: string[]
    check_ids: string[]
    followup_questions: FollowupQuestion[]
    evidence_state: 'recorded_evidence' | 'insufficient_evidence'
    mode: 'patient' | 'expert'
    provenance: Readonly<Record<string, unknown>>
  }
}

export interface ExtractionPayload {
  source_id: string
  title: string
  url: string
  published_on: string | null
  text: string
}

export interface ExtractionResponse {
  schema_version: string
  import_status: 'not_imported'
  extraction: {
    generation_mode: 'live' | 'cached'
    model: string
    source_id: string
    entities: { id: string; type: string; label: string }[]
    claims: { id: string; subject_id: string; object_id: string; relation: string; source_excerpt: string; review_status: 'pending' }[]
    provenance: Readonly<Record<string, unknown>>
  }
}
