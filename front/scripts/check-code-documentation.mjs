import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

import { parse as parseVue } from '@vue/compiler-sfc'
import ts from 'typescript'


const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const sourceRoot = path.join(projectRoot, 'src')
const fixMode = process.argv.includes('--fix')

const exactDescriptions = {
  bootstrap: '加载数据库导航并完成前端路由、权限状态和应用实例初始化。',
  refreshAccessToken: '使用刷新令牌换取新的访问令牌，并同步更新本地登录状态。',
  formatError: '将接口错误结构转换为用户可理解的中文提示。',
  registerPath: '登记数据库页面路由、权限代码和上级权限链的对应关系。',
  walkPages: '递归遍历数据库返回的页面节点并执行指定访问函数。',
  beginPointerResize: '启动表格相邻列的指针拖拽调整并注册结束清理逻辑。',
  createHandle: '创建表格列宽拖拽手柄并设置无障碍说明。',
  setupHtmlTable: '为原生表格安装列宽拖拽、双击复位和稳定布局。',
  setupGridTable: '为网格形式的数据列表安装列宽拖拽和复位行为。',
  scanTables: '扫描当前页面中新出现的数据表格并安装列宽调整能力。',
  scheduleScan: '合并短时间内的表格扫描请求，避免重复执行布局计算。',
  sendCommandAudit: '将终端中完成输入的命令发送到后端命令审计接口。',
  trackTerminalInput: '跟踪终端键盘输入并识别需要提交审计的完整命令。',
  sendTerminalData: '向当前 WebSocket 终端连接发送用户输入数据。',
  playGuacamoleRecording: '加载并播放 Guacamole 服务端生成的 RDP 录像。',
  renderSshToPosition: '将 SSH 终端回放事件重新渲染到指定时间位置。',
  actionCode: '根据页面权限代码和操作代码生成完整操作权限代码。',
  resetRuleState: '以默认拒绝为基础重建权限策略编辑状态。',
  setPageWithActions: '同步设置页面访问权限及页面全部真实操作权限。',
  setGroupWithChildren: '同步设置菜单组及其全部页面和操作权限。',
  detailValue: '将审计详情值转换为安全且用户友好的展示文字。',
  queryString: '根据当前筛选条件生成接口查询字符串。',
  wsUrl: '根据当前协议和令牌生成堡垒机 WebSocket 地址。',
}

function purposeFor(name) {
  /**
   * 根据函数名称生成中文用途说明，并优先使用人工维护的业务说明。
   * 参数：`name` 表示函数名称。
   * 返回：返回中文用途说明。
   * 副作用：不修改文件或运行状态。
   */
  if (exactDescriptions[name]) return exactDescriptions[name]
  if (/^(get|current|first|collect|find|lookup)/.test(name)) return `计算并返回 ${name} 对应的业务数据。`
  if (/^(is|can|has|should)/.test(name)) return `判断 ${name} 对应的业务条件是否成立。`
  if (/^(load|fetch|refresh)/.test(name)) return `从后端或当前状态加载 ${name} 所需的最新业务数据。`
  if (/^(save|create|add|upload|submit)/.test(name)) return `校验当前输入并完成 ${name} 对应的数据保存操作。`
  if (/^(delete|remove|clear|cleanup)/.test(name)) return `执行 ${name} 对应的清理或删除操作并同步页面状态。`
  if (/^(open|show|reveal)/.test(name)) return `准备 ${name} 所需数据并打开对应交互界面。`
  if (/^(close|hide|disconnect)/.test(name)) return `关闭 ${name} 对应的界面或连接并清理临时状态。`
  if (/^(reset|restore)/.test(name)) return `将 ${name} 管理的界面或业务状态恢复到初始值。`
  if (/^(toggle|switch)/.test(name)) return `切换 ${name} 对应的界面或业务状态。`
  if (/^(format|label|display|text)/.test(name)) return `将业务值转换为 ${name} 对应的用户友好文字。`
  if (/^(build|make|payload)/.test(name)) return `组装 ${name} 对应的接口或界面数据结构。`
  if (/^(handle|on)/.test(name)) return `处理 ${name} 对应的用户操作或系统事件。`
  if (/^(render|mount|resize|fit|sync|update)/.test(name)) return `更新 ${name} 对应的界面内容、尺寸或同步状态。`
  if (/^(play|pause|seek|start|stop)/.test(name)) return `控制 ${name} 对应的会话回放或计时流程。`
  if (/^(ask|confirm)/.test(name)) return `处理 ${name} 对应的确认交互，并在确认后执行目标操作。`
  if (/^(validate|normalize|parse)/.test(name)) return `校验并规范化 ${name} 对应的输入数据。`
  return `封装 ${name} 对应的前端业务处理步骤，供当前模块统一调用。`
}

