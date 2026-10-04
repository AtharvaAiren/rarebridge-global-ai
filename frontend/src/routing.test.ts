import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { pageKey, parseHash, routeHash, type Route } from './routing.ts'

describe('routing', () => {
  test('empty and unknown hashes go home', () => {
    assert.deepEqual(parseHash(''), { name: 'home' })
    assert.deepEqual(parseHash('#/'), { name: 'home' })
    assert.deepEqual(parseHash('#/nowhere'), { name: 'home' })
    assert.deepEqual(parseHash('#main'), { name: 'home' })
  })

  test('a search without text goes home', () => {
    assert.deepEqual(parseHash('#/search?q=%20'), { name: 'home' })
  })

  test('round-trips search and disease routes', () => {
    const routes: Route[] = [
      { name: 'search', query: 'STXBP1 Foundation' },
      { name: 'disease', diseaseId: 'MONDO:0012960', goal: 'natural_history' },
    ]
    for (const route of routes) assert.deepEqual(parseHash(routeHash(route)), route)
  })

  test('encodes the disease ID in the hash', () => {
    assert.equal(
      routeHash({ name: 'disease', diseaseId: 'MONDO:0012960', goal: 'natural_history' }),
      '#/disease/MONDO%3A0012960?goal=natural_history',
    )
  })

  test('a disease route without a goal uses natural_history', () => {
    assert.deepEqual(parseHash('#/disease/MONDO%3A0012812'), {
      name: 'disease',
      diseaseId: 'MONDO:0012812',
      goal: 'natural_history',
    })
  })

  test('the evidence view is part of the disease route', () => {
    const route: Route = { name: 'disease', diseaseId: 'MONDO:0012960', goal: 'natural_history', evidenceId: 'framework-for-syngap1' }
    assert.deepEqual(parseHash(routeHash(route)), route)
  })

  test('opening the evidence view does not change the page identity', () => {
    const base: Route = { name: 'disease', diseaseId: 'MONDO:0012960', goal: 'natural_history' }
    assert.equal(pageKey({ ...base, evidenceId: 'framework-for-syngap1' }), pageKey(base))
  })

  test('the brief opens only together with an assessment', () => {
    const route: Route = {
      name: 'disease',
      diseaseId: 'MONDO:0012960',
      goal: 'natural_history',
      evidenceId: 'framework-for-syngap1',
      isBriefOpen: true,
    }
    assert.deepEqual(parseHash(routeHash(route)), route)
    assert.equal((parseHash('#/disease/MONDO%3A0012960?brief=1') as { isBriefOpen?: boolean }).isBriefOpen, undefined)
  })

  test('a malformed disease ID goes home instead of throwing', () => {
    assert.deepEqual(parseHash('#/disease/%E0%A4%A'), { name: 'home' })
  })
})
