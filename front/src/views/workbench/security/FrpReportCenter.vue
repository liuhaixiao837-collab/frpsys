<script setup lang="ts">
import { Activity, Cable, Gauge, Server, ShieldCheck } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { api } from '../../../api'
import EChart from '../../../components/EChart.vue'

const loading = ref(false)
const error = ref('')
const reportData = ref<any | null>(null)

const statusText: Record<string, string> = {
  available: '可用',
  configured: '已配置',
  unconfigured: '未配置',
  unavailable: '不可用',
  disabled: '已禁用',
  online: '在线',
  offline: '离线',
  error: '异常',
  pending: '待处理',
  approved: '已通过',
  rejected: '已拒绝',
  manual: '手动维护',
  frps_dashboard: 'frps Dashboard',
  agent_report: 'Agent上报',
}

const palette = ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed', '#0891b2', '#64748b', '#ea580c']

/**
 * 处理 label 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function label(value: any) {
  return statusText[String(value)] || String(value || '未设置')
}

/**
 * 处理 pairs 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function pairs(rows: any[] = []) {
  return rows.map((item) => ({ name: label(item.name), value: item.value || 0 }))
}

/**
 * 处理 chartBase 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function chartBase() {
  return {
    color: palette,
    tooltip: { trigger: 'axis' },
    legend: { top: 0, textStyle: { color: '#64748b', fontSize: 11 } },
    grid: { left: 36, right: 18, top: 38, bottom: 28 },
    xAxis: { type: 'category', axisTick: { show: false }, axisLine: { lineStyle: { color: '#cbd5e1' } }, axisLabel: { color: '#64748b', fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1, axisLine: { show: false }, splitLine: { lineStyle: { color: '#e5e7eb' } }, axisLabel: { color: '#64748b', fontSize: 11 } },
  }
}

/**
 * 处理 pieOption 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function pieOption(title: string, rows: any[] = [], colors: string[] = palette) {
  return {
    color: colors,
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, type: 'scroll', textStyle: { color: '#64748b', fontSize: 11 } },
    series: [{
      name: title,
      type: 'pie',
      radius: ['46%', '70%'],
      center: ['50%', '43%'],
      avoidLabelOverlap: true,
      label: { formatter: '{b}\n{c}', fontSize: 11 },
      data: pairs(rows),
    }],
  }
}

/**
 * 处理 barOption 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function barOption(name: string, rows: any[] = [], color = '#f97316') {
  return {
    ...chartBase(),
    tooltip: { trigger: 'axis' },
    xAxis: { ...chartBase().xAxis, data: rows.map((item) => item.name) },
    series: [{ name, type: 'bar', barMaxWidth: 28, itemStyle: { color, borderRadius: [6, 6, 0, 0] }, data: rows.map((item) => item.value || 0) }],
  }
}

const reportKpis = computed(() => {
  const summary = reportData.value?.summary || {}
  const resourceTotal = (summary.server_count || 0) + (summary.agent_count || 0) + (summary.proxy_count || 0)
  const availableTotal = (summary.available_servers || 0) + (summary.online_agents || 0) + (summary.available_proxies || 0)
  const availability = resourceTotal ? Math.round((availableTotal / resourceTotal) * 100) : 0
  return [
    { label: '服务端', value: summary.server_count || 0, hint: `可用 ${summary.available_servers || 0}`, icon: Server },
    { label: 'frpc客户端', value: summary.agent_count || 0, hint: `在线 ${summary.online_agents || 0}`, icon: ShieldCheck },
    { label: '隧道端口', value: summary.proxy_count || 0, hint: `可用 ${summary.available_proxies || 0}`, icon: Cable },
    { label: 'Store API', value: summary.store_enabled_agents || 0, hint: '可下发端口客户端', icon: Activity },
    { label: '审计记录', value: summary.audit_count || 0, hint: 'FRP操作记录', icon: Activity },
    { label: '整体可用率', value: `${availability}%`, hint: `${availableTotal}/${resourceTotal} 个资源可用`, icon: Gauge },
  ]
})

const auditTrendOption = computed(() => {
  const rows = reportData.value?.audit_trend || []
  const base = chartBase()
  return {
    ...base,
    xAxis: { ...base.xAxis, data: rows.map((item: any) => item.date) },
    series: [
      { name: '审计总数', type: 'bar', stack: 'audit', itemStyle: { color: '#6366f1', borderRadius: [5, 5, 0, 0] }, data: rows.map((item: any) => item.audit || 0) },
      { name: '同步', type: 'line', smooth: true, symbolSize: 7, lineStyle: { width: 3, color: '#10b981' }, itemStyle: { color: '#10b981' }, data: rows.map((item: any) => item.sync || 0) },
      { name: '端口', type: 'line', smooth: true, symbolSize: 7, lineStyle: { width: 3, color: '#f59e0b' }, itemStyle: { color: '#f59e0b' }, data: rows.map((item: any) => item.proxy || 0) },
    ],
  }
})

const agentStatusOption = computed(() => pieOption('客户端状态', reportData.value?.agent_statuses, ['#10b981', '#94a3b8', '#ef4444', '#f59e0b']))
const proxyTypeOption = computed(() => pieOption('隧道类型', reportData.value?.proxy_types, ['#8b5cf6', '#06b6d4', '#f97316', '#ec4899', '#3b82f6']))
const proxyStatusOption = computed(() => pieOption('隧道状态', reportData.value?.proxy_statuses, ['#22c55e', '#ef4444', '#f59e0b', '#64748b']))
const serverStatusOption = computed(() => pieOption('服务端状态', reportData.value?.server_statuses, ['#0ea5e9', '#22c55e', '#ef4444', '#f59e0b']))
const topAgentsOption = computed(() => barOption('端口数', reportData.value?.top_agents || [], '#f97316'))
const agentSourceOption = computed(() => pieOption('客户端来源', reportData.value?.agent_sources, ['#a855f7', '#14b8a6', '#f59e0b']))

/**
 * 处理 load 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
async function load() {
  loading.value = true
  error.value = ''
  try {
    reportData.value = await api('/security/frp/reports/')
  } catch (reason: any) {
    error.value = reason.message || 'FRP报表加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="bastion-report-center frp-report-center">
    <div v-if="error" class="bastion-error">{{ error }}</div>
    <div v-if="loading" class="bastion-report-loading">加载中...</div>

    <template v-else-if="reportData">
      <section class="bastion-report-kpis frp-report-kpis">
        <article v-for="item in reportKpis" :key="item.label" class="bastion-report-kpi frp-report-kpi">
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
          <b>{{ item.value }}</b>
          <em>{{ item.hint }}</em>
        </article>
      </section>

      <section class="bastion-report-grid frp-report-grid">
        <article class="bastion-report-panel wide">
          <header><strong>最近7天操作趋势</strong><span>审计 / 同步 / 端口</span></header>
          <EChart :option="auditTrendOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>客户端状态</strong><span>frpc在线情况</span></header>
          <EChart :option="agentStatusOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>隧道类型</strong><span>TCP / UDP / HTTP等</span></header>
          <EChart :option="proxyTypeOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>隧道状态</strong><span>可用与异常分布</span></header>
          <EChart :option="proxyStatusOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>服务端状态</strong><span>frps健康状态</span></header>
          <EChart :option="serverStatusOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>Top客户端端口数</strong><span>按隧道数量排名</span></header>
          <EChart :option="topAgentsOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>客户端来源</strong><span>同步与上报来源</span></header>
          <EChart :option="agentSourceOption" />
        </article>
      </section>
    </template>
  </section>
</template>
