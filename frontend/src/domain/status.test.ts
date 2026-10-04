import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { originLabel, reviewSpec, statusSpec } from './status.ts'

const ALL_STATES = [
  'supported',
  'unknown',
  'needs_source_review',
  'conflicting',
  'refuted',
  'candidate_for_expert_review',
  'needs_information',
  'needs_expert_review',
  'not_supported_for_stated_use',
]

describe('statusSpec', () => {
  test('uses the exact spec labels', () => {
    assert.equal(statusSpec('supported').label, 'Source supports this check')
    assert.equal(statusSpec('unknown').label, 'Information missing')
    assert.equal(statusSpec('needs_information').label, 'Questions still open')
    assert.equal(statusSpec('candidate_for_expert_review').label, 'Ready for expert review')
    assert.equal(statusSpec('not_supported_for_stated_use').label, 'This proposed use lacks support')
  })

  test('never colours unknown as failure', () => {
    assert.equal(statusSpec('unknown').tone, 'unknown')
    assert.equal(statusSpec('needs_information').tone, 'unknown')
  })

  test('candidate for expert review is not green', () => {
    assert.equal(statusSpec('candidate_for_expert_review').tone, 'candidate')
  })

  test('shows an unexpected value plainly instead of guessing', () => {
    assert.equal(statusSpec('weird_state').label, 'Status: weird state')
  })

  test('no label claims approval or validation', () => {
    for (const state of ALL_STATES) {
      assert.doesNotMatch(statusSpec(state).label, /approved|safe treatment|clinically validated/i)
    }
  })
})

describe('reviewSpec', () => {
  test('uses the agreed badge wording', () => {
    assert.equal(reviewSpec('pending').label, 'Source check pending')
    assert.equal(reviewSpec('source_checked').label, 'Fact checked against source')
    assert.equal(reviewSpec(undefined).label, 'No review status recorded')
  })
})

describe('originLabel', () => {
  test('names inferred links as navigation aids', () => {
    assert.equal(originLabel('inferred'), 'Inferred for navigation')
  })
})
