import { createContext, useContext, type ReactNode } from 'react'
import { useApiClient } from '../api/ApiContext.tsx'
import type { HealthResponse } from '../api/types.ts'
import { useApiResource, type Resource } from '../hooks/useApiResource.ts'

const HealthContext = createContext<Resource<HealthResponse> | null>(null)

type HealthProviderProps = {
  children: ReactNode
}

/** Loads /api/health once: capabilities, goals and the data snapshot. */
export function HealthProvider({ children }: HealthProviderProps) {
  const client = useApiClient()
  const health = useApiResource('health', (signal) => client.health(signal))
  return <HealthContext.Provider value={health}>{children}</HealthContext.Provider>
}

export function useHealth(): Resource<HealthResponse> {
  const health = useContext(HealthContext)
  if (!health) throw new Error('useHealth must be used inside <HealthProvider>.')
  return health
}
