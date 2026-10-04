#!/usr/bin/env node
/**
 * Captures real API responses into src/fixtures/ for demo mode.
 *
 *   npm run capture-fixtures                      # API at http://127.0.0.1:8000
 *   RAREBRIDGE_API=http://host:port npm run capture-fixtures
 *
 * Uses the same request builders and demo keys as the app (src/api/requests.ts,
 * loaded through Node's built-in TypeScript support, Node 22.18+), so the
 * manifest always matches what the client asks for. Each response is saved
 * with its HTTP status; error responses are replayed as errors in demo mode.
 * Nothing is written unless every request reaches the service.
 */
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import {
  demoKey,
  evaluateRequest,
  explainRequest,
  graphRequest,
  GRAPH_NODES_DEFAULT,
  GRAPH_NODES_MORE,
  healthRequest,
  overviewRequest,
  requestUrl,
  searchRequest,
  sourceRequest,
} from '../src/api/requests.ts'

const FIXTURES_DIR = fileURLToPath(new URL('../src/fixtures/', import.meta.url))
const MANIFEST_PATH = `${FIXTURES_DIR}manifest.json`
const DEFAULT_BASE_URL = 'http://127.0.0.1:8000'
const REQUEST_TIMEOUT_MS = 30_000

const ANCHOR_DOI = 'DOI:10.1002/epi.70374'
const ANCHOR_PMID = 'PMID:42446932'
const SYNGAP1 = 'MONDO:0012960'
const STXBP1 = 'MONDO:0012812'
const SCN2A = 'MONDO:0013388'

/** HANDOVER.txt "SAMPLE REQUESTS", plus the evaluations and graphs the UI uses. */
function captureList() {
  const graphs = [
    ['syngap1', SYNGAP1, 'framework-for-syngap1'],
    ['stxbp1', STXBP1, 'framework-for-stxbp1'],
    ['scn2a', SCN2A, 'framework-for-scn2a'],
  ].flatMap(([name, diseaseId, assessmentId]) => [
    [`graph-${name}`, graphRequest({ diseaseId, assessmentId, maxNodes: GRAPH_NODES_DEFAULT })],
    [`graph-${name}-${GRAPH_NODES_MORE}`, graphRequest({ diseaseId, assessmentId, maxNodes: GRAPH_NODES_MORE })],
  ])

  return [
    ['health', healthRequest()],
    ['search-syngap1', searchRequest('syngap1')],
    ['search-stxbp1', searchRequest('stxbp1')],
    ['search-scn2a', searchRequest('scn2a')],
    ['search-stxbp1-foundation', searchRequest('STXBP1 Foundation')],
    ['search-empty', searchRequest('not-in-this-slice')],
    ['overview-syngap1', overviewRequest(SYNGAP1)],
    ['overview-stxbp1', overviewRequest(STXBP1)],
    ['overview-scn2a', overviewRequest(SCN2A)],
    ['assessment-syngap1', evaluateRequest('framework-for-syngap1', [])],
    ['assessment-syngap1-withdrawn', evaluateRequest('framework-for-syngap1', [ANCHOR_DOI])],
    ['assessment-stxbp1', evaluateRequest('framework-for-stxbp1', [])],
    ['assessment-stxbp1-withdrawn', evaluateRequest('framework-for-stxbp1', [ANCHOR_DOI])],
    ['assessment-scn2a', evaluateRequest('framework-for-scn2a', [])],
    ['assessment-scn2a-withdrawn', evaluateRequest('framework-for-scn2a', [ANCHOR_DOI])],
    ['assessment-citizen-dataset-syngap1', evaluateRequest('citizen-dataset-for-syngap1', [])],
    ['error-unknown-assessment', evaluateRequest('nope', [])],
    ...graphs,
    ['source-anchor', sourceRequest(ANCHOR_DOI)],
    ['source-anchor-pmid', sourceRequest(ANCHOR_PMID)],
    ['ai-explain-syngap1', explainRequest('framework-for-syngap1', [])],
  ]
}

function readBaseUrl() {
  const raw = (process.env.RAREBRIDGE_API || process.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).trim()
  const parsed = URL.parse(raw)
  if (!parsed || !['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error(`API base URL must be http(s), got "${raw}".`)
  }
  return raw.replace(/\/+$/, '')
}

async function fetchCapture(baseUrl, name, req) {
  const url = `${baseUrl}${requestUrl(req)}`
  const hasBody = req.body !== undefined
  let response
  try {
    response = await fetch(url, {
      method: req.method,
      headers: hasBody ? { accept: 'application/json', 'content-type': 'application/json' } : { accept: 'application/json' },
      body: hasBody ? JSON.stringify(req.body) : undefined,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch (error) {
    throw new Error(`${name}: could not reach ${url} (${error.message}). Is the API running?`)
  }
  const text = await response.text()
  let body
  try {
    body = JSON.parse(text)
  } catch {
    throw new Error(`${name}: ${req.method} ${url} answered HTTP ${response.status} with non-JSON content.`)
  }
  if (!response.ok && typeof body?.error?.code !== 'string') {
    throw new Error(`${name}: HTTP ${response.status} without the {error:{code,message,details}} envelope.`)
  }
  return { name, req, status: response.status, body }
}

async function writeAtomic(path, content) {
  const temporary = `${path}.tmp`
  await writeFile(temporary, content)
  await rename(temporary, path)
}

async function readManifest() {
  try {
    return JSON.parse(await readFile(MANIFEST_PATH, 'utf8'))
  } catch (error) {
    if (error.code === 'ENOENT') return { entries: [] }
    throw new Error(`Could not read ${MANIFEST_PATH}: ${error.message}`)
  }
}

async function main() {
  const baseUrl = readBaseUrl()
  console.log(`Capturing from ${baseUrl}`)

  const captures = []
  for (const [name, req] of captureList()) captures.push(await fetchCapture(baseUrl, name, req))

  await mkdir(FIXTURES_DIR, { recursive: true })
  for (const capture of captures) {
    await writeAtomic(`${FIXTURES_DIR}${capture.name}.json`, `${JSON.stringify(capture.body, null, 2)}\n`)
  }

  const captured = captures.map((c) => ({ key: demoKey(c.req), file: `${c.name}.json`, status: c.status }))
  const capturedKeys = new Set(captured.map((entry) => entry.key))
  const previous = await readManifest()
  const kept = (previous.entries ?? []).filter((entry) => !capturedKeys.has(entry.key))
  const manifest = {
    note: 'Demo mode answers a request only if its key is listed here. Regenerate with npm run capture-fixtures.',
    captured_from: baseUrl,
    captured_at: new Date().toISOString(),
    entries: [...captured, ...kept],
  }
  await writeAtomic(MANIFEST_PATH, `${JSON.stringify(manifest, null, 2)}\n`)

  for (const c of captures) console.log(`${String(c.status).padEnd(4)} ${c.name}.json`)
  console.log(`Wrote ${captures.length} responses; manifest has ${manifest.entries.length} entries (${kept.length} kept from before).`)
}

main().catch((error) => {
  console.error(`capture-fixtures failed: ${error.message}`)
  process.exitCode = 1
})
