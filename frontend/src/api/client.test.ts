import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { createApiClient } from './client.ts'
import { ApiError } from './errors.ts'
import type { Transport } from './transport.ts'

const HEALTH = { status: 'ok', capabilities: {}, data_snapshot: 'abc' }

function scriptedTransport(results: ReadonlyArray<() => unknown>): Transport {
  let call = 0
  return async () => results[Math.min(call++, results.length - 1)]()
}

const networkFailure = () => {
  throw new ApiError({ kind: 'network', message: 'down' })
}
const notFound = () => {
  throw new ApiError({ kind: 'http', status: 404, message: 'missing' })
}

describe('api client', () => {
  test('returns a body that has the contract fields', async () => {
    const client = createApiClient('live', scriptedTransport([() => HEALTH]))
    assert.deepEqual(await client.health(), HEALTH)
  })

  test('rejects a body missing contract fields', async () => {
    const client = createApiClient('live', scriptedTransport([() => ({ status: 'ok' })]))
    await assert.rejects(client.health(), (error: unknown) => {
      assert.ok(error instanceof ApiError)
      assert.equal(error.kind, 'invalid_response')
      assert.match(error.message, /capabilities/)
      return true
    })
  })

  test('marks the service unreachable on a network failure and recovers on success', async () => {
    const client = createApiClient('live', scriptedTransport([networkFailure, () => HEALTH]))
    let notifications = 0
    client.subscribeServiceStatus(() => notifications++)

    await assert.rejects(client.health())
    assert.equal(client.getServiceStatus(), 'unreachable')

    await client.health()
    assert.equal(client.getServiceStatus(), 'ok')
    assert.equal(notifications, 2)
  })

  test('a 404 is a request error, not a service outage', async () => {
    const client = createApiClient('live', scriptedTransport([notFound]))
    await assert.rejects(client.overview('MONDO:1', 'natural_history'))
    assert.equal(client.getServiceStatus(), 'ok')
  })

  test('unsubscribe stops notifications', async () => {
    const client = createApiClient('live', scriptedTransport([networkFailure]))
    let notifications = 0
    const unsubscribe = client.subscribeServiceStatus(() => notifications++)
    unsubscribe()

    await assert.rejects(client.health())
    assert.equal(notifications, 0)
  })

  test('reports its mode', () => {
    assert.equal(createApiClient('demo', scriptedTransport([() => HEALTH])).mode, 'demo')
  })
})
