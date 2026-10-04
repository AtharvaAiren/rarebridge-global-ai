/** Record the real governed-access example for the team product video. */
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
import { chromium } from '../.tools/node_modules/playwright/index.mjs'
const base = process.argv[2]
assert.match(base ?? '', /^https:\/\/[a-z0-9.-]+$/)
await mkdir('submission/team-video', { recursive: true })
const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 },
  recordVideo: { dir: '.tools/team-recordings', size: { width: 1440, height: 1000 } } })
const created = Date.now(), page = await context.newPage(), video = page.video(), errors = []
page.on('pageerror', e => errors.push(e.message))
await page.goto(`${base}/#/disease/MONDO%3A0012960?goal=natural_history&evidence=citizen-dataset-for-syngap1`, { waitUntil: 'networkidle' })
await page.getByRole('tabpanel', { name: 'Evidence', exact: true }).waitFor()
await page.locator('.atlas__stage').scrollIntoViewIfNeeded()
await page.getByRole('button', { name: 'Fit view', exact: true }).click()
const start = Date.now(), trim = (start - created) / 1000
const until = async s => { const ms = start + s * 1000 - Date.now(); if (ms > 0) await page.waitForTimeout(ms) }
try {
  await until(8)
  await page.locator('.evidence__body').getByText(/permission|access|eligib/i).first().scrollIntoViewIfNeeded()
  await until(15)
  const contact = page.locator('.evidence__body summary').filter({ hasText: /contact/i }).first()
  if (await contact.count()) { await contact.click(); await contact.scrollIntoViewIfNeeded() }
  await until(23)
  await page.getByRole('button', { name: 'Prepare collaboration brief', exact: true }).click()
  await page.locator('.brief').getByRole('heading', { name: 'Public contact routes', exact: true }).scrollIntoViewIfNeeded()
  await until(31)
} finally {
  await context.close()
  const result = { raw_video_path: await video.path(), trim_start_seconds: trim, duration_seconds: 30,
    base_url: base, assessment_id: 'citizen-dataset-for-syngap1', mocked_responses: false, browser_errors: errors }
  await writeFile('.tools/governed-capture.json', JSON.stringify(result, null, 2) + '\n')
  await browser.close()
  console.log(JSON.stringify({ captured: errors.length === 0, browser_errors: errors }))
}
