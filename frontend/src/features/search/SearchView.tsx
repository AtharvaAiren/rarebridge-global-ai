import { useApiClient } from '../../api/ApiContext.tsx'
import { useHealth } from '../../app/HealthContext.tsx'
import { usePreferences } from '../../app/PreferencesContext.tsx'
import { Icon } from '../../components/Icon.tsx'
import { availableGoals } from '../../domain/goals.ts'
import { useApiResource } from '../../hooks/useApiResource.ts'
import { DiseaseShortcuts } from './DiseaseShortcuts.tsx'
import { GoalPicker } from './GoalPicker.tsx'
import { SearchForm } from './SearchForm.tsx'
import { SearchResults } from './SearchResults.tsx'

type SearchViewProps = {
  query: string
  goalId: string
  onGoalChange: (goalId: string) => void
}

export function SearchView({ query, goalId, onGoalChange }: SearchViewProps) {
  const client = useApiClient()
  const { state: healthState } = useHealth()
  const { isExpert, openPanel } = usePreferences()
  const search = useApiResource(query ? `search:${query}` : null, (signal) => client.search(query, signal))
  const serviceGoals = healthState.status === 'success' ? healthState.data.goals : undefined

  return (
    <main id="main" className="rb-container view" tabIndex={-1}>
      <div className="product-search-layout">
      <section className="search-hero" aria-labelledby="search-title">
        <p className="product-eyebrow">Research starts with a connection</p>
        <h1 id="search-title">Find a clearer next step for your community.</h1>
        <p className="rb-lead search-hero__lead">
          {isExpert
            ? 'Explore research resources for a specific disease and goal. Inspect the evidence, applicability checks, and public collaborator routes.'
            : 'You don’t have to start from scratch. Find existing study methods, understand what still needs checking, and prepare a conversation with the right research team.'}
        </p>
        <SearchForm key={query} initialQuery={query} />
        <p className="product-scope-strip"><Icon name="info" /><span>Built for patient organizations and their research partners. This demonstration covers three conditions and planning a study over time.</span></p>
      </section>
      <aside className="product-search-aside" aria-labelledby="journey-intro-title">
        <h2 id="journey-intro-title">A connection is a starting point.</h2>
        <ol><li><div><strong>Find an existing resource</strong>A study method, questionnaire, or other recorded resource.</div></li><li><div><strong>Understand the open questions</strong>Who it was used with, what is available, and what needs checking.</div></li><li><div><strong>Prepare the next conversation</strong>A sourced brief you can review and share yourself.</div></li></ol>
        <button type="button" className="rb-btn rb-btn--quiet" onClick={() => openPanel('guide')}>See how it works<Icon name="arrowRight" /></button>
      </aside>
      </div>
      <div className="product-search-content">
      {query && <SearchResults query={query} resource={search} goalId={goalId} />}
      <GoalPicker goals={availableGoals(serviceGoals)} value={goalId} onChange={onGoalChange} />
      <DiseaseShortcuts goalId={goalId} />
      </div>
    </main>
  )
}
