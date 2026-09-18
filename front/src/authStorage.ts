const ACCESS_KEY = 'ongrid_access_token'
const REFRESH_KEY = 'ongrid_refresh_token'

/**
 * 计算并返回 getAccessToken 对应的业务数据。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function getAccessToken() {
  const token = sessionStorage.getItem(ACCESS_KEY)
  if (token && token.length > 4096) {
    sessionStorage.removeItem(ACCESS_KEY)
    return null
  }
  return token
}

/**
 * 计算并返回 getRefreshToken 对应的业务数据。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function getRefreshToken() {
  const token = localStorage.getItem(REFRESH_KEY)
  if (token && token.length > 4096) {
    localStorage.removeItem(REFRESH_KEY)
    return null
  }
  return token
}

/**
 * 封装 setTokens 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`access` 表示该步骤所需的业务参数；`refresh` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
export function setTokens(access: string, refresh?: string) {
  sessionStorage.setItem(ACCESS_KEY, access)
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
}

/**
 * 执行 clearTokens 对应的清理或删除操作并同步页面状态。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
export function clearTokens() {
  sessionStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem('ongrid_token')
}

/**
 * 判断 hasAnyToken 对应的业务条件是否成立。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function hasAnyToken() {
  return Boolean(getAccessToken() || getRefreshToken() || localStorage.getItem('ongrid_token'))
}
