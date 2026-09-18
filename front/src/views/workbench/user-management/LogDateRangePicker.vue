<script setup lang="ts">
import { computed } from 'vue'
import { VueDatePicker } from '@vuepic/vue-datepicker'
import '@vuepic/vue-datepicker/dist/main.css'
import { zhCN } from 'date-fns/locale'

import type { LogDateRange } from './logTools'

const model = defineModel<LogDateRange>({ required: true })
const latestSelectableTime = new Date()
const formats = { input: formatLogDateTime, preview: formatLogDateTime }
const actionRow = {
  showSelect: true,
  showCancel: true,
  showNow: false,
  showPreview: false,
  selectBtnLabel: '确定',
  cancelBtnLabel: '取消',
}
const timeConfig = {
  enableTimePicker: true,
  enableSeconds: true,
  enableMinutes: true,
  is24: true,
  timePickerInline: true,
  minutesGridIncrement: 1,
  secondsGridIncrement: 1,
}
const pickerUi = { menu: 'log-date-picker-menu' }

const startTime = computed<Date | null>({
  get: () => model.value?.[0] ?? null,
  set: (value) => updateBoundary(0, value),
})

const endTime = computed<Date | null>({
  get: () => model.value?.[1] ?? null,
  set: (value) => updateBoundary(1, value),
})

const startMaxTime = computed(() => model.value?.[1] ?? latestSelectableTime)
const endMinTime = computed(() => model.value?.[0])

/** 将日期数字补齐为两位，保证输入框中的日期时间整齐一致。 */
function padDatePart(part: number) {
  return String(part).padStart(2, '0')
}

/** 将单个日期格式化为二十四小时制的完整时间。 */
function formatLogDateTime(value: Date) {
  return `${value.getFullYear()}-${padDatePart(value.getMonth() + 1)}-${padDatePart(value.getDate())} ${padDatePart(value.getHours())}:${padDatePart(value.getMinutes())}:${padDatePart(value.getSeconds())}`
}

/** 独立更新开始或结束时间，并始终向日志查询页回传完整时间范围。 */
function updateBoundary(index: 0 | 1, value: Date | null) {
  if (!value) return
  const currentStart = model.value?.[0] ?? value
  const currentEnd = model.value?.[1] ?? value
  model.value = index === 0 ? [value, currentEnd] : [currentStart, value]
}
</script>

<template>
  <div class="log-date-range-picker">
    <div class="log-date-boundary">
      <span class="log-date-boundary-label">开始时间</span>
      <VueDatePicker
        v-model="startTime"
        :max-date="startMaxTime"
        :clearable="false"
        :teleport="true"
        :formats="formats"
        :locale="zhCN"
        :time-config="timeConfig"
        :action-row="actionRow"
        :ui="pickerUi"
        placeholder="选择开始时间"
        aria-label="日志开始时间"
      />
    </div>

    <div class="log-date-boundary">
      <span class="log-date-boundary-label">结束时间</span>
      <VueDatePicker
        v-model="endTime"
        :min-date="endMinTime"
        :max-date="latestSelectableTime"
        :clearable="false"
        :teleport="true"
        :formats="formats"
        :locale="zhCN"
        :time-config="timeConfig"
        :action-row="actionRow"
        :ui="pickerUi"
        placeholder="选择结束时间"
        aria-label="日志结束时间"
      />
    </div>
  </div>
</template>
