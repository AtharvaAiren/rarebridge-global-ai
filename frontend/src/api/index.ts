/**
 * The one place that picks the data mode.
 * VITE_API_BASE_URL set   -> live mode against that service.
 * VITE_API_BASE_URL empty -> demo mode, replaying src/fixtures via manifest.json.
 */
import manifest from '../fixtures/manifest.json'
import { createApiClient, type ApiClient } from './client.ts'
import { ApiError } from './errors.ts'
import { createDemoTransport, createLiveTransport, type DemoEntry } from './transport.ts'

const fixtureModules = import.meta.glob<{ default: unknown }>(['../fixtures/*.json', '!../fixtures/manifest.json'])

async function loadFixture(file: string): Promise<unknown> {
  const load = fixtureModules[`../fixtures/${file}`]
  if (!load) {
    throw new ApiError({ kind: 'invalid_response', message: `Saved example file ${file} is listed but missing.` })
  }
  const module = await load()
  return module.default
}

function readBaseUrl(): string {
  const raw = (import.meta.env.VITE_API_BASE_URL ?? '').trim()
  // The deployed frontend and Python API share one public origin. Development
  // fixtures require an explicit development environment, never a live fallback.
  if (raw === '/' || (raw === '' && import.meta.env.PROD)) return '/'
  if (raw === '') return ''
  const parsed = URL.parse(raw)
  if (!parsed || !['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error(`VITE_API_BASE_URL must be an http(s) URL, got "${raw}".`)
  }
  return raw
}

function createClient(): ApiClient {
  const baseUrl = readBaseUrl()
  if (baseUrl) {
    return createApiClient('live', createLiveTransport(baseUrl, (input, init) => fetch(input, init)))
  }
  const entries: readonly DemoEntry[] = manifest.entries
  return createApiClient('demo', createDemoTransport(entries, loadFixture))
}

export const apiClient = createClient()
