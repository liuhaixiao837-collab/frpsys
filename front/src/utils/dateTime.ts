const SUPPORTED_TIMEZONES = new Set([
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Singapore',
  'Asia/Tokyo',
  'UTC',
])

let platformTimezone = 'Asia/Shanghai'

/**
 * 更新前端统一使用的平台时区。
 * 参数：`timezone` 为公开平台接口返回的 IANA 时区代码。
 * 返回：最终采用的受支持时区代码。
 * 副作用：更新当前浏览器会话后续时间格式化所用的模块状态。
 */
export function setPlatformTimezone(timezone?: string) {
  platformTimezone = timezone && SUPPORTED_TIMEZONES.has(timezone) ? timezone : 'Asia/Shanghai'
  return platformTimezone
}

/**
 * 按数据库配置的平台时区格式化日期时间。
 * 参数：`value` 为 ISO 日期字符串、时间戳或 Date 对象；`emptyText` 为空值显示文字。
 * 返回：格式为 YYYY-MM-DD HH:mm:ss 的平台时间，无法解析时返回原值。
 * 副作用：不修改持久化数据。
 */
export function formatPlatformDateTime(value?: string | number | Date | null, emptyText = '暂无') {
  if (value === null || value === undefined || value === '') return emptyText
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const formatter = new Intl.DateTimeFormat('zh-CN', {
    timeZone: platformTimezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  })
  const values: Record<string, string> = {}
  for (const part of formatter.formatToParts(date)) {
    if (part.type !== 'literal') values[part.type] = part.value
  }
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`
}