function parameterText(node, sourceFile) {
  /**
   * 从 TypeScript 函数签名提取参数名称并生成中文参数说明。
   * 参数：`node` 表示函数语法节点；`sourceFile` 表示所属源码节点。
   * 返回：返回中文参数说明文字。
   * 副作用：不修改文件或运行状态。
   */
  const parameters = node.parameters.map((parameter) => parameter.name.getText(sourceFile))
  if (!parameters.length) return '参数：无。'
  return `参数：${parameters.map((name) => `\`${name}\` 表示该步骤所需的业务参数`).join('；')}。`
}

function hasValueReturn(node) {
  /**
   * 判断函数自身控制流中是否存在带值返回，跳过内部函数作用域。
   * 参数：`node` 表示待检查的函数节点。
   * 返回：存在带值返回时返回真。
   * 副作用：不修改文件或运行状态。
   */
  let found = false
  const visit = (child) => {
    if (found) return
    if (child !== node && ts.isFunctionLike(child)) return
    if (ts.isReturnStatement(child) && child.expression) {
      found = true
      return
    }
    ts.forEachChild(child, visit)
  }
  ts.forEachChild(node, visit)
  return found
}

function sideEffectText(name) {
  /**
   * 根据函数命名约定生成保守的中文副作用说明。
   * 参数：`name` 表示函数名称。
   * 返回：返回中文副作用说明。
   * 副作用：不修改文件或运行状态。
   */
  if (/^(load|fetch|refresh|save|create|delete|remove|upload|download|connect|disconnect|send|submit|confirm)/.test(name)) {
    return '副作用：可能请求后端、修改持久化数据或更新全局状态。'
  }
  if (/^(open|close|toggle|reset|render|mount|resize|fit|sync|update|play|pause|seek|start|stop|handle|on)/.test(name)) {
    return '副作用：可能修改当前组件状态、定时器或页面元素。'
  }
  return '副作用：不直接修改持久化数据。'
}

function documentationFor(name, node, sourceFile, indent) {
  /**
   * 为一个前端函数生成包含用途、参数、返回值和副作用的中文 JSDoc。
   * 参数：`name` 表示函数名称；`node` 表示函数节点；`sourceFile` 表示源码；`indent` 表示缩进。
   * 返回：返回可插入源码的完整说明块。
   * 副作用：不修改文件或运行状态。
   */
  const result = hasValueReturn(node) ? '返回：返回该步骤计算、查询或校验后的结果。' : '返回：无显式返回值。'
  return [
    `${indent}/**`,
    `${indent} * ${purposeFor(name)}`,
    `${indent} * ${parameterText(node, sourceFile)}`,
    `${indent} * ${result}`,
    `${indent} * ${sideEffectText(name)}`,
    `${indent} */`,
    '',
  ].join('\n')
}

function targetForNode(node) {
  /**
   * 将 TypeScript 语法节点转换为需要检查的具名函数目标。
   * 参数：`node` 表示待识别的语法节点。
   * 返回：返回函数名称、函数节点和说明插入节点；非目标返回空值。
   * 副作用：不修改文件或运行状态。
   */
  if (ts.isFunctionDeclaration(node) && node.name && node.body) {
    return { name: node.name.text, functionNode: node, insertionNode: node }
  }
  if (ts.isVariableStatement(node)) {
    const declaration = node.declarationList.declarations.find((item) =>
      ts.isIdentifier(item.name) && item.initializer
      && (ts.isArrowFunction(item.initializer) || ts.isFunctionExpression(item.initializer)))
    if (declaration) {
      return { name: declaration.name.text, functionNode: declaration.initializer, insertionNode: node }
    }
  }
  if (ts.isMethodDeclaration(node) && node.name && node.body) {
    return { name: node.name.getText(), functionNode: node, insertionNode: node }
  }
  return null
}

function collectTargets(source, filename) {
  /**
   * 解析一段 TypeScript 源码并收集全部具名函数及其中文说明状态。
   * 参数：`source` 表示 TypeScript 源码；`filename` 表示用于解析模式判断的文件名。
   * 返回：返回具名函数检查目标列表。
   * 副作用：不修改文件或运行状态。
   */
  const sourceFile = ts.createSourceFile(
    filename,
    source,
    ts.ScriptTarget.Latest,
    true,
    filename.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  )
  const targets = []
  const visit = (node) => {
    const target = targetForNode(node)
    if (target) {
      const start = target.insertionNode.getStart(sourceFile)
      const fullStart = target.insertionNode.getFullStart()
      const leading = source.slice(fullStart, start)
      const lineStart = source.lastIndexOf('\n', start - 1) + 1
      const indent = source.slice(lineStart, start).match(/^\s*/)?.[0] || ''
      targets.push({ ...target, sourceFile, start, indent, documented: /\/\*\*[\s\S]*[\u4e00-\u9fff][\s\S]*\*\//.test(leading) })
    }
    ts.forEachChild(node, visit)
  }
  visit(sourceFile)
  return targets
}

function sourceFiles(directory) {
  /**
   * 递归枚举前端维护范围内的 TypeScript 和 Vue 源文件。
   * 参数：`directory` 表示待扫描目录。
   * 返回：返回源文件绝对路径列表。
   * 副作用：只读取目录，不修改文件。
   */
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const resolved = path.join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(resolved)
    return /\.(ts|tsx|vue)$/.test(entry.name) ? [resolved] : []
  })
}

function scriptRegion(filename, source) {
  /**
   * 返回普通 TypeScript 文件或 Vue 脚本块的内容和原文件偏移。
   * 参数：`filename` 表示文件名；`source` 表示完整文件内容。
   * 返回：返回可解析脚本内容及其在原文件中的起始位置。
   * 副作用：不修改文件或运行状态。
   */
  if (!filename.endsWith('.vue')) return { content: source, offset: 0 }
  const descriptor = parseVue(source, { filename }).descriptor
  const block = descriptor.scriptSetup || descriptor.script
  if (!block) return { content: '', offset: 0 }
  return { content: block.content, offset: source.indexOf(block.content) }
}

function inspectFile(filename) {
  /**
   * 检查单个前端源码文件，并在修复模式下补齐缺失中文说明。
   * 参数：`filename` 表示待检查文件路径。
   * 返回：返回该文件仍存在的说明问题列表。
   * 副作用：修复模式下会写回源码文件。
   */
  let source = fs.readFileSync(filename, 'utf8')
  const region = scriptRegion(filename, source)
  if (!region.content) return []
  const targets = collectTargets(region.content, filename)
  const missing = targets.filter((target) => !target.documented)
  if (fixMode && missing.length) {
    const edits = missing.map((target) => ({
      position: region.offset + target.start,
      text: documentationFor(target.name, target.functionNode, target.sourceFile, target.indent),
    }))
    for (const edit of edits.sort((left, right) => right.position - left.position)) {
      source = source.slice(0, edit.position) + edit.text + source.slice(edit.position)
    }
    fs.writeFileSync(filename, source, 'utf8')
    return []
  }
  return missing.map((target) => `${path.relative(projectRoot, filename)}：函数 ${target.name} 缺少中文 JSDoc`)
}

const issues = sourceFiles(sourceRoot).flatMap(inspectFile)
if (issues.length) {
  console.error('前端中文函数说明检查失败：')
  for (const issue of issues) console.error(`- ${issue}`)
  process.exit(1)
}
console.log(fixMode ? '前端中文函数说明已补齐。' : '前端中文函数说明检查通过。')
