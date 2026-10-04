/** Capture the real public journey. No fixtures, mocked API results or AI claims. */
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
import { chromium } from '../.tools/node_modules/playwright/index.mjs'

const base = process.argv[2]
assert.match(base ?? '', /^https:\/\/[a-z0-9.-]+$/)
const output = 'submission/walkthrough'
await mkdir(output, { recursive: true })
const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 },
  recordVideo: { dir: '.tools/walkthrough-recordings', size: { width: 1440, height: 1000 } }, acceptDownloads: true })
const creationTime = Date.now()
const page = await context.newPage()
const video = page.video()
const errors = [], events = []
page.on('pageerror', error => errors.push(error.message))
await page.goto(base, { waitUntil: 'networkidle' })
await page.locator('#search-input').waitFor()
const start = Date.now()
const trimStart = (start - creationTime) / 1000
const until = async seconds => {
  const remaining = start + seconds * 1000 - Date.now()
  if (remaining > 0) await page.waitForTimeout(remaining)
}
const note = name => events.push({ seconds: Math.round((Date.now() - start) / 100) / 10, name })
try {
  note('Public production search')
  await until(2)
  await page.locator('#search-input').pressSequentially('SYNGAP1', { delay: 160 })
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await page.getByRole('link', { name: 'SYNGAP1', exact: true }).first().waitFor()
  await until(6)
  await page.getByRole('link', { name: 'SYNGAP1', exact: true }).first().click()
  await page.getByRole('navigation', { name: 'Journey' }).waitFor()
  note('Disease and natural-history goal')
  await until(10)
  await page.getByRole('navigation', { name: 'Journey' }).getByRole('button', { name: 'Connection' }).click()
  await page.locator('.atlas__stage').scrollIntoViewIfNeeded()
  note('Trace the actual reviewed inferred route')
  await until(19)
  await page.getByRole('navigation', { name: 'Journey' }).getByRole('button', { name: 'Evidence' }).click()
  await page.locator('.dependence').getByRole('button', { name: 'Hide', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Fit view', exact: true }).click()
  note('Specific resource assessment')
  await until(26)
  await page.locator('.dependence').getByRole('button', { name: 'Hide', exact: true }).click()
  await page.locator('.change-summary__item').first().waitFor()
  assert.equal(await page.locator('.change-summary__item').count(), 2)
  note('Two supported checks lose support')
  await until(34)
  await page.locator('.dependence').getByRole('button', { name: 'Show again', exact: true }).click()
  await page.waitForFunction(() => document.querySelectorAll('.change-summary__item').length === 0)
  note('Restore support without changing records')
  await until(39)
  await page.goto(`${base}/#/disease/MONDO%3A0013388?goal=natural_history&evidence=framework-for-scn2a`, { waitUntil: 'networkidle' })
  await page.getByRole('tabpanel', { name: 'Evidence', exact: true }).waitFor()
  await page.locator('.atlas__stage').scrollIntoViewIfNeeded()
  note('SCN2A applicability remains unknown')
  await until(45)
  await page.goto(`${base}/#/disease/MONDO%3A0012960?goal=natural_history&evidence=framework-for-syngap1`, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Prepare collaboration brief', exact: true }).click()
  await page.getByRole('button', { name: 'Download as text', exact: true }).waitFor()
  note('Sourced collaboration proposal')
  await until(50)
  await page.locator('.brief').getByRole('heading', { name: 'Public contact routes', exact: true }).scrollIntoViewIfNeeded()
  await until(53)
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download as text', exact: true }).click()
  const download = await downloadPromise
  await download.saveAs(`${output}/demonstrated-brief.txt`)
  note('Actual text export')
  assert.ok((Date.now() - start) / 1000 < 60, 'Journey exceeded the one-minute storyboard')
  await until(61)
} finally {
  await context.close()
  const rawPath = await video.path()
  const report = { base_url: base, recorded_at: new Date().toISOString(), raw_video_path: rawPath,
    trim_start_seconds: trimStart, target_duration_seconds: 60, events, browser_errors: errors,
    mocked_responses: false, scope: 'Real public graph, assessments and brief export. No claim of clinical validation or measured 10x impact.' }
  await writeFile(`${output}/capture.json`, JSON.stringify(report, null, 2) + '\n')
  await browser.close()
  console.log(JSON.stringify({ capture_complete: events.length === 9 && errors.length === 0, events, browser_errors: errors }))
}
