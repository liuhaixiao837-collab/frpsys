import { computed, ref } from 'vue'

import { downloadFile } from '../../../api'

export type LogDateRange = [Date, Date] | null

/** 返回日志页面默认使用的最近七天时间范围。 */
export function defaultLogDateRange(): LogDateRange {
  const end = new Date()
  const start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000)
  return [start, end]
}

/** 将日志时间范围和其他筛选条件转换为接口查询参数。 */
export function logQueryParams(range: LogDateRange, filters: Record<string, string> = {}) {
  const params = new URLSearchParams()
  if (range?.[0] && range?.[1]) {
    params.set('start_time', range[0].toISOString())
    params.set('end_time', range[1].toISOString())
  }
  Object.entries(filters).forEach(([key, value]) => {
    const normalized = value.trim()
    if (normalized) params.set(key, normalized)
  })
  return params
}

/** 校验日志导出时间范围完整且不超过一百八十天。 */
export function validateLogExportRange(range: LogDateRange) {
  if (!range?.[0] || !range?.[1]) return '导出前请选择完整的开始时间和结束时间'
  const duration = range[1].getTime() - range[0].getTime()
  if (duration <= 0) return '结束时间必须晚于开始时间'
  if (duration > 180 * 24 * 60 * 60 * 1000) return '单次最多导出 180 天日志，请缩小时间范围'
  return ''
}

/** 提供日志导出五秒倒计时、稳定按钮文字和浏览器下载状态。 */
export function useLogExport() {
  const exporting = ref(false)
  const countdown = ref(0)
  const exportButtonLabel = computed(() => {
    if (countdown.value > 0) return `导出中 ${countdown.value}`
    return exporting.value ? '正在生成 Excel' : '导出 Excel'
  })

  /** 倒计时结束后调用后端并触发浏览器附件下载。 */
  async function runLogExport(path: string, fallbackName: string) {
    if (exporting.value) return
    exporting.value = true
    try {
      for (let seconds = 5; seconds >= 1; seconds -= 1) {
        countdown.value = seconds
        await new Promise((resolve) => setTimeout(resolve, 1000))
      }
      countdown.value = 0
      await downloadFile(path, fallbackName)
    } finally {
      countdown.value = 0
      exporting.value = false
    }
  }

  return { exporting, countdown, exportButtonLabel, runLogExport }
}
