/**
 * The typed RareBridge client. It checks the minimum contract shape at the
 * boundary and reports service health to subscribers (the mode banner).
 */
import { ApiError, isAbortError, isRecord, toApiError } from './errors.ts'
import {
  evaluateRequest,
  askRequest,
  discoverRequest,
  extractRequest,
  explainRequest,
  graphRequest,
  healthRequest,
  overviewRequest,
  searchRequest,
  type ApiRequest,
} from './requests.ts'
import type { Transport } from './transport.ts'
import type {
  AssessmentResponse,
  AskResponse,
  DiscoveryResponse,
  ExtractionPayload,
  ExtractionResponse,
  ExplainResponse,
  GraphResponse,
  HealthResponse,
  OverviewResponse,
  SearchResponse,
} from './types.ts'

export interface GraphQuery {
  diseaseId: string
  assessmentId?: string
  maxNodes: number
}

export type DataMode = 'live' | 'demo'

/** 'ok' until a call fails because the service itself is unavailable. */
export type ServiceStatus = 'ok' | 'unreachable'

export interface ApiClient {
  readonly mode: DataMode
  health(signal?: AbortSignal): Promise<HealthResponse>
  search(q: string, signal?: AbortSignal): Promise<SearchResponse>
  overview(diseaseId: string, goal: string, signal?: AbortSignal): Promise<OverviewResponse>
  graph(query: GraphQuery, signal?: AbortSignal): Promise<GraphResponse>
  evaluate(assessmentId: string, withdrawnSourceIds: readonly string[], signal?: AbortSignal): Promise<AssessmentResponse>
  explain(assessmentId: string, withdrawnSourceIds: readonly string[], signal?: AbortSignal): Promise<ExplainResponse>
  discover(diseaseId: string, goalId: string, signal?: AbortSignal): Promise<DiscoveryResponse>
  ask(assessmentId: string, withdrawnSourceIds: readonly string[], question: string, mode: 'patient' | 'expert', signal?: AbortSignal): Promise<AskResponse>
  extract(payload: ExtractionPayload, signal?: AbortSignal): Promise<ExtractionResponse>
  getServiceStatus(): ServiceStatus
  subscribeServiceStatus(listener: () => void): () => void
}

export function createApiClient(mode: DataMode, transport: Transport): ApiClient {
  let status: ServiceStatus = 'ok'
  const listeners = new Set<() => void>()

  const setStatus = (next: ServiceStatus) => {
    if (next === status) return
    status = next
    listeners.forEach((listener) => listener())
  }

  async function call<T>(req: ApiRequest, requiredKeys: readonly string[], signal?: AbortSignal): Promise<T> {
    try {
      const body = await transport(req, signal)
      assertShape(body, requiredKeys)
      setStatus('ok')
      return body as T
    } catch (error) {
      if (isAbortError(error)) throw error
      const apiError = toApiError(error)
      if (apiError.isServiceFailure) setStatus('unreachable')
      throw apiError
    }
  }

  return {
    mode,
    health: (signal) => call(healthRequest(), ['status', 'capabilities'], signal),
    search: (q, signal) => call(searchRequest(q), ['items', 'coverage'], signal),
    overview: (diseaseId, goal, signal) =>
      call(overviewRequest(diseaseId, goal), ['disease', 'related_diseases', 'opportunities', 'coverage'], signal),
    graph: (query, signal) => call(graphRequest(query), ['nodes', 'edges', 'sources', 'coverage'], signal),
    evaluate: (assessmentId, withdrawnSourceIds, signal) =>
      call(evaluateRequest(assessmentId, withdrawnSourceIds), ['before', 'after', 'changed_checks', 'sources'], signal),
    explain: (assessmentId, withdrawnSourceIds, signal) =>
      call(explainRequest(assessmentId, withdrawnSourceIds), ['explanation'], signal),
    discover: (diseaseId, goalId, signal) => call(discoverRequest(diseaseId, goalId), ['discovery'], signal),
    ask: (assessmentId, withdrawnSourceIds, question, mode, signal) =>
      call(askRequest(assessmentId, withdrawnSourceIds, question, mode), ['answer', 'assessment_id'], signal),
    extract: (payload, signal) => call(extractRequest(payload), ['extraction', 'import_status'], signal),
    getServiceStatus: () => status,
    subscribeServiceStatus: (listener) => {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
  }
}

function assertShape(body: unknown, requiredKeys: readonly string[]): void {
  const missing = isRecord(body) ? requiredKeys.filter((key) => !(key in body)) : [...requiredKeys]
  if (missing.length === 0) return
  throw new ApiError({
    kind: 'invalid_response',
    message: `The response is missing expected fields: ${missing.join(', ')}.`,
  })
}
