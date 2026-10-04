/**
 * Exact state labels from FRONTEND_SPEC.txt and the user's chip mapping.
 * Every status renders icon + text; colour only reinforces. Nothing here
 * says approved, safe or validated, and unknown is never failure-coloured.
 */
import type { IconName } from '../components/Icon.tsx'

export type ChipTone = 'supported' | 'unknown' | 'weaker' | 'contradicted' | 'candidate' | 'neutral'

export interface StatusSpec {
  label: string
  tone: ChipTone
  icon: IconName
}

const STATES: Readonly<Record<string, StatusSpec>> = {
  supported: { label: 'Source supports this check', tone: 'supported', icon: 'check' },
  unknown: { label: 'Information missing', tone: 'unknown', icon: 'question' },
  needs_source_review: { label: 'Source check pending', tone: 'weaker', icon: 'clock' },
  conflicting: { label: 'Sources disagree', tone: 'weaker', icon: 'split' },
  refuted: { label: 'Source argues against this proposed use', tone: 'contradicted', icon: 'x' },
  candidate_for_expert_review: { label: 'Ready for expert review', tone: 'candidate', icon: 'flag' },
  needs_information: { label: 'Questions still open', tone: 'unknown', icon: 'list' },
  needs_expert_review: { label: 'Expert review needed', tone: 'unknown', icon: 'person' },
  not_supported_for_stated_use: { label: 'This proposed use lacks support', tone: 'contradicted', icon: 'slash' },
}

/** Check states and assessment outcomes share one vocabulary. */
export function statusSpec(state: string): StatusSpec {
  return STATES[state] ?? { label: `Status: ${state.replace(/_/g, ' ')}`, tone: 'unknown', icon: 'question' }
}

const REVIEW: Readonly<Record<string, StatusSpec>> = {
  pending: { label: 'Source check pending', tone: 'weaker', icon: 'clock' },
  source_checked: { label: 'Fact checked against source', tone: 'neutral', icon: 'check' },
}

const NO_REVIEW: StatusSpec = { label: 'No review status recorded', tone: 'unknown', icon: 'question' }

/** Evidence review badge. "Fact checked" is a narrow source audit, not approval. */
export function reviewSpec(reviewStatus: string | undefined): StatusSpec {
  if (!reviewStatus) return NO_REVIEW
  return REVIEW[reviewStatus] ?? { label: `Review: ${reviewStatus.replace(/_/g, ' ')}`, tone: 'unknown', icon: 'question' }
}

const ORIGINS: Readonly<Record<string, string>> = {
  imported: 'Imported from the DisMech record',
  recorded: 'Recorded in the curated collection',
  inferred: 'Inferred for navigation',
}

export function originLabel(origin: string | undefined): string {
  if (!origin) return 'Origin not recorded'
  return ORIGINS[origin] ?? origin.replace(/_/g, ' ')
}
