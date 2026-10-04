/**
 * Hash routes. Pure functions (tested under Node); the hook lives in
 * hooks/useRoute.ts.
 *   #/                                               home
 *   #/search?q=syngap1                               search results
 *   #/disease/MONDO%3A0012960?goal=natural_history   research-route view
 *   ...&evidence=framework-for-syngap1                with the evidence view open
 *   ...&evidence=...&brief=1                          with the collaboration brief open
 */
import { NATURAL_HISTORY_GOAL } from './api/requests.ts'

export type Route =
  | { name: 'home' }
  | { name: 'search'; query: string }
  | { name: 'disease'; diseaseId: string; goal: string; evidenceId?: string; isBriefOpen?: boolean }

const HOME: Route = { name: 'home' }

export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#/, '')
  const [pathPart, queryPart = ''] = raw.split('?', 2)
  const segments = pathPart.split('/').filter(Boolean)
  const params = new URLSearchParams(queryPart)

  if (segments[0] === 'search') {
    const query = (params.get('q') ?? '').trim()
    return query ? { name: 'search', query } : HOME
  }
  if (segments[0] === 'disease' && segments.length === 2) {
    const diseaseId = safeDecode(segments[1])
    if (!diseaseId) return HOME
    const evidenceId = params.get('evidence')?.trim()
    const goal = params.get('goal') || NATURAL_HISTORY_GOAL
    if (!evidenceId) return { name: 'disease', diseaseId, goal }
    // The brief is built from an open assessment, so it needs one.
    return params.get('brief') === '1'
      ? { name: 'disease', diseaseId, goal, evidenceId, isBriefOpen: true }
      : { name: 'disease', diseaseId, goal, evidenceId }
  }
  return HOME
}

export function routeHash(route: Route): string {
  switch (route.name) {
    case 'home':
      return '#/'
    case 'search':
      return `#/search?${new URLSearchParams({ q: route.query }).toString()}`
    case 'disease': {
      const params = new URLSearchParams({ goal: route.goal })
      if (route.evidenceId) params.set('evidence', route.evidenceId)
      if (route.evidenceId && route.isBriefOpen) params.set('brief', '1')
      return `#/disease/${encodeURIComponent(route.diseaseId)}?${params.toString()}`
    }
  }
}

/** Identity of the page, ignoring in-page state such as an open evidence view. */
export function pageKey(route: Route): string {
  return routeHash(route.name === 'disease' ? { ...route, evidenceId: undefined, isBriefOpen: undefined } : route)
}

function safeDecode(segment: string): string | null {
  try {
    return decodeURIComponent(segment)
  } catch {
    return null
  }
}
