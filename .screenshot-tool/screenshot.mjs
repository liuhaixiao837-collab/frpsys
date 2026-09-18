import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import puppeteer from 'puppeteer-core'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const token = JSON.parse(fs.readFileSync(path.resolve(ROOT, '_token.json'), 'utf-8'))
const OUT = path.join(ROOT, 'docs', 'images')

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'

const TARGETS = [
  { url: 'http://127.0.0.1:5173/security/frp/servers', file: '02-frp-servers.png', wait: 3500 },
  { url: 'http://127.0.0.1:5173/security/frp/agents', file: '03-frp-agents.png', wait: 3500 },
  { url: 'http://127.0.0.1:5173/security/frp/proxies', file: '04-frp-proxies.png', wait: 3500 },
  { url: 'http://127.0.0.1:5173/security/frp/audits', file: '05-frp-audits.png', wait: 3500 },
  { url: 'http://127.0.0.1:5173/security/frp/reports', file: '06-frp-reports.png', wait: 3500 },
  { url: 'http://127.0.0.1:5173/security/frp/traffic-reports', file: '07-frp-traffic.png', wait: 3500 },
  { url: 'http://127.0.0.1:5173/admin/users', file: '08-user-management.png', wait: 3500 },
  { url: 'http://127.0.0.1:5173/settings', file: '09-platform-settings.png', wait: 3500 },
  { url: 'http://127.0.0.1:5173/logs/users', file: '10-user-logs.png', wait: 3500 },
  { url: 'http://127.0.0.1:5173/logs/system', file: '11-system-logs.png', wait: 3500 },
]

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-gpu', '--window-size=1600,900', '--lang=zh-CN'],
  defaultViewport: { width: 1600, height: 900, deviceScaleFactor: 1.5 },
})

try {
  const page = await browser.newPage()

  // 注入令牌
  await page.goto('http://127.0.0.1:5173/login', { waitUntil: 'networkidle2', timeout: 30000 })
  await page.evaluate((t) => {
    sessionStorage.setItem('ongrid_access_token', t.access)
    localStorage.setItem('ongrid_refresh_token', t.refresh)
    localStorage.setItem('ongrid_token', t.access)
  }, token)

  // 先进入一个有顶部操作栏的页面，切换到「天青白」主题
  await page.goto('http://127.0.0.1:5173/admin/users', { waitUntil: 'networkidle2', timeout: 30000 })
  await page.waitForSelector('button.theme-picker-trigger', { timeout: 10000 })
  await page.click('button.theme-picker-trigger')
  await page.waitForSelector('button.theme-option', { visible: true, timeout: 10000 })
  const options = await page.$$('button.theme-option')
  for (const option of options) {
    const text = await page.evaluate((el) => el.textContent, option)
    if (text.includes('天青白')) {
      await option.click()
      break
    }
  }
  await new Promise((r) => setTimeout(r, 800)) // 等待主题切换动画
  await page.screenshot({ path: path.join(OUT, '08-user-management.png') })
  console.log('saved 08-user-management.png')

  // 其余页面直接跳转截图（主题已全局生效）
  for (const target of TARGETS) {
    if (target.file === '08-user-management.png') continue
    await page.goto(target.url, { waitUntil: 'networkidle2', timeout: 30000 })
    await new Promise((r) => setTimeout(r, target.wait))
    await page.screenshot({ path: path.join(OUT, target.file) })
    console.log('saved', target.file)
  }
} finally {
  await browser.close()
}
