import { createContext, useContext, useSyncExternalStore, type ReactNode } from 'react'
import type { ApiClient, ServiceStatus } from './client.ts'

const ApiContext = createContext<ApiClient | null>(null)

type ApiProviderProps = {
  client: ApiClient
  children: ReactNode
}

export function ApiProvider({ client, children }: ApiProviderProps) {
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>
}

export function useApiClient(): ApiClient {
  const client = useContext(ApiContext)
  if (!client) throw new Error('useApiClient must be used inside <ApiProvider>.')
  return client
}

export function useServiceStatus(): ServiceStatus {
  const client = useApiClient()
  return useSyncExternalStore(client.subscribeServiceStatus, client.getServiceStatus)
}
