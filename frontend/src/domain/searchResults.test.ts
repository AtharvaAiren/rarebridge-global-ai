import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import type { SearchItem } from '../api/types.ts'
import { orderSearchItems, searchItemAction, searchTypeLabel } from './searchResults.ts'

function item(overrides: Partial<SearchItem>): SearchItem {
  return { id: 'x', type: 'gene', label: 'X', matched_on: 'name', disease_ids: [], ...overrides }
}

describe('orderSearchItems', () => {
  test('puts diseases first and keeps the API order otherwise', () => {
    const items = [item({ id: 'g1' }), item({ id: 'd1', type: 'disease' }), item({ id: 'o1', type: 'organization' })]
    assert.deepEqual(
      orderSearchItems(items).map((i) => i.id),
      ['d1', 'g1', 'o1'],
    )
  })

  test('does not reorder the input array', () => {
    const items = [item({ id: 'g1' }), item({ id: 'd1', type: 'disease' })]
    orderSearchItems(items)
    assert.deepEqual(
      items.map((i) => i.id),
      ['g1', 'd1'],
    )
  })
})

describe('searchItemAction', () => {
  test('a disease opens itself', () => {
    assert.deepEqual(searchItemAction(item({ id: 'MONDO:1', type: 'disease', disease_ids: ['MONDO:1'] })), {
      kind: 'open',
      diseaseId: 'MONDO:1',
    })
  })

  test('a hit with one disease opens that disease', () => {
    assert.deepEqual(searchItemAction(item({ disease_ids: ['MONDO:2'] })), { kind: 'open', diseaseId: 'MONDO:2' })
  })

  test('a hit with several diseases asks her to choose, without duplicates', () => {
    assert.deepEqual(searchItemAction(item({ disease_ids: ['MONDO:1', 'MONDO:2', 'MONDO:1'] })), {
      kind: 'choose',
      diseaseIds: ['MONDO:1', 'MONDO:2'],
    })
  })

  test('a hit with no disease has no action', () => {
    assert.deepEqual(searchItemAction(item({ disease_ids: [] })), { kind: 'none' })
  })
})

describe('searchTypeLabel', () => {
  test('uses plain words for known types', () => {
    assert.equal(searchTypeLabel('claim'), 'Mechanism claim')
    assert.equal(searchTypeLabel('asset'), 'Research resource')
  })

  test('humanises unknown types instead of hiding them', () => {
    assert.equal(searchTypeLabel('go_term'), 'Go term')
  })
})
