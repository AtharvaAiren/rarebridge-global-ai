import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, test } from 'node:test'
import type { GraphResponse } from '../../api/types.ts'
import { centerOn, fitCamera, lerpCamera, screenToWorld, zoomAround, ZOOM_LIMITS } from './camera.ts'
import { buildGraphModel } from './graphModel.ts'
import { ANCHORS, computeLayout, labelPlacements, LAYOUT_BOUNDS, seededRandom } from './layout.ts'

const graph = JSON.parse(
  readFileSync(new URL('../../fixtures/graph-syngap1.json', import.meta.url), 'utf8'),
) as GraphResponse
const model = buildGraphModel(graph)
const SYNGAP1 = 'MONDO:0012960'
const FRAMEWORK = 'DOI:10.1002/epi.70374#framework'
const allIds = new Set(model.nodes.keys())
const input = { model, visibleIds: allIds, focusDiseaseId: SYNGAP1, focusResourceId: FRAMEWORK }

describe('computeLayout', () => {
  test('is deterministic', () => {
    assert.deepEqual([...computeLayout(input)], [...computeLayout(input)])
  })

  test('fixes the disease and the selected resource at their anchors', () => {
    const layout = computeLayout(input)
    assert.deepEqual(layout.get(SYNGAP1), ANCHORS.focusDisease)
    assert.deepEqual(layout.get(FRAMEWORK), ANCHORS.focusResource)
  })

  test('places every visible node inside the layout bounds', () => {
    const layout = computeLayout(input)
    assert.equal(layout.size, allIds.size)
    for (const p of layout.values()) {
      assert.ok(p.x >= LAYOUT_BOUNDS.minX && p.x <= LAYOUT_BOUNDS.maxX)
      assert.ok(p.y >= LAYOUT_BOUNDS.minY && p.y <= LAYOUT_BOUNDS.maxY)
    }
  })

  test('pinned nodes do not move when others are added', () => {
    const first = computeLayout({ ...input, visibleIds: new Set([SYNGAP1, FRAMEWORK, 'study:prommis']) })
    const second = computeLayout({ ...input, pinned: first })
    for (const [id, point] of first) assert.deepEqual(second.get(id), point)
  })
})

describe('labelPlacements', () => {
  const radii = new Map(['a', 'b', 'c', 'd', 'e'].map((id) => [id, 10]))
  const labels = new Map([
    ['a', 'ProMMiS natural history study'],
    ['b', 'STARR natural history study'],
    ['c', 'Far away'],
    ['d', 'Fourth label'],
    ['e', 'Fifth label'],
  ])

  test('two close labels end up on different sides, neither covering a node', () => {
    const positions = new Map([
      ['a', { x: 400, y: 200 }],
      ['b', { x: 460, y: 215 }],
      ['c', { x: 900, y: 600 }],
    ])
    const placement = labelPlacements(positions, labels, radii)
    assert.notEqual(placement.get('a'), placement.get('b'))
    assert.ok(placement.get('a') !== 'crowded' && placement.get('b') !== 'crowded')
    assert.equal(placement.get('c'), 'below')
  })

  test('a side that would leave the visible area is not used', () => {
    const positions = new Map([['c', { x: 990, y: 100 }]])
    const placement = labelPlacements(positions, labels, radii, { bounds: { left: 0, top: 0, right: 1000, bottom: 1000 } })
    assert.equal(placement.get('c'), 'left')
  })

  test('leaves well-separated labels below', () => {
    const positions = new Map([
      ['a', { x: 100, y: 100 }],
      ['b', { x: 600, y: 100 }],
    ])
    const placement = labelPlacements(positions, labels, radii)
    assert.equal(placement.get('a'), 'below')
    assert.equal(placement.get('b'), 'below')
  })

  test('an optional label with no room is crowded, a must-show label never is', () => {
    const crowd = new Map(['a', 'b', 'c', 'd', 'e'].map((id, i) => [id, { x: 400, y: 200 + i * 0.5 }]))
    const optional = labelPlacements(crowd, labels, radii)
    assert.ok([...optional.values()].includes('crowded'))
    const forced = labelPlacements(crowd, labels, radii, { mustShowIds: new Set(labels.keys()) })
    assert.ok(![...forced.values()].includes('crowded'))
  })
})

describe('orientation', () => {
  test('portrait swaps the anchor axes so the story reads top to bottom', () => {
    const layout = computeLayout({ ...input, orientation: 'portrait' })
    assert.deepEqual(layout.get(SYNGAP1), { x: ANCHORS.focusDisease.y, y: ANCHORS.focusDisease.x })
    assert.deepEqual(layout.get(FRAMEWORK), { x: ANCHORS.focusResource.y, y: ANCHORS.focusResource.x })
  })
})

describe('seededRandom', () => {
  test('repeats for the same seed', () => {
    const a = seededRandom(1)
    const b = seededRandom(1)
    assert.deepEqual([a(), a(), a()], [b(), b(), b()])
  })
})

describe('camera', () => {
  const viewport = { width: 800, height: 500 }

  test('fit puts the centre of the points in the centre of the viewport', () => {
    const camera = fitCamera([{ x: 100, y: 100 }, { x: 300, y: 200 }], viewport, 0)
    const centre = screenToWorld(camera, { x: 400, y: 250 })
    assert.ok(Math.abs(centre.x - 200) < 1e-9 && Math.abs(centre.y - 150) < 1e-9)
  })

  test('zoom keeps the pointer over the same world point', () => {
    const camera = centerOn({ x: 0, y: 0 }, 1, viewport)
    const pointer = { x: 120, y: 80 }
    const before = screenToWorld(camera, pointer)
    const after = screenToWorld(zoomAround(camera, pointer, 1.5), pointer)
    assert.ok(Math.abs(before.x - after.x) < 1e-9 && Math.abs(before.y - after.y) < 1e-9)
  })

  test('zoom is clamped', () => {
    assert.equal(zoomAround({ x: 0, y: 0, k: 1 }, { x: 0, y: 0 }, 100).k, ZOOM_LIMITS.max)
  })

  test('lerp hits both ends exactly', () => {
    const from = { x: 0, y: 0, k: 1 }
    const to = { x: 50, y: -20, k: 2 }
    assert.deepEqual(lerpCamera(from, to, 0), from)
    assert.deepEqual(lerpCamera(from, to, 1), to)
  })
})
