import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { createApiClient } from './client.ts'
import { createLiveTransport } from './transport.ts'

describe('research API integration', () => {
  it('uses same-origin /api and copies the current hidden-source state for patient questions', async () => {
    const calls: { url: string; init: RequestInit }[] = []
    const client = createApiClient('live', createLiveTransport('/', async (url, init) => {
      calls.push({ url, init })
      return new Response(JSON.stringify({ assessment_id: 'citizen-dataset-for-syngap1', answer: {} }), { status: 200 })
    }))
    const hidden = ['DOI:10.1002/epi.70374']
    const pending = client.ask('citizen-dataset-for-syngap1', hidden, '  What is access?  ', 'patient')
    hidden.push('another-source')
    await pending
    assert.equal(calls[0]?.url, '/api/ai/ask')
    assert.deepEqual(JSON.parse(String(calls[0]?.init.body)), {
      assessment_id: 'citizen-dataset-for-syngap1', withdrawn_source_ids: ['DOI:10.1002/epi.70374'],
      question: 'What is access?', mode: 'patient',
    })
  })

  it('keeps model failure explicit without replaying fixtures or marking the data API down', async () => {
    const client = createApiClient('live', createLiveTransport('/', async () => new Response(JSON.stringify({
      error: { code: 'model_unavailable', message: 'No model configured.', details: [] },
    }), { status: 503 })))
    await assert.rejects(client.discover('MONDO:0013388', 'natural_history'), /No model configured/)
    assert.equal(client.getServiceStatus(), 'ok')
  })

  it('sends a source-bound import preview to the genuine extraction endpoint', async () => {
    let request: unknown
    const client = createApiClient('live', createLiveTransport('/', async (url, init) => {
      assert.equal(url, '/api/ai/extract')
      request = JSON.parse(String(init.body))
      return new Response(JSON.stringify({ extraction: { claims: [] }, import_status: 'not_imported' }), { status: 200 })
    }))
    const payload = { source_id: 'WEB:public-source', title: 'Public source', url: 'https://example.org/study', published_on: null, text: 'Quoted source text.' }
    assert.equal((await client.extract(payload)).import_status, 'not_imported')
    assert.deepEqual(request, payload)
  })
})
