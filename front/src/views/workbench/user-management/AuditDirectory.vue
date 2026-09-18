<script setup lang="ts">
import { Activity, Clock3, Download, Eye, MapPin, Search, Target, UserRound } from 'lucide-vue-next'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { api } from '../../../api'
import ModalDialog from '../../../components/ModalDialog.vue'
import { normalize } from '../../../endpoints'
import { actionPermissionForPath } from '../../../permissions'
import { useAuthStore } from '../../../stores/auth'
import LogDateRangePicker from './LogDateRangePicker.vue'
import PaginationBar from './PaginationBar.vue'
import {
  auditActionLabel,
  auditActionTone,
  auditDetailItems,
  auditResourceLabel,
  auditResourceType,
  isTechnicalAudit,
} from './auditPresentation'
import { defaultLogDateRange, logQueryParams, useLogExport, validateLogExportRange } from './logTools'
import type { AuditLogRow } from './types'
import { formatDateTime } from './types'
import { usePager } from './usePager'

const logs = ref<AuditLogRow[]>([])
const detailLog = ref<AuditLogRow | null>(null)
const loadingLogs = ref(false)
const error = ref('')
const filters = reactive({ q: '' })
const dateRange = ref(defaultLogDateRange())
const auth = useAuthStore()
const canExport = computed(() => auth.can(actionPermissionForPath('/logs/system', 'export')))
const { exporting, exportButtonLabel, runLogExport } = useLogExport()
/**
 * 判断接口兜底日志是否已有同一请求生成的中文业务日志。
 * 参数：`log` 表示待判断的接口兜底日志。
 * 返回：存在同操作者且时间接近的业务日志时返回真。
 * 副作用：不直接修改持久化数据。
 */
function hasBusinessPair(log: AuditLogRow) {
  const occurredAt = new Date(log.created_at).getTime()
  return logs.value.some((candidate) => (
    !isTechnicalAudit(candidate)
    && candidate.actor === log.actor
    && Math.abs(new Date(candidate.created_at).getTime() - occurredAt) <= 3000
  ))
}

const businessLogs = computed(() => logs.value.filter((log) => !isTechnicalAudit(log) || !hasBusinessPair(log)))
const visibleLogs = computed(() => businessLogs.value.filter((log) => {
  const query = filters.q.trim().toLowerCase()
  const action = auditActionLabel(log.action)
  const resource = auditResourceLabel(log)
  const details = auditDetailItems(log.detail).map((item) => `${item.label}${item.value}`).join(' ')
  const matchesQuery = !query || [log.actor, action, resource, log.ip_address, details].some((value) => String(value || '').toLowerCase().includes(query))
  return matchesQuery
}))
const {
  pageSize, currentPage, jumpPage, totalPages, paginatedItems: paginatedLogs,
  pageStart, pageEnd, goPage, movePage, applyJump, resetPage,
} = usePager(visibleLogs, 10)

/**
 * 根据当前筛选条件生成接口查询字符串。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function queryString() {
  const params = logQueryParams(dateRange.value)
  params.set('page_size', '500')
  return params.toString()
}

/**
 * 从后端或当前状态加载 loadLogs 所需的最新业务数据。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function loadLogs() {
  loadingLogs.value = true
  error.value = ''
  try {
    logs.value = normalize(await api(`/system-logs/?${queryString()}`))
    resetPage()
  } catch (reason: any) {
    error.value = reason.message || '加载审计日志失败'
  } finally {
    loadingLogs.value = false
  }
}

/** 按当前关键词和时间范围倒计时导出全部系统日志。 */
async function exportLogs() {
  error.value = validateLogExportRange(dateRange.value)
  if (error.value) return
  const params = logQueryParams(dateRange.value, { q: filters.q })
  try {
    await runLogExport(`/system-logs/export/?${params}`, 'system-logs.xlsx')
  } catch (reason: any) {
    error.value = reason.message || '系统日志导出失败'
  }
}

