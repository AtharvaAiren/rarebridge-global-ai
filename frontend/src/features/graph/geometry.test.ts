import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { safeExternalUrl, urlHost } from '../../domain/urls.ts'
import { edgeShape } from './geometry.ts'

describe('edgeShape', () => {
  test('a straight edge starts and ends on the node outlines', () => {
    const shape = edgeShape({ x: 0, y: 0 }, { x: 100, y: 0 }, 0, 10, 10)
    assert.deepEqual(shape.start, { x: 10, y: 0 })
    assert.ok(shape.end.x < 90 && shape.end.x > 85)
    assert.equal(shape.mid.y, 0)
  })

  test('curvature bends the edge to one side and its opposite to the other', () => {
    const up = edgeShape({ x: 0, y: 0 }, { x: 100, y: 0 }, 0.2, 0, 0)
    const down = edgeShape({ x: 0, y: 0 }, { x: 100, y: 0 }, -0.2, 0, 0)
    assert.ok(up.mid.y * down.mid.y < 0)
  })
})

describe('safeExternalUrl', () => {
  test('keeps http(s) links', () => {
    assert.equal(safeExternalUrl('https://doi.org/10.1002/epi.70374'), 'https://doi.org/10.1002/epi.70374')
  })

  test('drops script and data URLs, junk and empty values', () => {
    assert.equal(safeExternalUrl('javascript:alert(1)'), undefined)
    assert.equal(safeExternalUrl('data:text/html,hi'), undefined)
    assert.equal(safeExternalUrl('not a url'), undefined)
    assert.equal(safeExternalUrl(''), undefined)
    assert.equal(safeExternalUrl(null), undefined)
  })

  test('urlHost strips www', () => {
    assert.equal(urlHost('https://www.stxbp1disorders.org/starr'), 'stxbp1disorders.org')
  })
})
