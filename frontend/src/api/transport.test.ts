import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { ApiError } from './errors.ts'
import { demoKey, healthRequest, searchRequest, sourceRequest } from './requests.ts'
import { createDemoTransport, createLiveTransport, type FetchLike } from './transport.ts'

const ERROR_BODY = {
  schema_version: 'rarebridge.handoff.v1',
  error: { code: 'unknown_disease', message: 'This disease is not in the current data slice.', details: [] },
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    assert.ok(error instanceof ApiError, 'expected an ApiError')
    return error
  }
  assert.fail('expected the request to fail')
}

describe('live transport', () => {
  test('calls base URL + encoded path and returns the JSON body', async () => {
    const calls: string[] = []
    const fetchImpl: FetchLike = async (url) => {
      calls.push(url)
      return jsonResponse({ ok: true })
    }
    const transport = createLiveTransport('http://127.0.0.1:8000/', fetchImpl)

    const body = await transport(sourceRequest('DOI:10.1002/epi.70374'))

    assert.deepEqual(body, { ok: true })
    assert.deepEqual(calls, ['http://127.0.0.1:8000/api/sources/DOI%3A10.1002%2Fepi.70374'])
  })

  test('turns an error envelope into an http ApiError with code and message', async () => {
    const transport = createLiveTransport('http://x', async () => jsonResponse(ERROR_BODY, 404))

    const error = await rejection(transport(healthRequest()))

    assert.equal(error.kind, 'http')
    assert.equal(error.status, 404)
    assert.equal(error.code, 'unknown_disease')
    assert.equal(error.message, 'This disease is not in the current data slice.')
    assert.equal(error.isServiceFailure, false)
  })

  test('reports an unreachable service as a network error', async () => {
    const transport = createLiveTransport('http://x', async () => {
      throw new TypeError('Failed to fetch')
    })

    const error = await rejection(transport(healthRequest()))

    assert.equal(error.kind, 'network')
    assert.equal(error.isServiceFailure, true)
  })

  test('treats a 5xx without an envelope as a service failure', async () => {
    const transport = createLiveTransport('http://x', async () => new Response('Bad gateway', { status: 502 }))

    const error = await rejection(transport(healthRequest()))

    assert.equal(error.kind, 'http')
    assert.equal(error.code, 'http_502')
    assert.equal(error.isServiceFailure, true)
  })

  test('an AI service that is not connected is not a service outage', async () => {
    const body = { schema_version: 'x', error: { code: 'model_unavailable', message: 'not connected', details: [] } }
    const transport = createLiveTransport('http://x', async () => jsonResponse(body, 503))

    const error = await rejection(transport(healthRequest()))

    assert.equal(error.code, 'model_unavailable')
    assert.equal(error.isServiceFailure, false)
  })

  test('rejects a successful response that is not JSON', async () => {
    const transport = createLiveTransport('http://x', async () => new Response('<html>', { status: 200 }))

    const error = await rejection(transport(healthRequest()))

    assert.equal(error.kind, 'invalid_response')
  })

  test('sends POST bodies as JSON', async () => {
    let seen: RequestInit | undefined
    const transport = createLiveTransport('http://x', async (_url, init) => {
      seen = init
      return jsonResponse({})
    })

    await transport({ method: 'POST', path: '/api/assessments/evaluate', body: { a: 1 } })

    assert.equal(seen?.method, 'POST')
    assert.equal(seen?.body, '{"a":1}')
  })
})

describe('demo transport', () => {
  const entries = [
    { key: demoKey(searchRequest('syngap1')), file: 'search-syngap1.json', status: 200 },
    { key: demoKey(healthRequest()), file: 'error.json', status: 503 },
  ]
  const files: Record<string, unknown> = { 'search-syngap1.json': { items: [] }, 'error.json': ERROR_BODY }
  const transport = createDemoTransport(entries, async (file) => files[file])

  test('replays the saved response for a matching request', async () => {
    assert.deepEqual(await transport(searchRequest('SYNGAP1')), { items: [] })
  })

  test('fails with demo_missing instead of borrowing another response', async () => {
    const error = await rejection(transport(searchRequest('stxbp1')))

    assert.equal(error.kind, 'demo_missing')
    assert.equal(error.message, 'Not available in demo data')
    assert.equal(error.isServiceFailure, false)
  })

  test('replays saved error responses as errors', async () => {
    const error = await rejection(transport(healthRequest()))

    assert.equal(error.kind, 'http')
    assert.equal(error.status, 503)
    assert.equal(error.code, 'unknown_disease')
  })
})