/**
 * 封装 actorLabel 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`actor` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function actorLabel(actor: string) {
  return actor || '系统服务'
}

watch(filters, () => resetPage())
watch(dateRange, () => resetPage())

onMounted(loadLogs)
</script>

<template>
  <section class="governance-page">

    <div class="governance-card user-governance-card">
      <form class="governance-toolbar audit-toolbar system-log-toolbar" @submit.prevent="loadLogs">
        <label class="search-box">
          <Search :size="16" />
          <input v-model="filters.q" placeholder="搜索操作者、操作、资源" />
        </label>
        <LogDateRangePicker v-model="dateRange" />
        <div class="toolbar-actions">
          <button class="primary" type="submit"><Search :size="16" />查询</button>
          <button v-if="canExport" class="secondary log-export-button" type="button" :disabled="exporting" @click="exportLogs">
            <Download :size="16" />{{ exportButtonLabel }}
          </button>
        </div>
      </form>

      <p v-if="error" class="form-error">{{ error }}</p>
      <div class="governance-table audit-table">
        <div class="governance-table-row table-head">
          <span class="sequence-col">序号</span>
          <span>时间</span>
          <span>操作者</span>
          <span>操作类型</span>
          <span>操作对象</span>
          <span>操作</span>
        </div>
        <div v-for="(log, rowIndex) in paginatedLogs" :key="log.id" class="governance-table-row">
          <span class="sequence-col">{{ (currentPage - 1) * pageSize + rowIndex + 1 }}</span>
          <span>{{ formatDateTime(log.created_at) }}</span>
          <span>
            <strong>{{ actorLabel(log.actor) }}</strong>
          </span>
          <span><b class="badge audit-action-badge" :class="auditActionTone(log.action)">{{ auditActionLabel(log.action) }}</b></span>
          <span class="audit-resource">{{ auditResourceLabel(log) }}</span>
          <span class="row-actions">
            <button class="detail-button" title="查看详情" type="button" @click="detailLog = log"><Eye :size="15" />详情</button>
          </span>
        </div>
        <p v-if="!logs.length" class="empty-list">{{ loadingLogs ? '系统日志加载中...' : '暂无系统日志' }}</p>
      </div>

      <PaginationBar
        v-model:jump-page="jumpPage"
        :page-size="pageSize"
        :current-page="currentPage"
        :total-pages="totalPages"
        :page-start="pageStart"
        :page-end="pageEnd"
        :total="visibleLogs.length"
        @go="goPage"
        @move="movePage"
        @jump="applyJump"
      />
    </div>
  </section>

  <ModalDialog
    :open="Boolean(detailLog)"
    title="系统日志详情"
    description="用户行为已转换为便于阅读的中文业务信息。"
    width="760px"
    @close="detailLog = null"
  >
    <div v-if="detailLog" class="audit-detail-modal">
      <section class="audit-detail-summary">
        <span class="audit-detail-summary-icon"><Activity :size="22" /></span>
        <div>
          <b class="badge audit-action-badge" :class="auditActionTone(detailLog.action)">{{ auditActionLabel(detailLog.action) }}</b>
          <h3>{{ auditResourceLabel(detailLog) }}</h3>
          <p>{{ actorLabel(detailLog.actor) }} 在 {{ formatDateTime(detailLog.created_at) }} 对 {{ auditResourceLabel(detailLog) }} 执行了“{{ auditActionLabel(detailLog.action) }}”。</p>
        </div>
      </section>

      <section class="audit-detail-overview">
        <article><UserRound :size="18" /><span>操作者<strong>{{ actorLabel(detailLog.actor) }}</strong></span></article>
        <article><Clock3 :size="18" /><span>发生时间<strong>{{ formatDateTime(detailLog.created_at) }}</strong></span></article>
        <article><Target :size="18" /><span>资源类型<strong>{{ auditResourceType(detailLog) }}</strong></span></article>
        <article><MapPin :size="18" /><span>来源地址<strong>{{ detailLog.ip_address || '未知地址' }}</strong></span></article>
      </section>

      <section class="audit-detail-content">
        <header><h3>操作内容</h3><span>本次操作记录的业务信息</span></header>
        <dl v-if="auditDetailItems(detailLog.detail).length">
          <template v-for="item in auditDetailItems(detailLog.detail)" :key="`${item.label}-${item.value}`">
            <dt>{{ item.label }}</dt><dd>{{ item.value }}</dd>
          </template>
        </dl>
        <p v-else class="audit-detail-empty">本次操作没有额外的变更信息。</p>
      </section>
    </div>
  </ModalDialog>
</template>
