import type { SearchItem, SearchResponse } from '../../api/types.ts'
import { usePreferences } from '../../app/PreferencesContext.tsx'
import { Icon } from '../../components/Icon.tsx'
import { ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { diseaseDisplayName, shortDiseaseName } from '../../domain/diseases.ts'
import { orderSearchItems, searchItemAction, searchTypeLabel } from '../../domain/searchResults.ts'
import type { Resource } from '../../hooks/useApiResource.ts'
import { routeHash } from '../../routing.ts'

type SearchResultsProps = {
  query: string
  resource: Resource<SearchResponse>
  goalId: string
}

export function SearchResults({ query, resource, goalId }: SearchResultsProps) {
  const { state, retry } = resource
  return (
    <section className="page-section results" aria-labelledby="results-title">
      <h2 id="results-title" className="section-title">
        Results for “{query}”
      </h2>
      {state.status === 'loading' && <LoadingState label="Searching the collection…" />}
      {state.status === 'error' && <ErrorState error={state.error} onRetry={retry} />}
      {state.status === 'success' && <ResultsBody query={query} data={state.data} goalId={goalId} />}
    </section>
  )
}

type ResultsBodyProps = {
  query: string
  data: SearchResponse
  goalId: string
}

function ResultsBody({ query, data, goalId }: ResultsBodyProps) {
  const items = orderSearchItems(data.items)
  if (items.length === 0) return <EmptyResults query={query} scopeNote={data.coverage.scope_note} />

  const total = data.total_matches ?? items.length
  const countText = total > items.length ? `Showing ${items.length} of ${total} matches` : `${items.length} matches`

  return (
    <>
      <p className="results__count" role="status">
        {countText}
      </p>
      <ul className="row-list">
        {items.map((item) => (
          <ResultRow key={`${item.type}:${item.id}`} item={item} goalId={goalId} />
        ))}
      </ul>
      <p className="results__scope rb-meta">{data.coverage.scope_note}</p>
    </>
  )
}

type ResultRowProps = {
  item: SearchItem
  goalId: string
}

function ResultRow({ item, goalId }: ResultRowProps) {
  const { isExpert } = usePreferences()
  const action = searchItemAction(item)
  const diseaseHref = (diseaseId: string) => routeHash({ name: 'disease', diseaseId, goal: goalId })
  const isDisease = item.type === 'disease'
  const title = isDisease ? diseaseDisplayName(item.id, item.label) : item.label
  const fullName = isDisease && shortDiseaseName(item.id) ? item.label : null
  const matchedText = item.matched_text && item.matched_text !== item.label ? `: ${item.matched_text}` : ''

  return (
    <li className="result">
      <span className="result__type">{searchTypeLabel(item.type)}</span>
      {action.kind === 'open' ? (
        <a className="result__title result__title--link" href={diseaseHref(action.diseaseId)}>
          {title}
        </a>
      ) : (
        <span className="result__title">{title}</span>
      )}
      {fullName && <span className="result__full-name">{fullName}</span>}
      {isExpert ? <span className="result__meta">
        Matched on {item.matched_on}
        {matchedText}
      </span> : <details className="product-disclosure"><summary>Why this matched</summary><p>Matched on {item.matched_on}{matchedText}</p></details>}
      {action.kind === 'open' && !isDisease && (
        <span className="result__meta result__opens">
          <Icon name="arrowRight" />
          Opens {diseaseDisplayName(action.diseaseId)}
        </span>
      )}
      {action.kind === 'choose' && (
        <div className="result__choice">
          <span className="result__meta">Appears in {action.diseaseIds.length} diseases. Choose one:</span>
          <span className="rb-cluster">
            {action.diseaseIds.map((diseaseId) => (
              <a key={diseaseId} className="rb-btn rb-btn--quiet" href={diseaseHref(diseaseId)}>
                {diseaseDisplayName(diseaseId)}
              </a>
            ))}
          </span>
        </div>
      )}
      {action.kind === 'none' && <span className="result__meta">Not linked to a disease in this collection.</span>}
    </li>
  )
}

type EmptyResultsProps = {
  query: string
  scopeNote: string
}

function EmptyResults({ query, scopeNote }: EmptyResultsProps) {
  return (
    <div className="empty-state" role="status">
      <Icon name="search" className="empty-state__icon" />
      <div className="empty-state__body">
        <p className="state__title">No match for “{query}” in this collection</p>
        <p>{scopeNote}</p>
        <p>Try a gene symbol such as SYNGAP1, a disease name, or one of the demonstration diseases below.</p>
      </div>
    </div>
  )
}
