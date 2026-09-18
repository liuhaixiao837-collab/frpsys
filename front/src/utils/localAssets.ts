const LOCAL_ASSET_PREFIXES = ['/assets/', '/uploads/']

/**
 * 封装 localAssetUrl 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`value` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function localAssetUrl(value: unknown): string {
  const path = String(value || '').trim()
  if (!path || path.startsWith('//') || path.includes('\\') || path.split('/').includes('..')) return ''
  return LOCAL_ASSET_PREFIXES.some((prefix) => path.startsWith(prefix)) ? path : ''
}

/**
 * 封装 requireLocalAssetUrl 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`value` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function requireLocalAssetUrl(value: unknown): string {
  const path = String(value || '').trim()
  const normalized = localAssetUrl(path)
  if (path && !normalized) throw new Error('只能使用 /assets/ 或 /uploads/ 下的本地资源路径，禁止引用外网地址')
  return normalized
}

