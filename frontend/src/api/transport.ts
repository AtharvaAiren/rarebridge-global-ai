/**
 * Two transports with one signature. The client and every component call a
 * Transport; only api/index.ts decides which one is used.
 */
import { ApiError, isAbortError, readErrorEnvelope } from './errors.ts'
import { demoKey, requestUrl, type ApiRequest } from './requests.ts'

export type Transport = (req: ApiRequest, signal?: AbortSignal) => Promise<unknown>

export type FetchLike = (input: string, init: RequestInit) => Promise<Response>

const JSON_HEADERS = { accept: 'application/json' }
const JSON_BODY_HEADERS = { ...JSON_HEADERS, 'content-type': 'application/json' }

export function createLiveTransport(baseUrl: string, fetchImpl: FetchLike): Transport {
  const root = baseUrl.replace(/\/+$/, '')
  return async (req, signal) => {
    const hasBody = req.body !== undefined
    const init: RequestInit = {
      method: req.method,
      headers: hasBody ? JSON_BODY_HEADERS : JSON_HEADERS,
      body: hasBody ? JSON.stringify(req.body) : undefined,
      signal,
    }
    const response = await fetchOrThrow(fetchImpl, `${root}${requestUrl(req)}`, init)
    const body = await readJson(response)
    if (response.ok) return body
    throw httpError(response.status, body)
  }
}

async function fetchOrThrow(fetchImpl: FetchLike, url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetchImpl(url, init)
  } catch (error) {
    if (isAbortError(error)) throw error
    throw new ApiError({ kind: 'network', message: 'Could not reach the RareBridge service.' })
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    if (!response.ok) return null
    throw new ApiError({
      kind: 'invalid_response',
      status: response.status,
      message: 'The service sent a response that is not JSON.',
    })
  }
}

function httpError(status: number, body: unknown): ApiError {
  const envelope = readErrorEnvelope(body)
  return new ApiError({
    kind: 'http',
    status,
    code: envelope?.code ?? `http_${status}`,
    message: envelope?.message ?? `The service answered with HTTP ${status}.`,
    details: envelope?.details ?? [],
  })
}

export interface DemoEntry {
  key: string
  file: string
  status: number
}

export type DemoFileLoader = (file: string) => Promise<unknown>

export const DEMO_MISSING_MESSAGE = 'Not available in demo data'

/**
 * Replays saved responses by request identity. A request with no saved
 * response fails with demo_missing; it never borrows another response.
 */
export function createDemoTransport(entries: readonly DemoEntry[], loadFile: DemoFileLoader): Transport {
  const byKey = new Map(entries.map((entry) => [entry.key, entry]))
  return async (req) => {
    const entry = byKey.get(demoKey(req))
    if (!entry) {
      throw new ApiError({ kind: 'demo_missing', code: 'demo_missing', message: DEMO_MISSING_MESSAGE })
    }
    const body = await loadFile(entry.file)
    if (entry.status >= 200 && entry.status < 300) return body
    throw httpError(entry.status, body)
  }
}
