<script setup lang="ts">
import {
  Activity, Cpu, HardDrive, MemoryStick, Network,
  RefreshCw, Server, Users,
} from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { api } from '../../api'
import CustomSelect from '../../components/CustomSelect.vue'
import EChart from '../../components/EChart.vue'

type StatusPayload = {
  collected_at: string
  cpu: { percent: number; physical_cores: number; logical_cores: number }
  memory: { percent: number; used_bytes: number; total_bytes: number }
  disk: { percent: number; used_bytes: number; total_bytes: number }
  network: { bytes_sent: number; bytes_received: number }
  concurrency: { users: number; sessions: number }
  runtime: {
    hostname: string
    operating_system: string
    python_version: string
    process_id: number
    boot_time: string
    uptime_seconds: number
    architecture: string
    national_cryptography: Array<{
      feature: string
      algorithm: 'SM2' | 'SM3' | 'SM4'
      description: string
    }>
  }
}

type HistoryPoint = {
  time: string
  cpu: number
  memory: number
  disk: number
  upload: number
  download: number
  users: number
}

const refreshOptions = [5, 10, 30, 60, 120, 180]
const refreshSeconds = ref(10)
const loading = ref(false)
const error = ref('')
const status = ref<StatusPayload | null>(null)
const history = ref<HistoryPoint[]>([])
let refreshTimer: number | undefined
let previousNetwork: { sent: number; received: number; timestamp: number } | null = null

const commonChart = {
  animationDuration: 280,
  textStyle: { color: '#94a3b8' },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#111827',
    borderColor: '#334155',
    textStyle: { color: '#e5e7eb' },
  },
  grid: { left: 48, right: 22, top: 48, bottom: 34 },
  legend: { top: 10, textStyle: { color: '#94a3b8' } },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    axisLabel: { color: '#64748b' },
    axisLine: { lineStyle: { color: '#334155' } },
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: '#64748b' },
    splitLine: { lineStyle: { color: 'rgba(148, 163, 184, .12)' } },
  },
}

const resourceOption = computed(() => ({
  ...commonChart,
  xAxis: { ...commonChart.xAxis, data: history.value.map((point) => point.time) },
  yAxis: { ...commonChart.yAxis, min: 0, max: 100, axisLabel: { color: '#64748b', formatter: '{value}%' } },
  series: [
    { name: 'CPU', type: 'line', smooth: true, showSymbol: history.value.length <= 1, symbolSize: 7, data: history.value.map((point) => point.cpu), lineStyle: { color: '#3b82f6' }, itemStyle: { color: '#3b82f6' } },
    { name: '内存', type: 'line', smooth: true, showSymbol: history.value.length <= 1, symbolSize: 7, data: history.value.map((point) => point.memory), lineStyle: { color: '#10b981' }, itemStyle: { color: '#10b981' } },
    { name: '磁盘', type: 'line', smooth: true, showSymbol: history.value.length <= 1, symbolSize: 7, data: history.value.map((point) => point.disk), lineStyle: { color: '#f59e0b' }, itemStyle: { color: '#f59e0b' } },
  ],
}))

const networkOption = computed(() => ({
  ...commonChart,
  xAxis: { ...commonChart.xAxis, data: history.value.map((point) => point.time) },
  yAxis: { ...commonChart.yAxis, axisLabel: { color: '#64748b', formatter: '{value} KB/s' } },
  series: [
    { name: '发送', type: 'line', smooth: true, showSymbol: history.value.length <= 1, symbolSize: 7, data: history.value.map((point) => point.upload), lineStyle: { color: '#06b6d4' }, itemStyle: { color: '#06b6d4' }, areaStyle: { color: 'rgba(6, 182, 212, .08)' } },
    { name: '接收', type: 'line', smooth: true, showSymbol: history.value.length <= 1, symbolSize: 7, data: history.value.map((point) => point.download), lineStyle: { color: '#f43f5e' }, itemStyle: { color: '#f43f5e' }, areaStyle: { color: 'rgba(244, 63, 94, .06)' } },
  ],
}))

