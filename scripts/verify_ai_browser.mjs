/** Verify genuine current-state AI responses and brief exports through the UI. */
import assert from 'node:assert/strict'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { chromium } from '../.tools/node_modules/playwright/index.mjs'

const base = process.argv[2]
if (!base || !/^https?:\/\//.test(base)) throw new Error('Pass the app base URL as the first argument')
const output = process.argv[3] ?? 'submission/ai-browser-verification'
await mkdir(output, { recursive: true })
const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1360, height: 960 }, acceptDownloads: true })
const page = await context.newPage()
page.setDefaultTimeout(100_000)
const checks = [], errors = [], providerResults = []
page.on('pageerror', e => errors.push(e.message))
const check = (name, details = {}) => checks.push({ name, passed: true, details })
const disease = `${base.replace(/\/$/, '')}/#/disease/MONDO%3A0012960?goal=natural_history&evidence=framework-for-syngap1`
try {
  await page.goto(disease, { waitUntil: 'networkidle' })
  await page.getByRole('tabpanel', { name: 'Evidence', exact: true }).getByRole('heading', { name: 'STARR / ProMMiS natural-history framework', exact: true }).waitFor()
  await page.locator('summary').filter({ hasText: 'Plain-language explanation (AI)' }).click()
  await page.getByLabel('Your question', { exact: false }).fill('What should we ask a researcher next?')
  const firstResponse = page.waitForResponse(r => r.url().endsWith('/api/ai/ask'))
  await page.getByRole('button', { name: 'Ask the research assistant', exact: true }).click()
  const first = await (await firstResponse).json()
  assert.ok(first.answer, JSON.stringify(first.error))
  assert.ok(first.answer.response_id.startsWith('msg_'))
  providerResults.push({ operation: 'ask', mode: first.answer.generation_mode, response_id: first.answer.response_id })
  await page.locator('.ai-assistant__answer').waitFor()
  assert.match(await page.locator('.ai-assistant__answer').innerText(), /claude-sonnet-4-6/)
  assert.ok(first.answer.cited_source_ids.every(id => id === 'DOI:10.1002/epi.70374'))
  assert.ok(first.answer.check_ids.length > 0 || first.answer.evidence_state === 'insufficient_evidence')
  check('patient question displays genuine provider answer with eligible citations and recorded next questions', { generation_mode: first.answer.generation_mode, cited_source_ids: first.answer.cited_source_ids })
  await page.locator('.ai-assistant__answer').screenshot({ path: 'frontend/screenshots/integrated-ai-patient-answer.png' })

  await page.locator('.dependence').getByRole('button', { name: 'Hide', exact: true }).click()
  await page.getByText('The evidence view changed. Ask again to get an answer using the current sources.').waitFor()
  assert.equal(await page.locator('.ai-assistant__answer').count(), 0)
  await page.locator('.change-summary__item').first().waitFor()
  assert.equal(await page.locator('.change-summary__item').count(), 2)
  check('hiding a source removes old AI prose and shows two actual changed checks')

  await page.getByLabel('Your question', { exact: false }).fill('What changes if a paper is hidden?')
  const hiddenResponse = page.waitForResponse(r => r.url().endsWith('/api/ai/ask'))
  await page.getByRole('button', { name: 'Ask the research assistant', exact: true }).click()
  const hidden = await (await hiddenResponse).json()
  assert.ok(hidden.answer, JSON.stringify(hidden.error))
  assert.deepEqual(hidden.withdrawn_source_ids, ['DOI:10.1002/epi.70374'])
  assert.deepEqual(hidden.answer.cited_source_ids, [])
  providerResults.push({ operation: 'ask-withdrawn', mode: hidden.answer.generation_mode, response_id: hidden.answer.response_id })
  await page.locator('.ai-assistant__answer').waitFor()
  check('new answer uses current hidden-source state and cites no hidden paper', { generation_mode: hidden.answer.generation_mode })
  await page.locator('.ai-assistant__answer').screenshot({ path: 'frontend/screenshots/integrated-ai-hidden-answer.png' })

  await page.getByRole('button', { name: 'Doctor / expert', exact: true }).click()
  assert.equal(await page.locator('.ai-assistant__answer').count(), 0)
  check('switching reading mode invalidates the old answer')
  await page.getByRole('button', { name: 'Patient / simple', exact: true }).click()
  await page.getByRole('button', { name: 'Prepare collaboration brief', exact: true }).click()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download as text', exact: true }).click()
  const download = await downloadPromise
  const exportPath = `${output}/hidden-source-brief.txt`
  await download.saveAs(exportPath)
  const text = await readFile(exportPath, 'utf8')
  assert.match(text, /DOI:10\.1002\/epi\.70374/)
  assert.match(text, /hidden/i)
  assert.match(text, /Information missing|unknown/i)
  check('downloaded brief retains current missing checks and hidden canonical source')
  await page.emulateMedia({ media: 'print' })
  await page.pdf({ path: `${output}/hidden-source-brief.pdf`, format: 'A4', printBackground: true })
  check('Chromium generates the actual print-layout PDF', { scope: 'Headless PDF output; OS print dialog was not tested' })
  await page.emulateMedia({ media: 'screen' })
  await page.getByRole('button', { name: 'Close', exact: true }).click()
  await page.locator('.dependence').getByRole('button', { name: 'Show again', exact: true }).click()
  await page.waitForFunction(() => document.querySelectorAll('.change-summary__item').length === 0)
  check('reset restores evidence and keeps the assistant state tied to its request key')

  const discoveryResponse = page.waitForResponse(r => r.url().endsWith('/api/ai/discover'))
  await page.getByRole('button', { name: 'Find research leads', exact: true }).click()
  const discovery = await (await discoveryResponse).json()
  assert.ok(discovery.discovery, JSON.stringify(discovery.error))
  assert.ok(discovery.discovery.response_id.startsWith('msg_'))
  assert.ok(discovery.discovery.hypotheses.length > 0)
  assert.ok(discovery.discovery.hypotheses.every(h => h.claim_origin === 'inferred' && h.review_status === 'pending'))
  providerResults.push({ operation: 'discover', mode: discovery.discovery.generation_mode, response_id: discovery.discovery.response_id })
  await page.locator('.research-lead').first().waitFor()
  check('model-generated research leads render sources, unresolved questions and pending inference labels', { hypotheses: discovery.discovery.hypotheses.length, generation_mode: discovery.discovery.generation_mode })
  await page.locator('.research-leads').screenshot({ path: 'frontend/screenshots/integrated-ai-research-leads.png' })
  await page.locator('.dependence').getByRole('button', { name: 'Hide', exact: true }).click()
  assert.equal(await page.locator('.research-lead').count(), 0)
  assert.ok(await page.getByRole('button', { name: 'Review leads again', exact: true }).count() === 0)
  assert.ok(await page.getByRole('button', { name: 'Find research leads', exact: true }).isDisabled())
  check('full-registry scout prose is hidden during the source-withdrawn inspection')
  assert.deepEqual(errors, [])
} finally {
  const report = { checked_at: new Date().toISOString(), base_url: base, passed: checks.length === 9 && errors.length === 0,
    checks, browser_errors: errors, genuine_provider_results: providerResults,
    limits: [base.startsWith('https://') ? 'Public browser journey was checked without Vercel authentication.' : 'Local production browser verification does not prove public hosting.', 'Generation/citation checks do not establish biomedical truth.', 'Headless PDF generation does not test a real OS print dialog.'] }
  await writeFile(`${output}/report.json`, JSON.stringify(report, null, 2) + '\n')
  await context.close()
  await browser.close()
  console.log(JSON.stringify(report, null, 2))
}
