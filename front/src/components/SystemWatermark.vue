<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import type { WatermarkSettings } from '../stores/platform'

const props = defineProps<{
  config: WatermarkSettings
  username: string
  platformName: string
  clientIp?: string
  preview?: boolean
}>()

const currentTime = ref(new Date())
let refreshTimer: number | undefined

const identityText = computed(() => ({
    username: props.username || '当前用户',
    username_ip: `${props.username || '当前用户'} · ${props.clientIp || '当前 IP'}`,
    platform: props.platformName || '统一管理平台',
    custom: props.config.custom_text || '安全水印',
  }[props.config.content_type]))

const timeText = computed(() => props.config.show_time ? formatMinute(currentTime.value) : '')

const tiledStyle = computed(() => {
  const identityWidth = estimateTextWidth(identityText.value, props.config.font_size)
  const timeWidth = timeText.value ? estimateTextWidth(timeText.value, props.config.font_size * 0.82) : 0
  const textWidth = Math.max(identityWidth, timeWidth)
  const textHeight = props.config.font_size * (timeText.value ? 2.35 : 1.4)
  const radians = Math.abs(props.config.rotate) * Math.PI / 180
  const rotatedWidth = textWidth * Math.cos(radians) + textHeight * Math.sin(radians)
  const rotatedHeight = textWidth * Math.sin(radians) + textHeight * Math.cos(radians)
  const width = Math.max(props.config.horizontal_gap, Math.ceil(rotatedWidth + 36))
  const height = Math.max(props.config.vertical_gap, Math.ceil(rotatedHeight + 30))
  const identity = escapeSvgText(identityText.value)
  const timestamp = escapeSvgText(timeText.value)
  const textLines = timeText.value
    ? `<tspan x="50%" dy="-0.5em">${identity}</tspan><tspan x="50%" dy="1.55em" font-size="82%" font-weight="400">${timestamp}</tspan>`
    : `<tspan x="50%">${identity}</tspan>`
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" transform="rotate(${props.config.rotate} ${width / 2} ${height / 2})" fill="${props.config.color}" fill-opacity="${props.config.opacity}" font-family="Arial, Microsoft YaHei, sans-serif" font-size="${props.config.font_size}" font-weight="${props.config.font_weight}">${textLines}</text></svg>`
  return {
    backgroundImage: `url("data:image/svg+xml,${encodeURIComponent(svg)}")`,
    backgroundSize: `${width}px ${height}px`,
  }
})

const centerStyle = computed(() => ({
  color: props.config.color,
  opacity: props.config.opacity,
  fontSize: `${props.config.font_size}px`,
  fontWeight: props.config.font_weight,
  transform: `rotate(${props.config.rotate}deg)`,
}))

/** 将当前时间格式化到分钟，作为可追溯水印的一部分。 */
function formatMinute(value: Date) {
  return `${value.getFullYear()}-${padTimePart(value.getMonth() + 1)}-${padTimePart(value.getDate())} ${padTimePart(value.getHours())}:${padTimePart(value.getMinutes())}`
}

/** 把水印时间中的单个数字补齐为两位。 */
function padTimePart(part: number) {
  return String(part).padStart(2, '0')
}

/** 转义 SVG 文本节点中的特殊字符，避免自定义文字破坏水印图层。 */
function escapeSvgText(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
  }[character] || character))
}

/** 按中英文字符宽度估算水印文本尺寸，用于避免平铺单元裁切用户名。 */
function estimateTextWidth(value: string, fontSize: number) {
  return Array.from(value).reduce((width, character) => (
    width + (/^[\x00-\xff]$/.test(character) ? fontSize * 0.62 : fontSize)
  ), 0)
}

/** 启动分钟级刷新，使包含时间的水印保持当前。 */
function startTimeRefresh() {
  refreshTimer = window.setInterval(() => {
    currentTime.value = new Date()
  }, 60_000)
}

/** 释放水印时间刷新定时器。 */
function stopTimeRefresh() {
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer)
}

onMounted(startTimeRefresh)
onBeforeUnmount(stopTimeRefresh)
</script>

<template>
  <div
    v-if="config.enabled"
    class="system-watermark"
    :class="{ 'system-watermark-preview': preview, 'system-watermark-center': config.layout === 'center' }"
    :style="config.layout === 'tiled' ? tiledStyle : undefined"
    aria-hidden="true"
  >
    <span v-if="config.layout === 'center'" :style="centerStyle">
      <strong>{{ identityText }}</strong>
      <small v-if="timeText">{{ timeText }}</small>
    </span>
  </div>
</template>

<style scoped>
.system-watermark {
  position: fixed;
  inset: 0;
  z-index: 70;
  overflow: hidden;
  pointer-events: none;
  user-select: none;
}

.system-watermark-preview {
  position: absolute;
  z-index: 1;
  border-radius: inherit;
}

.system-watermark-center {
  display: grid;
  place-items: center;
}

.system-watermark-center span {
  max-width: 82%;
  line-height: 1.5;
  text-align: center;
  white-space: nowrap;
}

.system-watermark-center strong,
.system-watermark-center small {
  display: block;
  color: inherit;
  font: inherit;
}

.system-watermark-center small {
  margin-top: .45em;
  font-size: .82em;
  font-weight: 400;
}
</style>
