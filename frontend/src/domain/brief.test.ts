import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, test } from 'node:test'
import type { AssessmentResponse } from '../api/types.ts'
import { BRIEF_DISCLAIMER, briefFileName, briefToText, buildBrief, defaultDraft } from './brief.ts'

const fixture = (name: string) =>
  JSON.parse(readFileSync(new URL(`../fixtures/${name}`, import.meta.url), 'utf8')) as AssessmentResponse
const PAPER = 'DOI:10.1002/epi.70374'
const PREPARED = new Date(2026, 9, 4)

const original = buildBrief({ assessment: fixture('assessment-syngap1.json'), hidden: [], preparedOn: PREPARED, dataMode: 'live' })
const hidden = buildBrief({
  assessment: fixture('assessment-syngap1-withdrawn.json'),
  hidden: [PAPER],
  preparedOn: PREPARED,
  dataMode: 'live',
})

describe('buildBrief', () => {
  test('uses the after state: hiding the paper moves two checks from supported to open', () => {
    assert.equal(original.supported.length, 2)
    assert.equal(hidden.supported.length, 0)
    assert.equal(hidden.open.length, original.open.length + 2)
  })

  test('lists the hidden source and explains what changed', () => {
    assert.deepEqual(
      hidden.hiddenSources.map((s) => s.id),
      [PAPER],
    )
    assert.match(hidden.outcomeNote ?? '', /2 checks changed/)
    assert.match(hidden.outcomeNote ?? '', /did not change/)
    assert.equal(original.outcomeNote, null)
  })

  test('numbers sources once, cited sources first, using the URLs the API gave', () => {
    assert.equal(original.sources[0].id, PAPER)
    assert.equal(original.sources[0].url, 'https://doi.org/10.1002/epi.70374')
    assert.deepEqual(
      original.sources.map((s) => s.number),
      original.sources.map((_, i) => i + 1),
    )
    assert.deepEqual(original.supported[0].sourceNumbers, [1])
  })

  test('carries recorded differences, including unestablished ownership', () => {
    assert.ok(original.differences.some((d) => /not demonstrated/.test(d)))
    assert.ok(original.differences.some((d) => /Ownership of protocol materials not established/.test(d)))
  })

  test('says plainly when there is no AI text', () => {
    assert.match(original.generation, /No AI-generated text/)
  })

  test('uses exact status labels and never approval wording', () => {
    const text = briefToText(hidden, defaultDraft(hidden))
    assert.match(text, /Questions still open/)
    assert.match(text, /Information missing/)
    assert.doesNotMatch(text, /approved|safe treatment|clinically validated/i)
  })
})

describe('defaultDraft', () => {
  test('is addressed to a role, not an invented person, and lists the API questions', () => {
    const draft = defaultDraft(original)
    assert.match(draft, /^Dear study coordinator,/)
    assert.match(draft, /1\. Can we access the protocol and instrument materials/)
    assert.match(draft, /2\. Which components need adapting/)
    assert.match(draft, /\[Your name\]/)
  })
})

describe('briefToText', () => {
  test('includes the edited draft, the hidden sources and the dated disclaimer', () => {
    const text = briefToText(hidden, 'My own words.')
    assert.match(text, /My own words\./)
    assert.match(text, /SOURCES HIDDEN IN THIS VIEW/)
    assert.match(text, /A prospective natural history study protocol/)
    assert.ok(text.includes(`${BRIEF_DISCLAIMER} Prepared 4 October 2026.`))
    assert.match(text, /\[1\] A prospective natural history study protocol.*\(hidden in this view\)/)
  })

  test('has no hidden-source section when nothing is hidden', () => {
    assert.doesNotMatch(briefToText(original, defaultDraft(original)), /SOURCES HIDDEN IN THIS VIEW/)
  })
})

describe('briefFileName', () => {
  test('is a dated, safe .txt name', () => {
    assert.equal(briefFileName(original), 'rarebridge-brief-starr-prommis-natural-history-framework-2026-10-04.txt')
  })
})
