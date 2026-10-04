import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { describe, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { demoKey, healthRequest, overviewRequest, searchRequest } from './requests.ts'
import type { DemoEntry } from './transport.ts'

const fixturesDir = fileURLToPath(new URL('../fixtures/', import.meta.url))
const manifest = JSON.parse(readFileSync(`${fixturesDir}manifest.json`, 'utf8')) as { entries: DemoEntry[] }
const keys = new Set(manifest.entries.map((entry) => entry.key))

describe('demo manifest', () => {
  test('every listed file exists and is valid JSON', () => {
    for (const entry of manifest.entries) {
      const path = `${fixturesDir}${entry.file}`
      assert.ok(existsSync(path), `${entry.file} is listed but missing`)
      assert.doesNotThrow(() => JSON.parse(readFileSync(path, 'utf8')), `${entry.file} is not JSON`)
    }
  })

  test('keys are unique', () => {
    assert.equal(keys.size, manifest.entries.length)
  })

  test('saved error responses use the error envelope', () => {
    for (const entry of manifest.entries.filter((e) => e.status >= 400)) {
      const body = JSON.parse(readFileSync(`${fixturesDir}${entry.file}`, 'utf8'))
      assert.equal(typeof body.error?.code, 'string', `${entry.file} lacks error.code`)
    }
  })

  test('covers the phase 1 journey: health, search, empty search, three overviews', () => {
    const required = [
      healthRequest(),
      searchRequest('syngap1'),
      searchRequest('not-in-this-slice'),
      overviewRequest('MONDO:0012960'),
      overviewRequest('MONDO:0012812'),
      overviewRequest('MONDO:0013388'),
    ]
    for (const req of required) assert.ok(keys.has(demoKey(req)), `missing ${demoKey(req)}`)
  })
})
