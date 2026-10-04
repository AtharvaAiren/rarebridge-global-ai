/** Create code-rendered title/credit cards using the supplied RareBridge brand. */
import { readFile, mkdir } from 'node:fs/promises'
import { chromium } from '../.tools/node_modules/playwright/index.mjs'
const content = JSON.parse(await readFile('submission/team-video/CONTENT.json', 'utf8'))
const logo = (await readFile('frontend/src/assets/brand/wordmark-dark.png')).toString('base64')
const token = await readFile('frontend/src/styles/token.css', 'utf8')
const html = await readFile('frontend/dist/index.html', 'utf8')
const css = html.match(/href="([^\"]+\.css)"/)?.[1]
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;')
await mkdir('.tools/team-cards', { recursive: true })
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
for (const card of content.cards) {
  await page.setContent(`<!doctype html><html><head>${css ? `<link rel="stylesheet" href="${content.public_demo_url}${css}">` : ''}
  <style>${token}
  *{box-sizing:border-box}body{margin:0;background:#09111f;color:#edf4f9;font-family:Lexend,system-ui,sans-serif}
  main{height:1000px;padding:90px 100px;display:flex;flex-direction:column;justify-content:space-between;background:radial-gradient(ellipse at 95% 10%,#18394b 0,transparent 60%)}
  img{width:270px;height:auto}small{font-size:20px;color:#a7bccb}h1{color:#edf4f9;font:64px/1.13 'Source Serif 4',Georgia,serif;font-weight:600;max-width:1100px;margin:38px 0 26px}
  .subtitle{font-size:29px;line-height:1.5;color:#ffd217;max-width:1080px}ul{list-style:none;padding:0;font-size:24px;line-height:1.8;color:#d3e0eb}li{margin:8px 0}
  footer{border-top:1px solid #456071;padding-top:28px;display:grid;gap:13px;font-size:18px}.disclosure{color:#a7bccb;font-size:15px}
  </style></head><body><main><div><img src="data:image/png;base64,${logo}" alt="RareBridge"><h1>${escape(card.title)}</h1><p class="subtitle">${escape(card.subtitle)}</p><ul>${card.body.map(line => `<li>${escape(line)}</li>`).join('')}</ul></div>
  <footer><div>${escape(card.footer)}</div><div>${escape(content.public_demo_url)}</div><div>${escape(content.source_repository_url)}</div><div class="disclosure">Real product footage · synthesized narration · research planning, with expert review required</div></footer></main></body></html>`)
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: `.tools/team-cards/${card.id}.png` })
}
await browser.close()
console.log('Three branded title/credit cards rendered; no generated patient or team imagery.')
