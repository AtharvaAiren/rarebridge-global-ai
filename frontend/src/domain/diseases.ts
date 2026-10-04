/**
 * The three diseases of the demonstration collection. These IDs (and the
 * goal natural_history) are the only IDs the frontend may hardcode.
 * Full names always come from the API; these short names are for display.
 */
export interface DemoDisease {
  id: string
  shortName: string
}

export const DEMO_DISEASES: readonly DemoDisease[] = [
  { id: 'MONDO:0012960', shortName: 'SYNGAP1-related disorder' },
  { id: 'MONDO:0012812', shortName: 'STXBP1-related disorder' },
  { id: 'MONDO:0013388', shortName: 'SCN2A-related disorder' },
]

export function shortDiseaseName(diseaseId: string): string | undefined {
  return DEMO_DISEASES.find((disease) => disease.id === diseaseId)?.shortName
}

/** Short name when known; otherwise the label or ID supplied by the API. */
export function diseaseDisplayName(diseaseId: string, fallback?: string): string {
  return shortDiseaseName(diseaseId) ?? fallback ?? diseaseId
}
