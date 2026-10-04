import { useState } from 'react'
import { useApiClient } from '../../api/ApiContext.tsx'
import { useHealth } from '../../app/HealthContext.tsx'
import { ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { useApiResource } from '../../hooks/useApiResource.ts'
import type { EvidenceState } from './useAssessment.ts'
import { PaperImport, ResearchAssistant } from './ResearchAssistant.tsx'

const GENERATION_LABELS: Readonly<Record<string, string>> = {
  live: 'AI-generated just now',
  cached: 'AI-generated earlier and saved',
}

/**
 * The AI area. The evidence journey never depends on it: when the service
 * reports no AI capability, this says so plainly and nothing is generated.
 */
export function AiExplanation({ evidence }: { evidence: EvidenceState }) {
  const [tab, setTab] = useState<'ask' | 'explain' | 'extract'>('ask')
  const { state } = useHealth()
  const health = state.status === 'success' ? state.data : null
  const isExplainable = health?.capabilities.ai_explanation === true
  const hasAssistant = health?.capabilities.ai_assistant === true
  const hasExtraction = health?.capabilities.ai_extraction === true

  return (
    <section className="ai-area" aria-labelledby="ai-area-title">
      <h4 id="ai-area-title" className="ai-area__title">
        Your research assistant
      </h4>
      {isExplainable || hasAssistant || hasExtraction ? (
        <>
          <div className="ai-assistant__tabs" aria-label="Research assistant tools">
            <button type="button" className="rb-btn rb-btn--quiet" aria-pressed={tab === 'ask'} onClick={() => setTab('ask')} disabled={!hasAssistant}>Ask a question</button>
            <button type="button" className="rb-btn rb-btn--quiet" aria-pressed={tab === 'explain'} onClick={() => setTab('explain')} disabled={!isExplainable}>Explain this view</button>
            <button type="button" className="rb-btn rb-btn--quiet" aria-pressed={tab === 'extract'} onClick={() => setTab('extract')} disabled={!hasExtraction}>Add a paper</button>
          </div>
          {tab === 'ask' && (health?.capabilities.ai_assistant ? <ResearchAssistant evidence={evidence} /> : <p className="rb-meta">Questions will be available when the assistant service is connected. You can explain the current view now.</p>)}
          {tab === 'explain' && isExplainable && <LiveExplanation evidence={evidence} />}
          {tab === 'extract' && hasExtraction && <PaperImport />}
        </>
      ) : (
        <>
          <p className="ai-area__status">AI explanation not connected yet.</p>
          {health?.ai_status_note && <p className="inspector__note">Service note: {health.ai_status_note}</p>}
          <p className="inspector__note">Everything in this panel comes from recorded sources, not from AI.</p>
        </>
      )}
    </section>
  )
}

/** Explains exactly the current view; hiding or showing a source invalidates it. */
function LiveExplanation({ evidence }: { evidence: EvidenceState }) {
  const client = useApiClient()
  const viewKey = `${evidence.assessmentId}:${evidence.hidden.join('|')}`
  const [requestedKey, setRequestedKey] = useState<string | null>(null)
  const isRequested = requestedKey === viewKey
  const { state, retry } = useApiResource(isRequested ? `explain:${viewKey}` : null, (signal) =>
    client.explain(evidence.assessmentId, evidence.hidden, signal),
  )

  if (!isRequested) {
    return (
      <>
        <p className="inspector__note">
          An AI summary of the checks in this view, citing only its sources. Read it alongside the checks, not instead.
        </p>
        <button
          type="button"
          className="rb-btn rb-btn--quiet"
          disabled={!evidence.current}
          onClick={() => setRequestedKey(viewKey)}
        >
          Explain this view
        </button>
      </>
    )
  }
  if (state.status === 'loading' || state.status === 'idle') return <LoadingState label="Asking for an explanation…" />
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={retry} />

  const explanation = state.data.explanation
  const sources = evidence.current?.sources ?? {}
  return (
    <div className="ai-area__result">
      <p className="ai-area__mode">
        {GENERATION_LABELS[explanation.generation_mode] ?? 'Not AI-generated'}
        {explanation.model && ` · ${explanation.model}`}
      </p>
      <p>{explanation.text ?? 'The service returned no explanation text.'}</p>
      {explanation.cited_source_ids.length > 0 && (
        <p className="inspector__note">
          Cites: {explanation.cited_source_ids.map((id) => sources[id]?.title ?? id).join('; ')}
        </p>
      )}
    </div>
  )
}
