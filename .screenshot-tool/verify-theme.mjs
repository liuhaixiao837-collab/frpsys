import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import puppeteer from 'puppeteer-core'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const token = JSON.parse(fs.readFileSync(path.resolve(ROOT, '_token.json'), 'utf-8'))
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-gpu', '--window-size=1600,900', '--lang=zh-CN'],
  defaultViewport: { width: 1600, height: 900, deviceScaleFactor: 1 },
})

try {
  const page = await browser.newPage()
  await page.goto('http://127.0.0.1:5173/login', { waitUntil: 'networkidle2' })
  await page.evaluate((t) => {
    sessionStorage.setItem('ongrid_access_token', t.access)
    localStorage.setItem('ongrid_refresh_token', t.refresh)
    localStorage.setItem('ongrid_token', t.access)
  }, token)
  await page.goto('http://127.0.0.1:5173/admin/users', { waitUntil: 'networkidle2' })
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
  await new Promise((r) => setTimeout(r, 500))
  const info = await page.evaluate(() => ({
    theme: document.documentElement.dataset.theme,
    palette: document.documentElement.dataset.palette,
    localStorageTheme: localStorage.getItem('ongrid_theme'),
  }))
  console.log(JSON.stringify(info))
} finally {
  await browser.close()
}
