<script setup lang="ts">
import { Activity, ArrowDownToLine, ArrowUpFromLine, Cable, Clock3, RefreshCw } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { api } from '../../../api'

const loading = ref(false)
const error = ref('')
const reportData = ref<any | null>(null)

function formatMegabytes(value: any) {
  const bytes = Number(value || 0)
  if (!bytes) return '0.00M'
  return `${(bytes / 1024 / 1024).toFixed(2)}M`
}

const summaryCards = computed(() => {
  const summary = reportData.value?.summary || {}
  return [
    { label: '合计流量', value: formatMegabytes(summary.traffic_total_bytes), icon: Activity, tone: 'blue' },
    { label: '今日流量', value: formatMegabytes(summary.today_traffic_total_bytes), icon: Clock3, tone: 'purple' },
    { label: '今日入站', value: formatMegabytes(summary.today_traffic_in_bytes), icon: ArrowDownToLine, tone: 'green' },
    { label: '今日出站', value: formatMegabytes(summary.today_traffic_out_bytes), icon: ArrowUpFromLine, tone: 'orange' },
  ]
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    reportData.value = await api('/security/frp/traffic-reports/')
  } catch (reason: any) {
    error.value = reason.message || '流量报表加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="frp-traffic-report">
    <header class="frp-traffic-report-head">
      <div>
        <h2>FRP 流量报表</h2>
        <p>展示已从 frps Dashboard 同步的隧道今日流量和合计流量，单位统一为 M。</p>
      </div>
      <button class="icon-button" type="button" title="刷新" :disabled="loading" @click="load">
        <RefreshCw :size="16" :class="{ spinning: loading }" />
      </button>
    </header>

    <div v-if="error" class="bastion-error">{{ error }}</div>
    <div v-if="loading && !reportData" class="bastion-report-loading">加载中...</div>

    <template v-else-if="reportData">
      <section class="frp-traffic-kpis">
        <article v-for="item in summaryCards" :key="item.label" :class="`tone-${item.tone}`">
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
        </article>
      </section>

      <section class="frp-traffic-panel">
        <header><strong>隧道流量明细</strong><span>按总流量从高到低排列</span></header>
        <div class="frp-traffic-table-wrap">
          <table class="frp-traffic-table">
            <thead>
              <tr><th>隧道名称</th><th>Agent</th><th>服务端</th><th>类型</th><th>今日流量</th><th>合计流量</th><th>更新时间</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in reportData.tunnels || []" :key="item.id">
                <td>{{ item.name || '-' }}</td>
                <td>{{ item.agent_name || '-' }}</td>
                <td>{{ item.server_name || '-' }}</td>
                <td>{{ String(item.proxy_type || '').toUpperCase() || '-' }}</td>
                <td class="traffic-in">{{ formatMegabytes(item.today_traffic_total_bytes) }}</td>
                <td class="traffic-total">{{ formatMegabytes(item.traffic_total_bytes) }}</td>
                <td>{{ item.traffic_updated_at || '-' }}</td>
              </tr>
              <tr v-if="!(reportData.tunnels || []).length"><td colspan="7" class="empty-cell">暂无流量数据，请先同步 FRP 服务端运行状态。</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>
