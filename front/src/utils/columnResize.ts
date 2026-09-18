const HANDLE_CLASS = 'column-resize-handle'
const MIN_COLUMN_WIDTH = 56

type ResizeState = {
  startX: number
  widths: number[]
  columnIndex: number
}

let observer: MutationObserver | null = null
let scanFrame = 0
const gridWidths = new WeakMap<HTMLElement, number[]>()

/**
 * 封装 clampPair 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`left` 表示该步骤所需的业务参数；`right` 表示该步骤所需的业务参数；`delta` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function clampPair(left: number, right: number, delta: number) {
  const safeDelta = Math.max(MIN_COLUMN_WIDTH - left, Math.min(delta, right - MIN_COLUMN_WIDTH))
  return [left + safeDelta, right - safeDelta] as const
}

/**
 * 启动表格相邻列的指针拖拽调整并注册结束清理逻辑。
 * 参数：`event` 表示该步骤所需的业务参数；`columnIndex` 表示该步骤所需的业务参数；`widths` 表示该步骤所需的业务参数；`apply` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function beginPointerResize(
  event: PointerEvent,
  columnIndex: number,
  widths: number[],
  apply: (widths: number[]) => void,
) {
  event.preventDefault()
  event.stopPropagation()

  const state: ResizeState = {
    startX: event.clientX,
    widths,
    columnIndex,
  }

    /**
   * 封装 move 对应的前端业务处理步骤，供当前模块统一调用。
   * 参数：`moveEvent` 表示该步骤所需的业务参数。
   * 返回：无显式返回值。
   * 副作用：不直接修改持久化数据。
   */
const move = (moveEvent: PointerEvent) => {
    const nextWidths = [...state.widths]
    const [left, right] = clampPair(
      state.widths[state.columnIndex],
      state.widths[state.columnIndex + 1],
      moveEvent.clientX - state.startX,
    )
    nextWidths[state.columnIndex] = left
    nextWidths[state.columnIndex + 1] = right
    apply(nextWidths)
  }

    /**
   * 封装 finish 对应的前端业务处理步骤，供当前模块统一调用。
   * 参数：无。
   * 返回：无显式返回值。
   * 副作用：不直接修改持久化数据。
   */
const finish = () => {
    document.documentElement.classList.remove('is-resizing-columns')
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', finish)
    window.removeEventListener('pointercancel', finish)
  }

  document.documentElement.classList.add('is-resizing-columns')
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', finish, { once: true })
  window.addEventListener('pointercancel', finish, { once: true })
}

/**
 * 创建表格列宽拖拽手柄并设置无障碍说明。
 * 参数：`label` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
function createHandle(label: string) {
  const handle = document.createElement('span')
  handle.className = HANDLE_CLASS
  handle.role = 'separator'
  handle.tabIndex = 0
  handle.setAttribute('aria-orientation', 'vertical')
  handle.setAttribute('aria-label', `调整${label || '当前'}列宽`)
  handle.title = '左右拖动调整列宽，双击恢复默认宽度'
  return handle
}

/**
 * 为原生表格安装列宽拖拽、双击复位和稳定布局。
 * 参数：`table` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function setupHtmlTable(table: HTMLTableElement) {
  const headerRow = table.tHead?.rows.item(table.tHead.rows.length - 1)
  const headers = headerRow ? Array.from(headerRow.cells) : []
  if (headers.length < 2) return
  if (
    table.dataset.columnResizeReady === '1'
    && headerRow?.querySelectorAll(`.${HANDLE_CLASS}`).length === headers.length - 1
  ) return

  table.dataset.columnResizeReady = '1'
  table.classList.add('column-resizable-table')
  headerRow?.querySelectorAll(`.${HANDLE_CLASS}`).forEach((handle) => handle.remove())

    /**
   * 计算并返回 currentWidths 对应的业务数据。
   * 参数：无。
   * 返回：无显式返回值。
   * 副作用：不直接修改持久化数据。
   */
const currentWidths = () => headers.map((header) => header.getBoundingClientRect().width)
    /**
   * 封装 applyWidths 对应的前端业务处理步骤，供当前模块统一调用。
   * 参数：`widths` 表示该步骤所需的业务参数。
   * 返回：无显式返回值。
   * 副作用：不直接修改持久化数据。
   */
const applyWidths = (widths: number[]) => {
    table.style.tableLayout = 'fixed'
    headers.forEach((header, index) => {
      header.style.width = `${widths[index]}px`
      header.style.minWidth = `${MIN_COLUMN_WIDTH}px`
      header.style.maxWidth = 'none'
    })
  }
    /**
   * 将 reset 管理的界面或业务状态恢复到初始值。
   * 参数：无。
   * 返回：无显式返回值。
   * 副作用：可能修改当前组件状态、定时器或页面元素。
   */
