import { useEffect, useRef, useState } from 'react'
import { isAbortError, toApiError, type ApiError } from '../api/errors.ts'

export type ResourceState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: ApiError }

export interface Resource<T> {
  state: ResourceState<T>
  /** The most recent successful data for any key (kept while a new key loads or fails). */
  lastData: T | null
  retry: () => void
}

type Settled<T> = { key: string; attempt: number; state: ResourceState<T> }

/**
 * Loads data for a request key. A new key or a retry starts a new request;
 * the previous one is aborted so a late answer cannot overwrite a newer one.
 * A null key means "nothing to load".
 */
export function useApiResource<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>): Resource<T> {
  const loadRef = useRef(load)
  const [attempt, setAttempt] = useState(0)
  const [settled, setSettled] = useState<Settled<T> | null>(null)
  const [lastData, setLastData] = useState<T | null>(null)

  useEffect(() => {
    loadRef.current = load
  })

  useEffect(() => {
    if (key === null) return
    const controller = new AbortController()
    const settle = (state: ResourceState<T>) => {
      if (!controller.signal.aborted) setSettled({ key, attempt, state })
    }
    loadRef.current(controller.signal).then(
      (data) => {
        if (controller.signal.aborted) return
        setLastData(data)
        settle({ status: 'success', data })
      },
      (error: unknown) => {
        if (!isAbortError(error)) settle({ status: 'error', error: toApiError(error) })
      },
    )
    return () => controller.abort()
  }, [key, attempt])

  const isCurrent = settled !== null && settled.key === key && settled.attempt === attempt
  const state: ResourceState<T> = key === null ? { status: 'idle' } : isCurrent ? settled.state : { status: 'loading' }

  return { state, lastData, retry: () => setAttempt((n) => n + 1) }
}
