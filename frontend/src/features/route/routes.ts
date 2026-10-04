/**
 * Recorded study routes from the overview, plus the contacts it lists.
 * Pure module: tested under Node.
 */
import type { Contact, OverviewResponse, RecordedRoute, RelatedDisease } from '../../api/types.ts'

export interface RouteEntry {
  key: string
  related: RelatedDisease
  route: RecordedRoute
  title: string
}

const ROUTE_TITLES: Readonly<Record<string, string>> = {
  direct_edge: 'Direct navigation link',
  shared_study_framework: 'Through the shared study framework',
}

export function routeTitle(kind: string | undefined): string {
  if (!kind) return 'Recorded route'
  return ROUTE_TITLES[kind] ?? kind.replace(/_/g, ' ')
}

export function recordedRoutes(overview: OverviewResponse): RouteEntry[] {
  return overview.related_diseases.flatMap((related) =>
    (related.recorded_routes ?? []).map((route, index) => ({
      key: `${related.id}#${index}`,
      related,
      route,
      title: routeTitle(route.kind),
    })),
  )
}

/** Related diseases with a recorded route come first; the first one gets the callout. */
export function splitRelated(overview: OverviewResponse): { withRoutes: RelatedDisease[]; candidates: RelatedDisease[] } {
  const withRoutes = overview.related_diseases.filter((r) => (r.recorded_routes ?? []).length > 0)
  const candidates = overview.related_diseases.filter((r) => (r.recorded_routes ?? []).length === 0)
  return { withRoutes, candidates }
}

/** Every contact the overview lists, by ID (disease contacts win over community ones). */
export function contactsById(overview: OverviewResponse): Map<string, Contact> {
  const community = overview.related_diseases.flatMap((r) => r.organizations ?? [])
  return new Map([...community, ...overview.organizations].map((contact) => [contact.id, contact]))
}

const CONTACT_KINDS: Readonly<Record<string, string>> = {
  organization: 'Organization',
  researcher: 'Researcher',
  study_team: 'Study team',
}

export function contactKindLabel(kind: string): string {
  return CONTACT_KINDS[kind] ?? kind.replace(/_/g, ' ')
}

const ASSET_TYPES: Readonly<Record<string, string>> = {
  published_study_framework: 'Published study framework',
  dataset: 'Dataset',
  measurement_method: 'Measurement method',
  registry: 'Registry',
  questionnaire: 'Questionnaire',
  model: 'Model',
}

export function assetTypeLabel(type: string): string {
  if (ASSET_TYPES[type]) return ASSET_TYPES[type]
  const words = type.replace(/_/g, ' ')
  return words ? words[0].toUpperCase() + words.slice(1) : 'Research resource'
}

/** "implementation-access" -> "Implementation access" (check IDs, until the evidence view lists questions). */
export function checkIdLabel(checkId: string): string {
  const words = checkId.replace(/[-_]+/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1) : checkId
}
