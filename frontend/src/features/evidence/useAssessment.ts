import { useState } from 'react'
import { useApiClient } from '../../api/ApiContext.tsx'
import type { ApiError } from '../../api/errors.ts'
import type { AssessmentResponse } from '../../api/types.ts'
import { normalizeIds, withId, withoutId } from '../../domain/assessment.ts'
import { useApiResource } from '../../hooks/useApiResource.ts'

/** A response together with the exact request that produced it. */
interface Evaluated {
  assessmentId: string
  hiddenKey: string
  data: AssessmentResponse
}

/** The evidence view as the page sees it: state plus open/close (URL) actions. */
export interface EvidenceControls {
  state: EvidenceState | null
  open: (assessmentId: string) => void
  close: () => void
  /** Opens the collaboration brief for the open assessment. */
  openBrief: () => void
}

export interface EvidenceState {
  assessmentId: string
  /** Canonical source IDs hidden in this view (what was asked for). */
  hidden: readonly string[]
  /** The response for exactly `hidden`, or null while loading or failed. */
  current: AssessmentResponse | null
  /** An older response for this assessment, shown dimmed while the current one loads. */
  previous: AssessmentResponse | null
  isLoading: boolean
  error: ApiError | null
  retry: () => void
  hide: (sourceId: string) => void
  show: (sourceId: string) => void
  reset: () => void
}

/**
 * The single current assessment for a route. Hiding a source re-evaluates
 * with the full hidden list; reset sends an empty list. A response is only
 * "current" when it answers exactly the current list.
 */
export function useAssessment(assessmentId: string | undefined): EvidenceState | null {
  const client = useApiClient()
  const [hiddenFor, setHiddenFor] = useState<{ id: string | undefined; hidden: string[] }>({ id: undefined, hidden: [] })
  const hidden = hiddenFor.id === assessmentId ? hiddenFor.hidden : []
  const hiddenKey = hidden.join('|')

  const resource = useApiResource<Evaluated>(
    assessmentId ? `assess:${assessmentId}:${hiddenKey}` : null,
    async (signal) => {
      const id = assessmentId ?? ''
      const data = await client.evaluate(id, hidden, signal)
      return { assessmentId: id, hiddenKey, data }
    },
  )

  if (!assessmentId) return null
  const latest = resource.lastData?.assessmentId === assessmentId ? resource.lastData : null
  const isCurrent = resource.state.status === 'success' && latest?.hiddenKey === hiddenKey
  const isLoading = resource.state.status === 'loading'
  const update = (next: string[]) => setHiddenFor({ id: assessmentId, hidden: normalizeIds(next) })

  return {
    assessmentId,
    hidden,
    current: isCurrent ? (latest?.data ?? null) : null,
    previous: isLoading && latest ? latest.data : null,
    isLoading,
    error: resource.state.status === 'error' ? resource.state.error : null,
    retry: resource.retry,
    hide: (sourceId) => update(withId(hidden, sourceId)),
    show: (sourceId) => update(withoutId(hidden, sourceId)),
    reset: () => update([]),
  }
}
