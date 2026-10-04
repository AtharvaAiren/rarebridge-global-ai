import { useState } from 'react'
import { useApiClient } from '../../api/ApiContext.tsx'
import type { OverviewResponse } from '../../api/types.ts'
import { useHealth } from '../../app/HealthContext.tsx'
import { usePreferences } from '../../app/PreferencesContext.tsx'
import { Icon } from '../../components/Icon.tsx'
import { ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { safeExternalUrl } from '../../domain/urls.ts'
import { useApiResource } from '../../hooks/useApiResource.ts'
import { routeHash } from '../../routing.ts'

export function ResearchLeads({ overview, onExplore, hiddenSourceIds = [] }: { overview: OverviewResponse; onExplore: (id: string) => void; hiddenSourceIds?: readonly string[] }) {
  const client = useApiClient()
  const { isExpert } = usePreferences()
  const health = useHealth().state
  const available = health.status === 'success' && health.data.capabilities.ai_discovery === true
  const contextKey = `${overview.disease.id}:${overview.goal_id}`
  const [requestedKey, setRequestedKey] = useState<string | null>(null)
  const hasHiddenSources = hiddenSourceIds.length > 0
  const requested = requestedKey === contextKey && !hasHiddenSources
  const { state, retry } = useApiResource(requested ? `discovery:${contextKey}` : null, (signal) => client.discover(overview.disease.id, overview.goal_id, signal))

  return (
    <section className="research-leads page-section" aria-labelledby="research-leads-title">
      <div className="research-leads__heading">
        <div>
          <p className="rb-label"><Icon name="split" /> AI research scout</p>
          <h2 id="research-leads-title" className="section-title">What else could we investigate?</h2>
          <p className="research-leads__intro">Ask the trained AI model to connect the meaning of the records and suggest a question worth taking to a research partner.</p>
        </div>
        <button type="button" className="rb-btn rb-btn--primary" disabled={!available || hasHiddenSources || (requested && state.status === 'loading')} onClick={() => requested ? retry() : setRequestedKey(contextKey)}>
          <Icon name="search" /> {requested && state.status === 'success' ? 'Review leads again' : 'Find research leads'}
        </button>
      </div>
      {!available && <p className="rb-meta">Research scouting requires a connected AI service. Your sourced map and assessments remain available.</p>}
      {hasHiddenSources && <p className="rb-meta">The scout reads the full registry source set. Show the hidden sources again to view or request these leads; your assessment assistant can explain the hidden-source view now.</p>}
      <p className="rb-meta">Suggestions are research hypotheses to check. They do not approve a shared treatment or permission to reuse a resource.</p>
      {requested && state.status === 'loading' && <LoadingState label="Reading the source-linked records for possible research leads…" />}
      {requested && state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {requested && state.status === 'success' && (
        <div className="research-leads__results">
          <p className="ai-provenance"><Icon name={state.data.discovery.generation_mode === 'cached' ? 'archive' : 'live'} /> {state.data.discovery.generation_mode === 'cached' ? 'Saved AI-generated research leads' : 'AI-generated research leads'} · {state.data.discovery.model}</p>
          {state.data.discovery.hypotheses.length === 0 && <p>No additional lead was justified by the records available to the model. The recorded routes above are still worth exploring.</p>}
          {state.data.discovery.hypotheses.map((lead) => (
            <article className="research-lead" key={lead.id}>
              <span className="rb-chip"><Icon name="question" /> {lead.basis_kind === 'known_route' ? 'Known route · AI interpretation' : 'Proposed research hypothesis'} · review pending</span>
              <h3>{lead.label}</h3>
              <p>{lead.rationale}</p>
              <details className="research-lead__detail" open={isExpert || undefined}>
                <summary>What would need checking?</summary>
                <ul>{lead.unresolved_questions.map((question, i) => <li key={i}>{question}</li>)}</ul>
                <p><strong>Next step:</strong> {lead.proposed_next_step}</p>
                {isExpert && <p className="rb-meta">Based on {lead.basis_edge_ids.length} recorded graph relationships; the model has not independently verified their claims.</p>}
              </details>
              <div className="research-lead__sources">
                {lead.source_ids.map((id) => {
                  const source = state.data.discovery.sources?.[id]
                  const url = safeExternalUrl(source?.url ?? '')
                  return url ? <a className="rb-link" key={id} href={url} target="_blank" rel="noreferrer"><Icon name="external" /> {source?.title ?? id}</a> : <span className="rb-meta" key={id}>{source?.title ?? id}</span>
                })}
              </div>
              <button type="button" className="rb-btn rb-btn--quiet" onClick={() => onExplore(lead.target_disease_id)}><Icon name="fit" /> Explore this condition on the map</button>
              <a className="rb-btn rb-btn--quiet" href={routeHash({ name: 'disease', diseaseId: lead.target_disease_id, goal: overview.goal_id })}><Icon name="arrowRight" /> Open this condition's resources</a>
            </article>
          ))}
          <details><summary>Sources and search coverage</summary><p className="rb-meta">{state.data.discovery.coverage_note}</p></details>
        </div>
      )}
    </section>
  )
}