const concurrencyOption = computed(() => ({
  ...commonChart,
  xAxis: { ...commonChart.xAxis, data: history.value.map((point) => point.time) },
  yAxis: { ...commonChart.yAxis, minInterval: 1 },
  series: [
    { name: '在线用户', type: 'line', step: 'end', showSymbol: history.value.length <= 1, symbolSize: 7, data: history.value.map((point) => point.users), lineStyle: { color: '#22c55e' }, itemStyle: { color: '#22c55e' }, areaStyle: { color: 'rgba(34, 197, 94, .08)' } },
  ],
}))

/**
 * 把字节数转换为适合状态页面展示的容量文字。
 * 参数：`value` 为字节数。
 * 返回：带 B、KB、MB、GB 或 TB 单位的字符串。
 * 副作用：不修改页面或持久化数据。
 */
function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** index).toFixed(index > 1 ? 1 : 0)} ${units[index]}`
}

/**
 * 把运行秒数转换为天、小时和分钟组成的文字。
 * 参数：`seconds` 为系统运行秒数。
 * 返回：紧凑的中文运行时长。
 * 副作用：不修改页面或持久化数据。
 */
function formatUptime(seconds: number) {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return `${days} 天 ${hours} 小时 ${minutes} 分钟`
}

/**
 * 把采集时间转换为图表横轴所需的时分秒。
 * 参数：`value` 为 ISO 8601 时间。
 * 返回：当前浏览器时区的时分秒文字。
 * 副作用：不修改页面或持久化数据。
 */
function timeLabel(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date(value))
}

/**
 * 请求最新系统指标，并将相邻网络累计值换算为每秒吞吐量。
 * 参数：无。
 * 返回：异步采集完成后的 Promise。
 * 副作用：请求后端并更新指标、历史采样点及错误状态。
 */
async function loadStatus() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const payload = await api('/system-status/') as StatusPayload
    const timestamp = new Date(payload.collected_at).getTime()
    let upload = 0
    let download = 0
    if (previousNetwork && timestamp > previousNetwork.timestamp) {
      const elapsed = (timestamp - previousNetwork.timestamp) / 1000
      upload = Math.max(0, (payload.network.bytes_sent - previousNetwork.sent) / elapsed / 1024)
      download = Math.max(0, (payload.network.bytes_received - previousNetwork.received) / elapsed / 1024)
    }
    previousNetwork = {
      sent: payload.network.bytes_sent,
      received: payload.network.bytes_received,
      timestamp,
    }
    status.value = payload
    history.value = [...history.value, {
      time: timeLabel(payload.collected_at),
      cpu: payload.cpu.percent,
      memory: payload.memory.percent,
      disk: payload.disk.percent,
      upload: Number(upload.toFixed(2)),
      download: Number(download.toFixed(2)),
      users: payload.concurrency.users,
    }].slice(-30)
  } catch (reason: any) {
    error.value = reason.message || '加载系统状态失败'
  } finally {
    loading.value = false
  }
}

/**
 * 按当前选择重新创建自动刷新定时器。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：清理旧定时器并创建新的浏览器定时器。
 */
function restartTimer() {
  if (refreshTimer) window.clearInterval(refreshTimer)
  refreshTimer = window.setInterval(loadStatus, refreshSeconds.value * 1000)
}

/**
 * 选择系统状态自动刷新间隔。
 * 参数：`seconds` 为选中的秒数。
 * 返回：无显式返回值。
 * 副作用：更新刷新间隔并重启自动刷新定时器。
 */
function selectRefresh(seconds: number) {
  refreshSeconds.value = seconds
  restartTimer()
}

/**
 * 初始化系统状态页面并连续采集两个首屏数据点。
 * 参数：无。
 * 返回：首屏两次状态采集完成后的 Promise。
 * 副作用：立即请求系统状态，短暂等待后补充第二个图表采样点。
 */
async function initializeStatus() {
  await loadStatus()
  await new Promise<void>((resolve) => window.setTimeout(resolve, 800))
  await loadStatus()
}

onMounted(() => {
  void initializeStatus()
  restartTimer()
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<template>
  <section class="governance-page system-status-page">
    <header class="governance-page-head system-status-head">
      <div>
        <h2>系统状态</h2>
      </div>
      <div class="system-status-controls">
        <CustomSelect
          v-model.number="refreshSeconds"
          class="refresh-select"
          aria-label="自动刷新间隔"
          @change="selectRefresh(Number($event))"
        >
          <template #prefix><Activity :size="16" /></template>
          <option v-for="seconds in refreshOptions" :key="seconds" :value="seconds">{{ seconds }} 秒刷新</option>
        </CustomSelect>
        <button class="secondary icon-button action-refresh" type="button" title="刷新" :disabled="loading" @click="loadStatus">
          <RefreshCw :size="16" :class="{ spin: loading }" />
        </button>
      </div>
    </header>

    <p v-if="error" class="form-error system-status-error">{{ error }}</p>

    <div class="system-status-summary">
      <article><Cpu :size="19" /><span><small>CPU 使用率</small><strong>{{ status?.cpu.percent ?? 0 }}%</strong><em>{{ status?.cpu.logical_cores ?? 0 }} 逻辑核心</em></span></article>
      <article><MemoryStick :size="19" /><span><small>内存使用率</small><strong>{{ status?.memory.percent ?? 0 }}%</strong><em>{{ formatBytes(status?.memory.used_bytes ?? 0) }} / {{ formatBytes(status?.memory.total_bytes ?? 0) }}</em></span></article>
      <article><HardDrive :size="19" /><span><small>磁盘使用率</small><strong>{{ status?.disk.percent ?? 0 }}%</strong><em>{{ formatBytes(status?.disk.used_bytes ?? 0) }} / {{ formatBytes(status?.disk.total_bytes ?? 0) }}</em></span></article>
      <article><Users :size="19" /><span><small>在线用户</small><strong>{{ status?.concurrency.users ?? 0 }}</strong><em>已登录本平台的用户</em></span></article>
    </div>

    <div class="system-status-charts">
      <section class="system-status-chart-panel">
        <header><Cpu :size="17" /><div><h3>资源使用率</h3><p>CPU、内存与磁盘</p></div></header>
        <EChart :option="resourceOption" />
      </section>
      <section class="system-status-chart-panel">
        <header><Network :size="17" /><div><h3>网络吞吐量</h3><p>实时发送与接收速率</p></div></header>
        <EChart :option="networkOption" />
      </section>
      <section class="system-status-chart-panel system-status-chart-wide">
        <header><Users :size="17" /><div><h3>在线用户趋势</h3><p>已登录本平台的用户数量</p></div></header>
        <EChart :option="concurrencyOption" />
      </section>
    </div>

    <section v-if="status" class="system-runtime-band">
      <header><Server :size="18" /><h3>运行环境</h3></header>
      <dl>
        <div><dt>主机名</dt><dd>{{ status.runtime.hostname }}</dd></div>
        <div><dt>操作系统</dt><dd>{{ status.runtime.operating_system }}</dd></div>
        <div><dt>系统架构</dt><dd>{{ status.runtime.architecture }}</dd></div>
        <div><dt>Python</dt><dd>{{ status.runtime.python_version }}</dd></div>
        <div><dt>服务进程</dt><dd>PID {{ status.runtime.process_id }}</dd></div>
        <div><dt>运行时长</dt><dd>{{ formatUptime(status.runtime.uptime_seconds) }}</dd></div>
      </dl>
      <div class="runtime-cryptography">
        <h4>国密算法</h4>
        <div class="runtime-cryptography-table-wrap">
          <table>
            <thead><tr><th>功能</th><th>算法</th><th>说明</th></tr></thead>
            <tbody>
              <tr v-for="item in status.runtime.national_cryptography" :key="item.feature">
                <td :title="item.feature">{{ item.feature }}</td>
                <td><span class="runtime-algorithm-badge">{{ item.algorithm }}</span></td>
                <td :title="item.description">{{ item.description }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </section>
</template>
