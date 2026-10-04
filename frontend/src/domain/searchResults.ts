import type { SearchItem } from '../api/types.ts'

const TYPE_LABELS: Readonly<Record<string, string>> = {
  disease: 'Disease',
  gene: 'Gene',
  phenotype: 'Symptom or feature',
  claim: 'Mechanism claim',
  organization: 'Organization',
  study: 'Study',
  study_team: 'Study team',
  researcher: 'Researcher',
  asset: 'Research resource',
  publication: 'Publication',
  source: 'Source',
}

export function searchTypeLabel(type: string): string {
  const known = TYPE_LABELS[type]
  if (known) return known
  const words = type.replace(/[_-]+/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1) : 'Other'
}

/** Diseases first (search enters the disease journey), otherwise API order. */
export function orderSearchItems(items: readonly SearchItem[]): SearchItem[] {
  const diseases = items.filter((item) => item.type === 'disease')
  const others = items.filter((item) => item.type !== 'disease')
  return [...diseases, ...others]
}

export type SearchItemAction =
  | { kind: 'open'; diseaseId: string }
  | { kind: 'choose'; diseaseIds: readonly string[] }
  | { kind: 'none' }

/**
 * A disease opens itself. Anything else opens its disease when it has
 * exactly one, asks her to pick when it has several, and does nothing
 * when the collection links it to no disease.
 */
export function searchItemAction(item: SearchItem): SearchItemAction {
  if (item.type === 'disease') return { kind: 'open', diseaseId: item.id }
  const ids = [...new Set(item.disease_ids)]
  if (ids.length === 1) return { kind: 'open', diseaseId: ids[0] }
  if (ids.length > 1) return { kind: 'choose', diseaseIds: ids }
  return { kind: 'none' }
}
