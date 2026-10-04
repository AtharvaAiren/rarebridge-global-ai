export type Selection = { kind: 'none' } | { kind: 'node'; id: string } | { kind: 'edge'; id: string }

export type ViewMode = 'focused' | 'explore'

/** Commands from outside the map (route callout, resource list, journey bar). */
export type AtlasRequest =
  | { kind: 'trace'; routeKey: string; nonce: number }
  | { kind: 'select'; nodeId: string; nonce: number }
