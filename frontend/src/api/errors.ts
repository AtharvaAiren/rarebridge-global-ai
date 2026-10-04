/**
 * One error type for every failed request, whatever the mode.
 *  - network: the live service could not be reached
 *  - http: the service answered with an error envelope
 *  - invalid_response: the answer did not have the contract shape
 *  - demo_missing: demo mode has no saved response for this request
 */
export type ApiErrorKind = 'network' | 'http' | 'invalid_response' | 'demo_missing'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  readonly code: string
  readonly details: readonly unknown[]

  constructor(init: {
    kind: ApiErrorKind
    message: string
    status?: number | null
    code?: string
    details?: readonly unknown[]
  }) {
    super(init.message)
    this.name = 'ApiError'
    this.kind = init.kind
    this.status = init.status ?? null
    this.code = init.code ?? init.kind
    this.details = init.details ?? []
  }

  /**
   * True when the service itself is unavailable, not just this request.
   * An AI capability that is not connected (model_unavailable, ai_*) is not an outage.
   */
  get isServiceFailure(): boolean {
    if (this.kind === 'network') return true
    const isAiCapability = this.code === 'model_unavailable' || this.code.startsWith('ai_')
    return this.kind === 'http' && (this.status ?? 0) >= 500 && !isAiCapability
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  const message = error instanceof Error ? error.message : 'Unexpected error'
  return new ApiError({ kind: 'invalid_response', message })
}

/** Reads {error:{code,message,details}}; null if the body is not that shape. */
export function readErrorEnvelope(body: unknown): { code: string; message: string; details: unknown[] } | null {
  if (!isRecord(body) || !isRecord(body.error)) return null
  const { code, message, details } = body.error
  if (typeof code !== 'string' || typeof message !== 'string') return null
  return { code, message, details: Array.isArray(details) ? details : [] }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}
