import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, test } from 'node:test'
import type { AssessmentResponse } from '../api/types.ts'
import {
  canonicalId,
  changesByCheck,
  citedSourceIds,
  normalizeIds,
  polarityLabel,
  sourceOverlay,
  splitChecks,
  withId,
  withoutId,
} from './assessment.ts'

const fixture = (name: string) =>
  JSON.parse(readFileSync(new URL(`../fixtures/${name}`, import.meta.url), 'utf8')) as AssessmentResponse
const withdrawn = fixture('assessment-syngap1-withdrawn.json')
const original = fixture('assessment-syngap1.json')
const PAPER = 'DOI:10.1002/epi.70374'

describe('withdrawal lists', () => {
  test('are de-duplicated and sorted', () => {
    assert.deepEqual(normalizeIds(['b', 'a', 'b']), ['a', 'b'])
    assert.deepEqual(withId(['b'], 'a'), ['a', 'b'])
    assert.deepEqual(withoutId(['a', 'b'], 'a'), ['b'])
  })

  test('the PMID alias resolves to the same paper', () => {
    assert.equal(canonicalId(withdrawn.sources, 'PMID:42446932'), PAPER)
    assert.equal(canonicalId(withdrawn.sources, PAPER), PAPER)
  })
})

describe('the anchor fixture after hiding the paper', () => {
  test('two checks lose support while the overall outcome stays needs_information', () => {
    const changes = changesByCheck(withdrawn.changed_checks)
    assert.equal(changes.size, 2)
    for (const change of changes.values()) {
      assert.equal(change.before, 'supported')
      assert.equal(change.after, 'unknown')
    }
    assert.equal(withdrawn.before.outcome, 'needs_information')
    assert.equal(withdrawn.after.outcome, 'needs_information')
  })

  test('the paper moves to withdrawn evidence instead of disappearing', () => {
    const check = withdrawn.after.checks.find((c) => c.id === 'documented-framework')
    assert.equal(check?.active_evidence.length, 0)
    assert.equal(check?.withdrawn_evidence[0]?.source_id, PAPER)
  })

  test('reset (empty list) has no changed checks', () => {
    assert.equal(original.changed_checks.length, 0)
  })
})

describe('splitChecks', () => {
  test('separates required from optional checks', () => {
    const { required, optional } = splitChecks(original.before.checks)
    assert.ok(required.every((c) => c.required))
    assert.ok(optional.every((c) => !c.required))
    assert.equal(required.length + optional.length, original.before.checks.length)
  })
})

describe('sourceOverlay', () => {
  const identity = (id: string) => id
  const edges = [
    { id: 'one-source', source_ids: [PAPER] },
    { id: 'two-sources', source_ids: [PAPER, 'WEB:other'] },
    { id: 'unrelated', source_ids: ['WEB:other'] },
    { id: 'alias', source_ids: ['PMID:42446932'] },
  ]

  test('marks fully and partly affected edges separately', () => {
    const overlay = sourceOverlay(edges, [PAPER], (id) => canonicalId(withdrawn.sources, id))
    assert.deepEqual([...overlay.fully].sort(), ['alias', 'one-source'])
    assert.deepEqual([...overlay.partly], ['two-sources'])
  })

  test('a multi-source edge is never marked fully hidden by one source', () => {
    const overlay = sourceOverlay(edges, [PAPER], identity)
    assert.ok(!overlay.fully.has('two-sources'))
  })

  test('nothing is affected when nothing is hidden', () => {
    const overlay = sourceOverlay(edges, [], identity)
    assert.equal(overlay.partly.size + overlay.fully.size, 0)
  })
})

describe('labels and lookups', () => {
  test('polarity reads as plain language', () => {
    assert.equal(polarityLabel('support'), 'Supports this check')
    assert.equal(polarityLabel('uncertain'), 'Leaves this check uncertain')
    assert.equal(polarityLabel('odd_value'), 'odd value')
  })

  test('cited sources are listed once', () => {
    assert.deepEqual(citedSourceIds(withdrawn.after.checks), [PAPER])
  })
})
