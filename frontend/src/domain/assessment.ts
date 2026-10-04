/**
 * Helpers for the evidence view and the "hide a source" overlay.
 * Check statuses always come from the API response; these helpers only
 * look things up and describe the current view. Pure module.
 */
import type { AssessmentCheck, ChangedCheck, SourceMap } from '../api/types.ts'

/** Canonical, de-duplicated and sorted, so equal lists make equal requests. */
export function normalizeIds(ids: readonly string[]): string[] {
  return [...new Set(ids)].sort()
}

export function withId(ids: readonly string[], id: string): string[] {
  return normalizeIds([...ids, id])
}

export function withoutId(ids: readonly string[], id: string): string[] {
  return ids.filter((existing) => existing !== id)
}

/** DOI and PMID aliases name one paper. A different version is not an alias. */
export function canonicalId(sources: SourceMap, id: string): string {
  if (sources[id]) return id
  const match = Object.entries(sources).find(([, source]) => source.aliases.includes(id))
  return match ? match[0] : id
}

const POLARITY: Readonly<Record<string, string>> = {
  support: 'Supports this check',
  refute: 'Argues against this check',
  conflict: 'Conflicts with other sources',
  uncertain: 'Leaves this check uncertain',
}

export function polarityLabel(polarity: string): string {
  return POLARITY[polarity] ?? polarity.replace(/_/g, ' ')
}

export function changesByCheck(changed: readonly ChangedCheck[]): Map<string, ChangedCheck> {
  return new Map(changed.map((change) => [change.check_id, change]))
}

export function splitChecks(checks: readonly AssessmentCheck[]): { required: AssessmentCheck[]; optional: AssessmentCheck[] } {
  return { required: checks.filter((c) => c.required), optional: checks.filter((c) => !c.required) }
}

export interface OverlayEdge {
  id: string
  source_ids: readonly string[]
}

export interface SourceOverlay {
  /** Some, but not all, of the edge's sources are hidden in this view. */
  partly: Set<string>
  /** Every source of the edge is hidden in this view. */
  fully: Set<string>
}

/**
 * Which relationships cite a hidden source. This labels the current view;
 * it does not re-judge the relationship or change its recorded review.
 */
export function sourceOverlay(
  edges: readonly OverlayEdge[],
  hidden: readonly string[],
  canonical: (id: string) => string,
): SourceOverlay {
  const hiddenSet = new Set(hidden)
  const partly = new Set<string>()
  const fully = new Set<string>()
  if (hiddenSet.size === 0) return { partly, fully }
  for (const edge of edges) {
    const ids = [...new Set(edge.source_ids.map(canonical))]
    const hiddenCount = ids.filter((id) => hiddenSet.has(id)).length
    if (hiddenCount === 0) continue
    if (hiddenCount === ids.length) fully.add(edge.id)
    else partly.add(edge.id)
  }
  return { partly, fully }
}

/** Unique source IDs cited by any check, in check order. */
export function citedSourceIds(checks: readonly AssessmentCheck[]): string[] {
  const ids = checks.flatMap((c) => [...c.active_evidence, ...c.withdrawn_evidence].map((e) => e.source_id))
  return [...new Set(ids)]
}