const reset = () => {
    table.style.removeProperty('table-layout')
    headers.forEach((header) => {
      header.style.removeProperty('width')
      header.style.removeProperty('min-width')
      header.style.removeProperty('max-width')
    })
  }

  headers.slice(0, -1).forEach((header, columnIndex) => {
    const handle = createHandle(header.textContent?.trim() || '')
    handle.addEventListener('pointerdown', (event) => {
      const widths = currentWidths()
      applyWidths(widths)
      beginPointerResize(event, columnIndex, widths, applyWidths)
    })
    handle.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
      event.preventDefault()
      const widths = currentWidths()
      const delta = (event.key === 'ArrowRight' ? 1 : -1) * (event.shiftKey ? 32 : 12)
      const [left, right] = clampPair(widths[columnIndex], widths[columnIndex + 1], delta)
      widths[columnIndex] = left
      widths[columnIndex + 1] = right
      applyWidths(widths)
    })
    handle.addEventListener('dblclick', reset)
    header.append(handle)
  })
}

/**
 * 为网格形式的数据列表安装列宽拖拽和复位行为。
 * 参数：`table` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function setupGridTable(table: HTMLElement) {
  const rowSelector = table.classList.contains('member-table') ? '.member-table-row' : '.governance-table-row'
  const headerRow = table.querySelector<HTMLElement>(`:scope > ${rowSelector}.table-head`)
  if (!headerRow) return
  const headers = Array.from(headerRow.children).filter((item): item is HTMLElement => item instanceof HTMLElement)
  if (headers.length < 2) return

    /**
   * 封装 rows 对应的前端业务处理步骤，供当前模块统一调用。
   * 参数：无。
   * 返回：无显式返回值。
   * 副作用：不直接修改持久化数据。
   */
const rows = () => Array.from(table.querySelectorAll<HTMLElement>(`:scope > ${rowSelector}`))
    /**
   * 封装 applyWidths 对应的前端业务处理步骤，供当前模块统一调用。
   * 参数：`widths` 表示该步骤所需的业务参数。
   * 返回：无显式返回值。
   * 副作用：不直接修改持久化数据。
   */
const applyWidths = (widths: number[]) => {
    gridWidths.set(table, widths)
    const template = widths.map((width) => `${width}px`).join(' ')
    rows().forEach((row) => {
      row.style.gridTemplateColumns = template
    })
  }
  const savedWidths = gridWidths.get(table)
  if (savedWidths) applyWidths(savedWidths)
  if (
    table.dataset.columnResizeReady === '1'
    && headerRow.querySelectorAll(`.${HANDLE_CLASS}`).length === headers.length - 1
  ) return

  table.dataset.columnResizeReady = '1'
  table.classList.add('column-resizable-grid')
  headerRow.querySelectorAll(`.${HANDLE_CLASS}`).forEach((handle) => handle.remove())

    /**
   * 计算并返回 currentWidths 对应的业务数据。
   * 参数：无。
   * 返回：无显式返回值。
   * 副作用：不直接修改持久化数据。
   */
const currentWidths = () => headers.map((header) => header.getBoundingClientRect().width)
    /**
   * 将 reset 管理的界面或业务状态恢复到初始值。
   * 参数：无。
   * 返回：无显式返回值。
   * 副作用：可能修改当前组件状态、定时器或页面元素。
   */
const reset = () => {
    gridWidths.delete(table)
    rows().forEach((row) => row.style.removeProperty('grid-template-columns'))
  }

  headers.slice(0, -1).forEach((header, columnIndex) => {
    const handle = createHandle(header.textContent?.trim() || '')
    handle.addEventListener('pointerdown', (event) => {
      const widths = currentWidths()
      applyWidths(widths)
      beginPointerResize(event, columnIndex, widths, applyWidths)
    })
    handle.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
      event.preventDefault()
      const widths = currentWidths()
      const delta = (event.key === 'ArrowRight' ? 1 : -1) * (event.shiftKey ? 32 : 12)
      const [left, right] = clampPair(widths[columnIndex], widths[columnIndex + 1], delta)
      widths[columnIndex] = left
      widths[columnIndex + 1] = right
      applyWidths(widths)
    })
    handle.addEventListener('dblclick', reset)
    header.append(handle)
  })
}

/**
 * 扫描当前页面中新出现的数据表格并安装列宽调整能力。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function scanTables() {
  document.querySelectorAll<HTMLTableElement>('table').forEach(setupHtmlTable)
  document.querySelectorAll<HTMLElement>('.governance-table, .member-table').forEach(setupGridTable)
}

/**
 * 合并短时间内的表格扫描请求，避免重复执行布局计算。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function scheduleScan() {
  if (scanFrame) return
  scanFrame = requestAnimationFrame(() => {
    scanFrame = 0
    scanTables()
  })
}

/**
 * 封装 installColumnResizing 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
export function installColumnResizing() {
  if (observer) return
  scanTables()
  observer = new MutationObserver(scheduleScan)
  observer.observe(document.body, { childList: true, subtree: true })
}
