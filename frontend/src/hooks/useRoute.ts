import { useSyncExternalStore } from 'react'
import { parseHash, routeHash, type Route } from '../routing.ts'

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

const readHash = () => window.location.hash

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, readHash)
  return parseHash(hash)
}

export function navigate(route: Route): void {
  window.location.hash = routeHash(route)
}
