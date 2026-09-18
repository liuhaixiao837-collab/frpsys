<script setup lang="ts">
import { Clock3, Download, Eye, KeyRound, MapPin, Search, ShieldCheck, ShieldX, UserRound } from 'lucide-vue-next'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { api } from '../../../api'
import CustomSelect from '../../../components/CustomSelect.vue'
import ModalDialog from '../../../components/ModalDialog.vue'
import { normalize } from '../../../endpoints'
import { actionPermissionForPath } from '../../../permissions'
import { useAuthStore } from '../../../stores/auth'
import LogDateRangePicker from './LogDateRangePicker.vue'
import PaginationBar from './PaginationBar.vue'
import { defaultLogDateRange, logQueryParams, useLogExport, validateLogExportRange } from './logTools'
import type { AuditLogRow } from './types'
import { formatDateTime } from './types'
import { usePager } from './usePager'

const logs = ref<AuditLogRow[]>([])
const detailLog = ref<AuditLogRow | null>(null)
const loadingLogs = ref(false)
const error = ref('')
const filters = reactive({ q: '', status: '' })
const dateRange = ref(defaultLogDateRange())
const auth = useAuthStore()
const canExport = computed(() => auth.can(actionPermissionForPath('/logs/users', 'export')))
const { exporting, exportButtonLabel, runLogExport } = useLogExport()
const loginMethodLabels: Record<string, string> = {
  password: '账号密码',
  'password+otp': '密码 + OTP',
  sso: '单点登录',
  ldap: 'LDAP',
  oauth: 'OAuth',
}

/**
 * 返回登录日志的规范化结果状态。
 * 参数：`log` 表示一条登录日志。
 * 返回：成功或失败状态代码。
 * 副作用：不直接修改持久化数据。
 */
function loginStatus(log: AuditLogRow) {
  const status = String(log.detail?.status || '').toLowerCase()
  if (status === 'failed' || log.action.endsWith('.failed')) return 'failed'
  return 'success'
}

/**
 * 返回登录结果的中文显示文字。
 * 参数：`log` 表示一条登录日志。
 * 返回：中文状态名称。
 * 副作用：不直接修改持久化数据。
 */
function loginStatusLabel(log: AuditLogRow) {
  return loginStatus(log) === 'success' ? '成功' : '失败'
}

/**
 * 返回登录方式的中文显示文字。
 * 参数：`log` 表示一条登录日志。
 * 返回：中文登录方式。
 * 副作用：不直接修改持久化数据。
 */
function loginMethodLabel(log: AuditLogRow) {
  const method = String(log.detail?.auth_method || 'password').toLowerCase()
  return loginMethodLabels[method] || '其他方式'
}

/**
 * 返回登录日志中的用户友好结果说明。
 * 参数：`log` 表示一条登录日志。
 * 返回：结果说明文字。
 * 副作用：不直接修改持久化数据。
 */
function loginReason(log: AuditLogRow) {
  return String(log.detail?.reason || (loginStatus(log) === 'success' ? '登录成功' : '登录失败'))
}

const visibleLogs = computed(() => logs.value.filter((log) => {
  const query = filters.q.trim().toLowerCase()
  const matchesQuery = !query || [log.actor, log.ip_address, loginReason(log)]
    .some((value) => String(value || '').toLowerCase().includes(query))
  const matchesStatus = !filters.status || loginStatus(log) === filters.status
  return matchesQuery && matchesStatus
}))
const {
  pageSize, currentPage, jumpPage, totalPages, paginatedItems: paginatedLogs,
  pageStart, pageEnd, goPage, movePage, applyJump, resetPage,
} = usePager(visibleLogs, 10)

/**
 * 从后端加载用户登录日志并重置分页。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：请求用户日志接口并更新页面状态。
 */
async function loadLogs() {
  loadingLogs.value = true
  error.value = ''
  try {
    const params = logQueryParams(dateRange.value)
    params.set('page_size', '500')
    logs.value = normalize(await api(`/user-logs/?${params}`))
    resetPage()
  } catch (reason: any) {
    error.value = reason.message || '加载用户日志失败'
  } finally {
    loadingLogs.value = false
  }
}

