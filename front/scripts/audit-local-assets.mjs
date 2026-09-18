import { readdir, readFile } from 'node:fs/promises'
import { extname, join, relative } from 'node:path'

const root = new URL('..', import.meta.url)
const scanRoots = ['src', 'index.html']
const sourceExtensions = new Set(['.css', '.html', '.js', '.ts', '.vue'])
const forbiddenPatterns = [
  /(?:src|href)\s*=\s*["']https?:\/\//gi,
  /url\(\s*["']?https?:\/\//gi,
  /@import\s+(?:url\()?\s*["']?https?:\/\//gi,
  /(?:from|import)\s*["']https?:\/\//gi,
]

async function filesAt(path) {
  const absolute = new URL(path, root)
  if (extname(path)) return [absolute]
  const entries = await readdir(absolute, { withFileTypes: true })
  const nested = await Promise.all(entries.map((entry) => filesAt(join(path, entry.name))))
  return nested.flat()
}

const files = (await Promise.all(scanRoots.map(filesAt))).flat()
  .filter((file) => sourceExtensions.has(extname(file.pathname)))
const violations = []

for (const file of files) {
  const source = await readFile(file, 'utf8')
  for (const pattern of forbiddenPatterns) {
    pattern.lastIndex = 0
    for (const match of source.matchAll(pattern)) {
      const line = source.slice(0, match.index).split(/\r?\n/).length
      violations.push(`${relative(new URL('.', root).pathname, file.pathname)}:${line} ${match[0]}`)
    }
  }
}

if (violations.length) {
  console.error('发现前端外网资源引用：')
  for (const violation of violations) console.error(`- ${violation}`)
  process.exit(1)
}

console.log(`本地资源审计通过：已检查 ${files.length} 个前端源码文件。`)

