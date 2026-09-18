import { clearTokens, getAccessToken, getRefreshToken, setTokens } from './authStorage'

const BASE = import.meta.env.VITE_API_BASE || '/api/v1'

type ApiOptions = RequestInit & { skipAuth?: boolean; retried?: boolean }
type StreamOptions = ApiOptions & { payload?: any; onEvent?: (event: string, data: any) => void }

/**
 * 使用刷新令牌换取新的访问令牌，并同步更新本地登录状态。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function refreshAccessToken() {
  const refresh = getRefreshToken()
  if (!refresh) return false
  const response = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok || !data.access) {
    clearTokens()
    return false
  }
  setTokens(data.access, data.refresh)
  return true
}

/**
 * 判断 isHeaderTooLarge 对应的业务条件是否成立。
 * 参数：`status` 表示该步骤所需的业务参数；`data` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function isHeaderTooLarge(status: number, data: any) {
  const detail = typeof data?.detail === 'string' ? data.detail : ''
  return status === 431 || detail.includes('431')
}

/**
 * 封装 api 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`path` 表示该步骤所需的业务参数；`options` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export async function api(path: string, options: ApiOptions = {}): Promise<any> {
  const token = getAccessToken() || localStorage.getItem('ongrid_token')
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      ...(!options.skipAuth && token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  })
  const data = await response.json().catch(() => ({}))

  if (isHeaderTooLarge(response.status, data) && !options.skipAuth && !options.retried && await refreshAccessToken()) {
    return api(path, { ...options, retried: true })
  }
  if (isHeaderTooLarge(response.status, data) && !options.skipAuth && !options.retried) {
    clearTokens()
    if (location.pathname !== '/login') location.href = '/login'
  }
  if (shouldRefresh(response.status, data) && !options.skipAuth && !options.retried && await refreshAccessToken()) {
    return api(path, { ...options, retried: true })
  }
  if (shouldRefresh(response.status, data) && !options.skipAuth && !options.retried) {
    clearTokens()
    if (location.pathname !== '/login') location.href = '/login'
  }
  if (!response.ok) throw new Error(formatError(data.detail || data) || `请求失败 (${response.status})`)
  return data
}

/**
 * 封装 apiForm 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`path` 表示该步骤所需的业务参数；`formData` 表示该步骤所需的业务参数；`options` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export async function apiForm(path: string, formData: FormData, options: ApiOptions = {}): Promise<any> {
  const token = getAccessToken() || localStorage.getItem('ongrid_token')
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    method: options.method || 'POST',
    body: formData,
    headers: {
      ...(!options.skipAuth && token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  })
  const data = await response.json().catch(() => ({}))
  if (isHeaderTooLarge(response.status, data) && !options.skipAuth && !options.retried && await refreshAccessToken()) {
    return apiForm(path, formData, { ...options, retried: true })
  }
  if (isHeaderTooLarge(response.status, data) && !options.skipAuth && !options.retried) {
    clearTokens()
    if (location.pathname !== '/login') location.href = '/login'
  }
  if (shouldRefresh(response.status, data) && !options.skipAuth && !options.retried && await refreshAccessToken()) {
    return apiForm(path, formData, { ...options, retried: true })
  }
  if (shouldRefresh(response.status, data) && !options.skipAuth && !options.retried) {
    clearTokens()
    if (location.pathname !== '/login') location.href = '/login'
  }
  if (!response.ok) throw new Error(formatError(data.detail || data) || `请求失败 (${response.status})`)
  return data
}

/**
 * 封装 apiStream 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`path` 表示该步骤所需的业务参数；`options` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export async function apiStream(path: string, options: StreamOptions = {}): Promise<any> {
  const token = getAccessToken() || localStorage.getItem('ongrid_token')
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    method: options.method || 'POST',
    body: options.body || JSON.stringify(options.payload || {}),
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      Accept: 'text/event-stream, application/json',
      ...(!options.skipAuth && token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  })
  if (shouldRefresh(response.status, {}) && !options.skipAuth && !options.retried && await refreshAccessToken()) {
    return apiStream(path, { ...options, retried: true })
  }
  if (!response.ok || !response.body) {
    const data = await response.json().catch(() => ({}))
    if (shouldRefresh(response.status, data) && !options.skipAuth && !options.retried && await refreshAccessToken()) {
      return apiStream(path, { ...options, retried: true })
    }
    if (shouldRefresh(response.status, data) && !options.skipAuth && !options.retried) {
      clearTokens()
      if (location.pathname !== '/login') location.href = '/login'
    }
    throw new Error(formatError(data.detail || data) || `请求失败 (${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalPayload: any = null

    /**
   * 处理 handleBlock 对应的用户操作或系统事件。
   * 参数：`block` 表示该步骤所需的业务参数。
   * 返回：无显式返回值。
   * 副作用：可能修改当前组件状态、定时器或页面元素。
   */
function handleBlock(block: string) {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    if (!dataLines.length) return
    const rawData = dataLines.join('\n')
    const data = JSON.parse(rawData)
    options.onEvent?.(event, data)
    if (event === 'done') finalPayload = data
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      if (block.trim()) handleBlock(block)
    }
    if (done) break
  }
  if (buffer.trim()) handleBlock(buffer)
  return finalPayload
}

/**
 * 封装 downloadFile 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`path` 表示该步骤所需的业务参数；`fallbackName` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
export async function downloadFile(path: string, fallbackName: string) {
  const token = getAccessToken() || localStorage.getItem('ongrid_token')
  const response = await fetch(`${BASE}${path}`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  if (!response.ok) throw new Error(`文件下载失败 (${response.status})`)
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?([^"]+)"?/i)
  const fileName = decodeURIComponent(match?.[1] || fallbackName)
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/**
 * 判断 shouldRefresh 对应的业务条件是否成立。
 * 参数：`status` 表示该步骤所需的业务参数；`data` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function shouldRefresh(status: number, data: any) {
  const detail = typeof data?.detail === 'string' ? data.detail : ''
  return status === 401 || (status === 403 && detail.includes('Token 已过期'))
}

/**
 * 将接口错误结构转换为用户可理解的中文提示。
 * 参数：`detail` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function formatError(detail: any) {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.join('，')
  if (typeof detail === 'object') {
    return Object.entries(detail).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join('，') : String(value)}`).join('；')
  }
  return String(detail)
}
