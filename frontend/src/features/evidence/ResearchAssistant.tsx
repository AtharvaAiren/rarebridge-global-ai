import { useState, type FormEvent } from 'react'
import { useApiClient } from '../../api/ApiContext.tsx'
import type { ExtractionPayload } from '../../api/types.ts'
import { usePreferences } from '../../app/PreferencesContext.tsx'
import { Icon } from '../../components/Icon.tsx'
import { ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { safeExternalUrl } from '../../domain/urls.ts'
import { useApiResource } from '../../hooks/useApiResource.ts'
import type { EvidenceState } from './useAssessment.ts'

const PROMPTS = ['What does this mean for our patient group?', 'What should we ask a researcher next?', 'What changes if a paper is hidden?']

export function ResearchAssistant({ evidence }: { evidence: EvidenceState }) {
  const client = useApiClient()
  const { isExpert } = usePreferences()
  const mode = isExpert ? 'expert' : 'patient'
  const viewKey = `${evidence.assessmentId}:${evidence.hidden.join('|')}:${mode}`
  const [question, setQuestion] = useState('')
  const [request, setRequest] = useState<{ key: string; question: string } | null>(null)
  const currentRequest = request?.key === viewKey ? request : null
  const { state, retry } = useApiResource(currentRequest && evidence.current ? `ask:${viewKey}:${currentRequest.question}` : null,
    (signal) => client.ask(evidence.assessmentId, evidence.hidden, currentRequest?.question ?? '', mode, signal))
  function submit(event: FormEvent) {
    event.preventDefault()
    if (question.trim() && evidence.current) setRequest({ key: viewKey, question: question.trim() })
  }
  return (
    <div>
      <p className="inspector__note">Ask about this resource, its evidence or the next research step. Answers use the current sources and checks.</p>
      <div className="ai-assistant__prompts">
        {PROMPTS.map((prompt) => <button key={prompt} type="button" className="rb-btn rb-btn--quiet" onClick={() => setQuestion(prompt)}>{prompt}</button>)}
      </div>
      <form className="ai-assistant__form" onSubmit={submit}>
        <label htmlFor="research-question">Your question<textarea id="research-question" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000} placeholder="For example: what is a natural-history study?" required /></label>
        <button type="submit" className="rb-btn rb-btn--primary" disabled={!evidence.current || !question.trim() || state.status === 'loading'}><Icon name="question" /> Ask the research assistant</button>
      </form>
      {currentRequest && state.status === 'loading' && <LoadingState label="Preparing a source-grounded answer…" />}
      {currentRequest && state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {currentRequest && evidence.current && state.status === 'success' && (
        <section className="ai-assistant__answer" aria-live="polite">
          <p className="ai-provenance"><Icon name={state.data.answer.generation_mode === 'cached' ? 'archive' : 'live'} /> {state.data.answer.generation_mode === 'cached' ? 'Saved AI answer for this view' : 'AI answer for this view'} · {state.data.answer.model}</p>
          {state.data.answer.evidence_state === 'insufficient_evidence' && <span className="rb-chip"><Icon name="question" /> The records leave this unanswered</span>}
          <p>{state.data.answer.text}</p>
          {state.data.answer.cited_source_ids.length > 0 && <ul aria-label="Sources for this answer">{state.data.answer.cited_source_ids.map((id) => {
            const source = evidence.current?.sources[id]
            const url = safeExternalUrl(source?.url ?? '')
            return <li key={id}>{url ? <a className="rb-link" href={url} target="_blank" rel="noreferrer"><Icon name="external" /> {source?.title ?? id}</a> : source?.title ?? id}</li>
          })}</ul>}
          {state.data.answer.followup_questions.length > 0 && <details><summary>Questions for a research partner</summary><ul>{state.data.answer.followup_questions.map((q, i) => <li key={i}>{q.question} <span className="rb-meta">Ask a {q.contact_role}</span></li>)}</ul></details>}
          <p className="rb-meta">Research guidance from the recorded evidence. Clinical decisions need your care team.</p>
        </section>
      )}
      {request && !currentRequest && <p className="rb-meta">The evidence view changed. Ask again to get an answer using the current sources.</p>}
    </div>
  )
}

export function PaperImport() {
  const client = useApiClient()
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [request, setRequest] = useState<ExtractionPayload | null>(null)
  const { state, retry } = useApiResource(request ? `extract:${JSON.stringify(request)}` : null, (signal) => client.extract(request!, signal))
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (url.trim() && title.trim() && text.trim()) setRequest({ source_id: `WEB:${url.trim()}`, title: title.trim(), url: url.trim(), published_on: null, text: text.trim() })
  }
  return (
    <div>
      <p className="inspector__note">Paste a public abstract or a short excerpt. AI will suggest source-linked claims for human review; it does not automatically add them to the atlas.</p>
      <form className="ai-assistant__form" onSubmit={submit}>
        <label htmlFor="paper-title">Source title<input id="paper-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} required /></label>
        <label htmlFor="paper-url">Public source URL<input id="paper-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} maxLength={1000} placeholder="https://…" required /></label>
        <label htmlFor="paper-excerpt">Abstract or excerpt<textarea id="paper-excerpt" value={text} onChange={(e) => setText(e.target.value)} maxLength={12000} required /></label>
        <p className="rb-meta">Use public research text. Do not enter personal medical records.</p>
        <button type="submit" className="rb-btn rb-btn--primary" disabled={state.status === 'loading'}><Icon name="split" /> Preview candidate claims</button>
      </form>
      {state.status === 'loading' && <LoadingState label="Extracting candidate claims from your excerpt…" />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'success' && <section className="ai-assistant__answer">
        <p className="ai-provenance">{state.data.extraction.generation_mode === 'cached' ? 'Saved AI extraction' : 'AI extraction'} · {state.data.extraction.model}</p>
        <p><strong>{state.data.extraction.claims.length} candidate claims · review pending</strong></p>
        <p className="rb-meta">Preview only. The reviewed graph is unchanged.</p>
        {state.data.extraction.claims.length === 0 && <p>No source-supported relationship was extracted from this excerpt.</p>}
        {state.data.extraction.claims.map((claim) => <div className="ai-import__claim" key={claim.id}>
          <p>{state.data.extraction.entities.find((e) => e.id === claim.subject_id)?.label ?? claim.subject_id} — {claim.relation.replaceAll('_', ' ')} — {state.data.extraction.entities.find((e) => e.id === claim.object_id)?.label ?? claim.object_id}</p>
          <blockquote>{claim.source_excerpt}</blockquote>
          <span className="rb-chip"><Icon name="clock" /> Source check pending</span>
        </div>)}
      </section>}
    </div>
  )
}
