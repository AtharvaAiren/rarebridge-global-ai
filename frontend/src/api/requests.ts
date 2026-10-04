/**
 * Request descriptors shared by the live client, the demo lookup and
 * scripts/capture-fixtures.mjs, so all three agree on what a request is.
 * Pure module: no Vite or DOM APIs (it also runs under plain Node).
 */

export type HttpMethod = 'GET' | 'POST'

export interface ApiRequest {
  readonly method: HttpMethod
  readonly path: string
  readonly query?: Readonly<Record<string, string>>
  readonly body?: unknown
}

export const NATURAL_HISTORY_GOAL = 'natural_history'
export const SEARCH_LIMIT = 10
/** Graph budget per the atlas brief: the 40-node response, then an optional 80. */
export const GRAPH_NODES_DEFAULT = 40
export const GRAPH_NODES_MORE = 80

const enc = encodeURIComponent

export function healthRequest(): ApiRequest {
  return { method: 'GET', path: '/api/health' }
}

export function searchRequest(q: string, limit: number = SEARCH_LIMIT): ApiRequest {
  return { method: 'GET', path: '/api/search', query: { q: q.trim(), limit: String(limit) } }
}

export function overviewRequest(diseaseId: string, goal: string = NATURAL_HISTORY_GOAL): ApiRequest {
  return { method: 'GET', path: `/api/diseases/${enc(diseaseId)}/overview`, query: { goal } }
}

export function evaluateRequest(assessmentId: string, withdrawnSourceIds: readonly string[]): ApiRequest {
  return {
    method: 'POST',
    path: '/api/assessments/evaluate',
    body: { assessment_id: assessmentId, withdrawn_source_ids: [...withdrawnSourceIds] },
  }
}

export function graphRequest(params: {
  diseaseId: string
  assessmentId?: string
  maxNodes?: number
}): ApiRequest {
  const query: Record<string, string> = {
    disease_id: params.diseaseId,
    max_nodes: String(params.maxNodes ?? GRAPH_NODES_DEFAULT),
  }
  const withAssessment = params.assessmentId ? { ...query, assessment_id: params.assessmentId } : query
  return { method: 'GET', path: '/api/graph', query: withAssessment }
}

export function sourceRequest(sourceId: string): ApiRequest {
  return { method: 'GET', path: `/api/sources/${enc(sourceId)}` }
}

export function explainRequest(assessmentId: string, withdrawnSourceIds: readonly string[]): ApiRequest {
  return {
    method: 'POST',
    path: '/api/ai/explain',
    body: { assessment_id: assessmentId, withdrawn_source_ids: [...withdrawnSourceIds] },
  }
}

export function discoverRequest(diseaseId: string, goalId: string): ApiRequest {
  return { method: 'POST', path: '/api/ai/discover', body: { disease_id: diseaseId, goal_id: goalId } }
}

export function askRequest(assessmentId: string, withdrawnSourceIds: readonly string[], question: string, mode: 'patient' | 'expert'): ApiRequest {
  return { method: 'POST', path: '/api/ai/ask', body: { assessment_id: assessmentId, withdrawn_source_ids: [...withdrawnSourceIds], question: question.trim(), mode } }
}

export function extractRequest(payload: import('./types.ts').ExtractionPayload): ApiRequest {
  return { method: 'POST', path: '/api/ai/extract', body: payload }
}

/** Path plus query string, with keys sorted so equal requests give equal URLs. */
export function requestUrl(req: ApiRequest): string {
  const entries = Object.entries(req.query ?? {}).sort(([a], [b]) => a.localeCompare(b))
  if (entries.length === 0) return req.path
  return `${req.path}?${new URLSearchParams(entries).toString()}`
}

/**
 * Stable identity of a request, used to look up saved demo responses.
 * Search text is case-insensitive (as in the live API) and withdrawal lists
 * are order-insensitive, so both are normalised.
 */
export function demoKey(req: ApiRequest): string {
  const query = req.query?.q !== undefined ? { ...req.query, q: req.query.q.toLowerCase() } : req.query
  const url = requestUrl({ ...req, query })
  if (req.body === undefined) return `${req.method} ${url}`
  return `${req.method} ${url} ${stableJson(req.body)}`
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) {
    const items = value.map(stableJson)
    return `[${items.every((s) => s.startsWith('"')) ? [...items].sort().join(',') : items.join(',')}]`
  }
  if (value !== null && typeof value === 'object') {
    const keys = Object.keys(value).sort()
    const record = value as Record<string, unknown>
    return `{${keys.map((k) => `${JSON.stringify(k)}:${stableJson(record[k])}`).join(',')}}`
  }
  return JSON.stringify(value)
}
