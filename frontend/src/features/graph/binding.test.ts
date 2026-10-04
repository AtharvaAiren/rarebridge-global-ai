import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import type { OverviewResponse } from '../../api/types.ts'
import { selectedGraphAssessment } from './binding.ts'

const overview = {
  opportunities: [{ assessment_id: 'first-resource' }, { assessment_id: 'second-resource' }],
} as OverviewResponse

describe('selected graph assessment', () => {
  test('an opened second assessment overrides the first resource', () => {
    assert.equal(selectedGraphAssessment(overview, 'second-resource'), 'second-resource')
  })
  test('the retained selection remains the anchor after evidence closes', () => {
    assert.equal(selectedGraphAssessment(overview, undefined, 'second-resource'), 'second-resource')
  })
  test('the opened assessment takes precedence over a previous selection', () => {
    assert.equal(selectedGraphAssessment(overview, 'second-resource', 'first-resource'), 'second-resource')
  })
  test('an uncovered overview does not invent an assessment', () => {
    assert.equal(selectedGraphAssessment({ opportunities: [] } as unknown as OverviewResponse), undefined)
  })
})
