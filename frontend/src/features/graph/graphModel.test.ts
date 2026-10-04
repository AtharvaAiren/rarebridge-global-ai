import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, test } from 'node:test'
import type { GraphResponse, OverviewResponse } from '../../api/types.ts'
import {
  assessmentAssetId,
  buildGraphModel,
  canonicalSourceId,
  checkRoute,
  edgeLineStyle,
  endpointId,
  focusedNodeIds,
  hopDistances,
  nodeGroup,
  parallelCurvature,
  routeSteps,
} from './graphModel.ts'

const fixture = (name: string) => JSON.parse(readFileSync(new URL(`../../fixtures/${name}`, import.meta.url), 'utf8'))
const graph = fixture('graph-syngap1.json') as GraphResponse
const overview = fixture('overview-syngap1.json') as OverviewResponse
const model = buildGraphModel(graph)
const SYNGAP1 = 'MONDO:0012960'
const STXBP1 = 'MONDO:0012812'
const FRAMEWORK = 'DOI:10.1002/epi.70374#framework'
const PAPER = 'DOI:10.1002/epi.70374'

describe('buildGraphModel', () => {
  test('keeps every edge whose endpoints exist and copies instead of sharing', () => {
    assert.equal(model.edges.length + model.droppedEdgeIds.length, graph.edges.length)
    assert.notEqual(model.edges[0], graph.edges[0])
    assert.notEqual(model.nodes.get(SYNGAP1), graph.nodes.find((n) => n.id === SYNGAP1))
  })

  test('keeps endpoint IDs separately from source/target', () => {
    const edge = model.edges[0]
    assert.equal(edge.sourceId, graph.edges[0].source)
    assert.equal(edge.targetId, graph.edges[0].target)
  })
})

describe('endpointId', () => {
  test('accepts a string or an object with id', () => {
    assert.equal(endpointId('a'), 'a')
    assert.equal(endpointId({ id: 'b' }), 'b')
  })
})

describe('edgeLineStyle', () => {
  test('inferred is dotted even when its source was checked', () => {
    assert.equal(edgeLineStyle({ claim_origin: 'inferred', review_status: 'source_checked' }), 'dotted')
  })
  test('pending is dashed, checked is solid', () => {
    assert.equal(edgeLineStyle({ claim_origin: 'recorded', review_status: 'pending' }), 'dashed')
    assert.equal(edgeLineStyle({ claim_origin: 'imported', review_status: 'source_checked' }), 'solid')
  })
})

describe('nodeGroup', () => {
  test('groups people, biology and resources', () => {
    assert.equal(nodeGroup('study_team'), 'people')
    assert.equal(nodeGroup('cell_type'), 'biology')
    assert.equal(nodeGroup('claim'), 'biology')
    assert.equal(nodeGroup('asset'), 'resource')
  })
})

describe('focused view', () => {
  const routes = overview.related_diseases.flatMap((r) => r.recorded_routes ?? [])
  const focus = focusedNodeIds(model, {
    diseaseId: SYNGAP1,
    assessmentId: 'framework-for-syngap1',
    routes,
    relatedDiseaseIds: overview.related_diseases.map((r) => r.id),
    contactIds: [...overview.organizations, ...overview.related_diseases.flatMap((r) => r.organizations ?? [])].map(
      (c) => c.id,
    ),
  })

  test('holds the disease, assessed resource, its paper and the route studies', () => {
    for (const id of [SYNGAP1, STXBP1, FRAMEWORK, PAPER, 'study:prommis', 'study:starr']) {
      assert.ok(focus.has(id), `missing ${id}`)
    }
  })

  test('stays within the brief target of roughly 12-18 real nodes', () => {
    assert.ok(focus.size >= 10 && focus.size <= 18, `size ${focus.size}`)
    for (const id of focus) assert.ok(model.nodes.has(id))
  })

  test('finds the assessed asset from the assessment_scope edge', () => {
    assert.equal(assessmentAssetId(model, 'framework-for-syngap1'), FRAMEWORK)
    assert.equal(assessmentAssetId(model, 'no-such-assessment'), undefined)
  })
})

describe('recorded routes', () => {
  const related = overview.related_diseases.find((r) => r.id === STXBP1)
  const [direct, longRoute] = related?.recorded_routes ?? []

  test('both SYNGAP1-STXBP1 routes are complete in the 40-node view', () => {
    assert.ok(checkRoute(direct, model).isComplete)
    assert.ok(checkRoute(longRoute, model).isComplete)
  })

  test('the longer route keeps each edge in its recorded direction', () => {
    const steps = routeSteps(longRoute, model)
    assert.equal(steps.length, 4)
    assert.ok(steps.every((s) => s.edgeId !== null))
    for (const step of steps) {
      const edge = model.edgesById.get(step.edgeId ?? '')
      const forward = edge?.sourceId === step.fromId && edge?.targetId === step.toId
      assert.equal(step.isReversed, !forward)
    }
  })

  test('reports missing pieces instead of inventing them', () => {
    const check = checkRoute({ explanation: '', node_path: [SYNGAP1, 'nowhere'], edge_ids: ['edge:nope'] }, model)
    assert.equal(check.isComplete, false)
    assert.deepEqual(check.missingNodeIds, ['nowhere'])
    assert.deepEqual(check.missingEdgeIds, ['edge:nope'])
  })
})

describe('canonicalSourceId', () => {
  test('resolves the PMID alias to the DOI and leaves unknown IDs alone', () => {
    assert.equal(canonicalSourceId(model.sources, 'PMID:42446932'), PAPER)
    assert.equal(canonicalSourceId(model.sources, PAPER), PAPER)
    assert.equal(canonicalSourceId(model.sources, 'XYZ:1'), 'XYZ:1')
  })
})

describe('parallelCurvature', () => {
  test('separates the two SYNGAP1-STXBP1 links', () => {
    const pairKey = [SYNGAP1, STXBP1].sort().join()
    const pair = model.edges.filter((e) => [e.sourceId, e.targetId].sort().join() === pairKey)
    assert.ok(pair.length >= 2)
    const curvature = parallelCurvature(model.edges)
    assert.equal(new Set(pair.map((e) => curvature.get(e.id))).size, pair.length)
  })
})

describe('hopDistances', () => {
  test('starts at zero and only walks visible nodes', () => {
    const hops = hopDistances(model, SYNGAP1, new Set([SYNGAP1, STXBP1]))
    assert.equal(hops.get(SYNGAP1), 0)
    assert.equal(hops.get(STXBP1), 1)
    assert.equal(hops.size, 2)
  })
})
