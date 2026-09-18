<script setup lang="ts">
import { BarChart, GaugeChart, GraphChart, LineChart, PieChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, LegendComponent, ToolboxComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ option: any; enableDataZoomSelect?: boolean; resizeKey?: string | number }>()
const root = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null
let resizeFrame = 0
let resizeTimer: number | undefined

echarts.use([
  LineChart,
  BarChart,
  GaugeChart,
  GraphChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  DataZoomComponent,
  ToolboxComponent,
  CanvasRenderer,
])

/**
 * 更新 render 对应的界面内容、尺寸或同步状态。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function render() {
  if (!root.value) return
  chart ||= echarts.init(root.value)
  chart.setOption(props.option, true)
  if (props.enableDataZoomSelect) {
    chart.dispatchAction({
      type: 'takeGlobalCursor',
      key: 'dataZoomSelect',
      dataZoomSelectActive: true,
    } as any)
  }
  scheduleResize()
}

/**
 * 更新 resizeChart 对应的界面内容、尺寸或同步状态。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function resizeChart() {
  chart?.resize()
}

/**
 * 封装 scheduleResize 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function scheduleResize() {
  void nextTick(() => {
    resizeChart()
    if (resizeFrame) window.cancelAnimationFrame(resizeFrame)
    resizeFrame = window.requestAnimationFrame(() => {
      resizeFrame = 0
      resizeChart()
    })
    if (resizeTimer) window.clearTimeout(resizeTimer)
    resizeTimer = window.setTimeout(() => {
      resizeTimer = undefined
      resizeChart()
    }, 120)
  })
}

watch(() => props.option, render, { deep: true })
watch(() => props.enableDataZoomSelect, render)
watch(() => props.resizeKey, scheduleResize)
onMounted(() => {
  render()
  observer = new ResizeObserver(() => scheduleResize())
  observer.observe(root.value!)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  if (resizeFrame) window.cancelAnimationFrame(resizeFrame)
  if (resizeTimer) window.clearTimeout(resizeTimer)
  chart?.dispose()
})
</script>

<template><div ref="root" class="echart" /></template>