/** 按当前关键词、登录状态、登录方式和时间范围倒计时导出全部用户日志。 */
async function exportLogs() {
  error.value = validateLogExportRange(dateRange.value)
  if (error.value) return
  const params = logQueryParams(dateRange.value, filters)
  try {
    await runLogExport(`/user-logs/export/?${params}`, 'user-logs.xlsx')
  } catch (reason: any) {
    error.value = reason.message || '用户日志导出失败'
  }
}

watch(filters, resetPage)
watch(dateRange, resetPage)
onMounted(loadLogs)
</script>

<template>
  <section class="governance-page">
    <div class="governance-card user-governance-card">
      <form class="governance-toolbar audit-toolbar user-log-toolbar" @submit.prevent="loadLogs">
        <label class="search-box">
          <Search :size="16" />
          <input v-model="filters.q" placeholder="搜索用户、来源地址、结果" />
        </label>
        <CustomSelect v-model="filters.status" aria-label="登录状态">
          <option value="">全部状态</option>
          <option value="success">成功</option>
          <option value="failed">失败</option>
        </CustomSelect>
        <LogDateRangePicker v-model="dateRange" />
        <div class="toolbar-actions">
          <button class="primary" type="submit"><Search :size="16" />查询</button>
          <button v-if="canExport" class="secondary log-export-button" type="button" :disabled="exporting" @click="exportLogs">
            <Download :size="16" />{{ exportButtonLabel }}
          </button>
        </div>
      </form>

      <p v-if="error" class="form-error">{{ error }}</p>
      <div class="governance-table user-log-table">
        <div class="governance-table-row table-head">
          <span class="sequence-col">序号</span>
          <span>登录时间</span>
          <span>登录用户</span>
          <span>登录状态</span>
          <span>登录方式</span>
          <span>操作</span>
        </div>
        <div v-for="(log, rowIndex) in paginatedLogs" :key="log.id" class="governance-table-row">
          <span class="sequence-col">{{ (currentPage - 1) * pageSize + rowIndex + 1 }}</span>
          <span>{{ formatDateTime(log.created_at) }}</span>
          <span><strong>{{ log.actor || '未知用户' }}</strong></span>
          <span>
            <b class="badge audit-action-badge" :class="loginStatus(log) === 'success' ? 'audit-tone-success' : 'audit-tone-danger'">
              {{ loginStatusLabel(log) }}
            </b>
          </span>
          <span>{{ loginMethodLabel(log) }}</span>
          <span class="row-actions">
            <button class="detail-button" title="查看详情" type="button" @click="detailLog = log"><Eye :size="15" />详情</button>
          </span>
        </div>
        <p v-if="!logs.length" class="empty-list">{{ loadingLogs ? '用户日志加载中...' : '暂无用户日志' }}</p>
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
    title="用户日志详情"
    description="登录凭据不会进入日志。"
    width="700px"
    @close="detailLog = null"
  >
    <div v-if="detailLog" class="audit-detail-modal">
      <section class="audit-detail-summary">
        <span class="audit-detail-summary-icon">
          <ShieldCheck v-if="loginStatus(detailLog) === 'success'" :size="22" />
          <ShieldX v-else :size="22" />
        </span>
        <div>
          <b class="badge audit-action-badge" :class="loginStatus(detailLog) === 'success' ? 'audit-tone-success' : 'audit-tone-danger'">
            登录{{ loginStatusLabel(detailLog) }}
          </b>
          <h3>{{ detailLog.actor || '未知用户' }}</h3>
          <p>{{ loginReason(detailLog) }}</p>
        </div>
      </section>
      <section class="audit-detail-overview">
        <article><UserRound :size="18" /><span>登录用户<strong>{{ detailLog.actor || '未知用户' }}</strong></span></article>
        <article><Clock3 :size="18" /><span>登录时间<strong>{{ formatDateTime(detailLog.created_at) }}</strong></span></article>
        <article><KeyRound :size="18" /><span>登录方式<strong>{{ loginMethodLabel(detailLog) }}</strong></span></article>
        <article><MapPin :size="18" /><span>来源地址<strong>{{ detailLog.ip_address || '未知地址' }}</strong></span></article>
      </section>
    </div>
  </ModalDialog>
</template>
