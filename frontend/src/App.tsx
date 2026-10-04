import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { HealthProvider } from './app/HealthContext.tsx'
import { PreferencesProvider } from './app/PreferencesContext.tsx'
import { AppFooter } from './components/AppFooter.tsx'
import { AppHeader } from './components/AppHeader.tsx'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'
import { ModeBanner } from './components/ModeBanner.tsx'
import { ProductPanel } from './components/ProductPanel.tsx'
import { DEFAULT_GOAL_ID } from './domain/goals.ts'
import { RouteView } from './features/route/RouteView.tsx'
import { SearchView } from './features/search/SearchView.tsx'
import { useRoute } from './hooks/useRoute.ts'
import { pageKey } from './routing.ts'
import './styles/product.css'

const MAIN_ID = 'main'

// The skip link must not change the hash: the hash is the route.
function handleSkipLink(event: MouseEvent<HTMLAnchorElement>) {
  event.preventDefault()
  document.getElementById(MAIN_ID)?.focus()
}

export function App() {
  const route = useRoute()
  const [goalId, setGoalId] = useState(DEFAULT_GOAL_ID)
  // Opening the evidence view changes the hash but is the same page: no jump to top.
  const routeKey = pageKey(route)
  const previousRouteKey = useRef(routeKey)

  // Move to the top of the new view and put focus there, like a page load.
  // Comparing route keys (not a first-render flag) keeps StrictMode's
  // effect re-run from stealing focus on the initial load.
  useEffect(() => {
    if (previousRouteKey.current === routeKey) return
    previousRouteKey.current = routeKey
    window.scrollTo({ top: 0 })
    document.getElementById(MAIN_ID)?.focus({ preventScroll: true })
  }, [routeKey])

  return (
    <PreferencesProvider><HealthProvider>
      <a className="skip-link rb-btn rb-btn--primary" href={`#${MAIN_ID}`} onClick={handleSkipLink}>
        Skip to content
      </a>
      <AppHeader />
      <ModeBanner />
      <ErrorBoundary resetKey={routeKey}>
      {route.name === 'disease' ? (
        <RouteView
          key={route.diseaseId}
          diseaseId={route.diseaseId}
          goalId={route.goal}
          evidenceId={route.evidenceId}
          isBriefOpen={route.isBriefOpen === true}
        />
      ) : (
        <SearchView query={route.name === 'search' ? route.query : ''} goalId={goalId} onGoalChange={setGoalId} />
      )}
      </ErrorBoundary>
      <AppFooter />
      <ProductPanel />
    </HealthProvider></PreferencesProvider>
  )
}
