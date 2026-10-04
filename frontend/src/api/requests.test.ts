import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import {
  demoKey,
  evaluateRequest,
  graphRequest,
  GRAPH_NODES_DEFAULT,
  overviewRequest,
  requestUrl,
  searchRequest,
  sourceRequest,
} from './requests.ts'

describe('request builders', () => {
  test('encodes path parameters, including the slash inside a DOI', () => {
    assert.equal(sourceRequest('DOI:10.1002/epi.70374').path, '/api/sources/DOI%3A10.1002%2Fepi.70374')
    assert.equal(overviewRequest('MONDO:0012960').path, '/api/diseases/MONDO%3A0012960/overview')
  })

  test('overview defaults to the natural_history goal', () => {
    assert.equal(requestUrl(overviewRequest('MONDO:0012960')), '/api/diseases/MONDO%3A0012960/overview?goal=natural_history')
  })

  test('search trims the query and sends the fixed limit', () => {
    assert.equal(requestUrl(searchRequest('  syngap1 ')), '/api/search?limit=10&q=syngap1')
  })

  test('graph asks for the default node budget unless told otherwise', () => {
    const req = graphRequest({ diseaseId: 'MONDO:0012960' })
    assert.equal(req.query?.max_nodes, String(GRAPH_NODES_DEFAULT))
    assert.equal(req.query?.assessment_id, undefined)
  })

  test('evaluate copies the withdrawal list instead of sharing it', () => {
    const withdrawn = ['DOI:10.1002/epi.70374']
    const req = evaluateRequest('framework-for-syngap1', withdrawn)
    withdrawn.push('PMID:1')
    assert.deepEqual(req.body, { assessment_id: 'framework-for-syngap1', withdrawn_source_ids: ['DOI:10.1002/epi.70374'] })
  })
})

describe('demoKey', () => {
  test('ignores search case, as the live search does', () => {
    assert.equal(demoKey(searchRequest('SYNGAP1')), demoKey(searchRequest('syngap1')))
  })

  test('ignores withdrawal order', () => {
    const a = evaluateRequest('x', ['B', 'A'])
    const b = evaluateRequest('x', ['A', 'B'])
    assert.equal(demoKey(a), demoKey(b))
  })

  test('distinguishes different withdrawal lists', () => {
    assert.notEqual(demoKey(evaluateRequest('x', [])), demoKey(evaluateRequest('x', ['A'])))
  })

  test('is independent of query key order', () => {
    const a = { method: 'GET' as const, path: '/p', query: { b: '2', a: '1' } }
    const b = { method: 'GET' as const, path: '/p', query: { a: '1', b: '2' } }
    assert.equal(demoKey(a), demoKey(b))
  })
})
