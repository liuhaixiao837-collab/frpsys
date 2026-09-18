<script setup lang="ts">
import { Copy, Download, Edit3, Eye, EyeOff, Play, Plus, Power, RefreshCw, RotateCw, Search, Send, TestTube2, Trash2, Upload, XCircle } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, apiForm } from '../../api'
import { actionPermissionForPath } from '../../permissions'
import type { ResourceAction, ResourceColumn, ResourceField, ResourceSchema } from '../../resourceSchemas'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import ModalDialog from '../../components/ModalDialog.vue'
import RichTextEditor from '../../components/RichTextEditor.vue'
import CrudPagination from './dbquery/CrudPagination.vue'
import PaginationBar from './user-management/PaginationBar.vue'
import { useAuthStore } from '../../stores/auth'

const props = defineProps<{ schema: ResourceSchema; items: any[]; page?: number; pageSize?: number; total?: number }>()
const emit = defineEmits<{ refresh: []; page: [page: number] }>()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const query = ref('')
const modalOpen = ref(false)
const deleteOpen = ref(false)
const editing = ref<any | null>(null)
const deleting = ref<any | null>(null)
const saving = ref(false)
const deletingNow = ref(false)
const actionResult = ref('')
const error = ref('')
const form = reactive<Record<string, any>>({})
const visiblePasswords = reactive<Record<string, boolean>>({})
const revealingPasswords = reactive<Record<string, boolean>>({})
const revealedSecrets = reactive<Record<string, string>>({})
const revealedPasswordValues = reactive<Record<string, string>>({})
const actionModalOpen = ref(false)
const runningAction = ref<ResourceAction | null>(null)
const actionItem = ref<any | null>(null)
const actionForm = reactive<Record<string, any>>({})
const actionFile = ref<File | null>(null)
const downloadingTemplate = ref(false)
const selectedIds = ref<Array<string | number>>([])
const actionConfirmOpen = ref(false)
const confirmingAction = ref<ResourceAction | null>(null)
const confirmingActionItem = ref<any | null>(null)
const actionConfirmLoading = ref(false)
const previewOpen = ref(false)
const previewTitle = ref('')
const previewData = ref<Record<string, any> | null>(null)
const previewedAt = ref('')
const dynamicOptions = reactive<Record<string, Array<[string, string]>>>({})
const openMultiSelects = reactive<Record<string, boolean>>({})

const filtered = computed(() => props.items.filter((item) => JSON.stringify(item).toLowerCase().includes(query.value.toLowerCase())))
const currentPath = computed(() => route.path)
const isFrpResource = computed(() => props.schema.endpoint.startsWith('/security/frp/'))
const isFrpServerResource = computed(() => props.schema.endpoint.split('?')[0] === '/security/frp/servers/')
const isFrpAuditResource = computed(() => props.schema.endpoint.split('?')[0] === '/security/frp/audits/')
const isFrpPaginatedResource = computed(() => [
  '/security/frp/servers/',
  '/security/frp/agents/',
  '/security/frp/proxies/',
  '/security/frp/audits/',
].includes(props.schema.endpoint.split('?')[0]))
const canCreate = computed(() => auth.can(actionPermissionForPath(currentPath.value, 'create')))
const canUpdate = computed(() => auth.can(actionPermissionForPath(currentPath.value, 'update')))
const canDelete = computed(() => auth.can(actionPermissionForPath(currentPath.value, 'delete')))
const canReveal = computed(() => auth.can(actionPermissionForPath(currentPath.value, 'reveal')))
const canExecute = computed(() => auth.can(actionPermissionForPath(currentPath.value, 'execute')))
/**
 * 处理 canRunAction 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function canRunAction(action: ResourceAction) {
  return auth.can(actionPermissionForPath(currentPath.value, action.permission || 'execute'))
}
const hasRichTextForm = computed(() => props.schema.fields.some((field) => field.type === 'richtext'))
const hasPhishingForm = computed(() => props.schema.endpoint.includes('/security/phishing/'))
const formDialogClass = computed(() => hasRichTextForm.value ? 'template-editor-dialog' : (hasPhishingForm.value ? 'phishing-editor-dialog' : (isFrpResource.value ? 'frp-resource-dialog' : undefined)))
const formDialogWidth = computed(() => hasRichTextForm.value ? '1420px' : (hasPhishingForm.value ? '1000px' : (isFrpResource.value ? '980px' : undefined)))
const showActionColumn = computed(() => Boolean(
  (props.schema.actions || []).some((action) => canRunAction(action)) || (!props.schema.readonly && (canUpdate.value || canDelete.value)),
))
const isSelectable = computed(() => Boolean(props.schema.selectable))
const visibleSelectableIds = computed(() => filtered.value.map((item) => rowId(item)).filter((id) => id !== undefined && id !== null))
const allFilteredSelected = computed(() => Boolean(visibleSelectableIds.value.length) && visibleSelectableIds.value.every((id) => selectedIds.value.includes(id)))
const selectionHint = computed(() => selectedIds.value.length ? `已选择 ${selectedIds.value.length} 条` : `${filtered.value.length} 条记录`)
const paginationPage = computed(() => props.page || 1)
const paginationPageSize = computed(() => props.pageSize || 10)
const paginationTotal = computed(() => typeof props.total === 'number' ? props.total : 0)
const showPagination = computed(() => paginationTotal.value > paginationPageSize.value)
const paginationTotalPages = computed(() => Math.max(1, Math.ceil(paginationTotal.value / paginationPageSize.value)))
const paginationPageStart = computed(() => paginationTotal.value ? (paginationPage.value - 1) * paginationPageSize.value + 1 : 0)
const paginationPageEnd = computed(() => Math.min(paginationTotal.value, paginationPage.value * paginationPageSize.value))
const paginationJumpPage = ref('')
const firstColumnKey = computed(() => columnKey(props.schema.columns[0]))
const tableGridStyle = computed(() => {
  const trackMeta = props.schema.columns.map((column, index) => columnGridTrack(column, index))
  const dataColumns = trackMeta.map((item) => item.track)
  if (isSelectable.value) dataColumns.unshift('44px')
  const actionColumnWidth = props.schema.compactTable ? (isFrpResource.value ? 438 : 128) : 330
  if (showActionColumn.value) dataColumns.push(props.schema.compactTable ? `${actionColumnWidth}px` : `minmax(${actionColumnWidth}px, auto)`)
  const columnGap = props.schema.compactTable ? 5 : 10
  const rowPadding = props.schema.compactTable ? 14 : 24
  const contentWidth = trackMeta.reduce((sum, item) => sum + item.min, 0) +
    (isSelectable.value ? 44 : 0) +
    (showActionColumn.value ? actionColumnWidth : 0)
  const gapWidth = Math.max(dataColumns.length - 1, 0) * columnGap
  const minTableWidth = contentWidth + gapWidth + rowPadding
  return {
    gridTemplateColumns: dataColumns.join(' '),
    minWidth: props.schema.compactTableFill ? `max(100%, ${minTableWidth}px)` : (props.schema.compactTable ? `${minTableWidth}px` : `${Math.max(760, minTableWidth)}px`),
    width: props.schema.compactTableFill ? '100%' : undefined,
  }
})

/**
 * 返回敏感字段对应的后端存在标记字段。
 * 参数：`key` 为表单中的敏感字段名。
 * 返回：返回接口中的 has_* 标记字段名，没有对应标记时返回空字符串。
 * 副作用：无。
 */
function secretPresenceKey(key: string) {
  const mapping: Record<string, string> = {
    auth_token: 'has_auth_token',
    dashboard_password: 'has_dashboard_password',
    admin_password: 'has_admin_password',
  }
  return mapping[key] || ''
}
const previewSubject = computed(() => display(previewData.value?.subject || previewData.value?.title || previewData.value?.name || '预览内容'))
const previewHtml = computed(() => sanitizePreviewHtml(previewData.value?.html || previewData.value?.body_html || previewData.value?.html_content || ''))
const previewText = computed(() => display(previewData.value?.text || previewData.value?.body_text || previewData.value?.content || previewData.value || ''))
const previewSize = computed(() => {
  const length = String(previewData.value?.html || previewData.value?.text || previewData.value?.content || '').length
  if (!length) return '-'
  return length > 1024 ? `${Math.ceil(length / 1024)}k` : `${length}b`
})

/**
 * 处理 defaultValue 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function defaultValue(field: ResourceField) {
  if (field.default !== undefined) return field.default
  if (field.type === 'checkbox') return false
  if (field.type === 'statusSwitch') return true
  if (field.type === 'number') return 0
  if (field.type === 'json') return '{}'
  if (field.type === 'multiselect') return []
  if (field.type === 'file') return null
  if (field.type === 'list') return ''
  return ''
}

/**
 * 处理 togglePassword 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
async function togglePassword(key: string) {
  if (visiblePasswords[key]) {
    visiblePasswords[key] = false
    return
  }
  if (!editing.value || !isFrpResource.value || (form[key] && form[key] !== '********')) {
    visiblePasswords[key] = true
    return
  }
  if (!canReveal.value) {
    error.value = '没有查看敏感信息权限，请在用户管理的权限策略中授权。'
    return
  }
  revealingPasswords[key] = true
  error.value = ''
  try {
    if (!Object.keys(revealedSecrets).length) {
      const result = await api(`${endpointFor(editing.value)}reveal/`)
      for (const [secretKey, value] of Object.entries(result.secrets || {})) revealedSecrets[secretKey] = String(value || '')
    }
    const value = revealedSecrets[key] || ''
    form[key] = value
    revealedPasswordValues[key] = value
    visiblePasswords[key] = true
    if (!value) error.value = '当前字段尚未保存密码。'
  } catch (reason: any) {
    error.value = reason.message || '读取密码失败'
  } finally {
    revealingPasswords[key] = false
  }
}

/**
 * 处理 valueToForm 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function valueToForm(field: ResourceField, value: any) {
  if (field.type === 'json') return JSON.stringify(value ?? {}, null, 2)
  if (field.type === 'multiselect') return Array.isArray(value) ? value.map((item) => String(item)) : []
  if (field.type === 'file') return null
  if (field.type === 'statusSwitch') return value !== 'disabled'
  if (field.type === 'select' && field.optionEndpoint) return value === null || value === undefined ? '' : String(value)
  if (field.type === 'list') return Array.isArray(value) ? value.join(', ') : String(value || '')
  return value ?? defaultValue(field)
}

/**
 * 处理 formToValue 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function formToValue(field: ResourceField, value: any) {
  if (field.type === 'number') return Number(value || 0)
  if (field.type === 'checkbox') return Boolean(value)
  if (field.type === 'statusSwitch') return value ? 'enabled' : 'disabled'
  if (field.type === 'json') return value ? JSON.parse(value) : {}
  if (field.type === 'select' && field.optionEndpoint) return /^\d+$/.test(String(value)) ? Number(value) : value
  if (field.type === 'multiselect') return (Array.isArray(value) ? value : []).map((item) => (/^\d+$/.test(String(item)) ? Number(item) : item))
  if (field.type === 'list') return String(value || '').split(',').map((item) => item.trim()).filter(Boolean)
  return value
}

/**
 * 处理 display 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function display(value: any) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const statusText: Record<string, string> = {
  enabled: '可用',
  disabled: '已禁用',
  unavailable: '不可用',
  pending: '待发送',
  sent: '已发送',
  success: '发送成功',
  failed: '发送失败',
  opened: '已打开',
  clicked: '已点击',
  reported: '已上报',
  draft: '草稿',
  scheduled: '已计划',
  queued: '队列中',
  running: '发送中',
  sending: '发送中',
  completed: '已完成',
  cancelled: '已取消',
  paused: '已暂停',
  round_robin: '逐封轮换账号',
  batch: '连续发送',
  single: '单账号优先',
  available: '可用',
  configured: '已配置',
  unconfigured: '未配置',
  not_tested: '未测试',
  approved: '已通过',
  rejected: '已拒绝',
  online: '在线',
  offline: '离线',
  tcp: 'TCP',
  udp: 'UDP',
  http: 'HTTP',
  https: 'HTTPS',
  stcp: 'STCP',
  xtcp: 'XTCP',
}

/**
 * 处理 fieldForColumn 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function fieldForColumn(key: string) {
  return props.schema.fields.find((field) => field.key === key)
}

/**
 * 处理 optionLabel 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function optionLabel(field: ResourceField | undefined, value: any) {
  if (!field) return ''
  if (field.type === 'statusSwitch') return value === 'disabled' || value === false ? '禁用' : '启用'
  const option = fieldOptions(field).find(([optionValue]) => String(optionValue) === String(value))
  return option?.[1] || ''
}

/**
 * 处理 displayCell 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function displayCell(item: any, key: string) {
  const value = item[key]
  const field = fieldForColumn(key)
  const label = optionLabel(field, value)
  if (label) return label
  if (key === 'status' || key === 'mode') return statusText[String(value)] || display(value)
  return display(value)
}

/**
 * 将 FRP 审计动作转换为便于阅读的中文名称。
 * 参数：`value` 为后端返回的审计动作标识。
 * 返回：返回“资源类型 · 操作”的展示文本。
 * 副作用：无。
 */
function auditActionLabel(value: any) {
  const raw = String(value || '')
  const parts = raw.split('.')
  const resource = parts.at(-2) || ''
  const action = parts.at(-1) || raw
  const resourceLabels: Record<string, string> = {
    FrpServer: '服务端',
    FrpAgent: '客户端',
    FrpProxy: '隧道',
  }
  const actionLabels: Record<string, string> = {
    create: '新增',
    update: '编辑',
    delete: '删除',
    test: '测试',
    enable: '启用',
    disable: '禁用',
    sync_runtime: '同步客户端',
    sync_proxies: '同步端口',
    add_proxy: '新增端口',
  }
  const actionText = actionLabels[action] || action
  return resourceLabels[resource] ? `${resourceLabels[resource]} · ${actionText}` : actionText
}

/**
 * 返回 FRP 审计动作对应的视觉色调。
 * 参数：`value` 为审计动作标识。
 * 返回：返回用于样式分类的色调名称。
 * 副作用：无。
 */
function auditActionTone(value: any) {
  const action = String(value || '').split('.').at(-1) || ''
  if (action.includes('delete') || action.includes('disable')) return 'danger'
  if (action.includes('create') || action.includes('add')) return 'create'
  if (action.includes('update')) return 'update'
  if (action.includes('sync')) return 'sync'
  if (action.includes('test')) return 'test'
  if (action.includes('enable')) return 'enable'
  return 'default'
}

/**
 * 处理 isStatusColumn 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function isStatusColumn(key: string) {
  const field = fieldForColumn(key)
  return key === 'status' || key.endsWith('_status') || field?.type === 'statusSwitch'
}

/**
 * 处理 statusClass 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function statusClass(value: any) {
  const normalized = String(value ?? '').toLowerCase()
  if (['enabled', 'active', 'success', 'sent', 'opened', 'clicked', 'reported', 'completed', 'true'].includes(normalized)) return 'status-available'
  if (['available', 'online', 'approved'].includes(normalized)) return 'status-available'
  if (['configured', 'scheduled', 'queued', 'running', 'sending'].includes(normalized)) return 'status-configured'
  if (['pending', 'draft', 'not_tested', 'unconfigured'].includes(normalized)) return 'status-unconfigured'
  if (['failed', 'unavailable', 'error', 'rejected'].includes(normalized)) return 'status-unavailable'
  if (['disabled', 'offline', 'cancelled', 'paused', 'false'].includes(normalized)) return 'status-disabled'
  return 'status-default'
}

/**
 * 处理 columnContentLength 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function columnContentLength(key: string, label: string) {
  const values = filtered.value.slice(0, 30).map((item) => displayCell(item, key))
  return Math.max(label.length, ...values.map((value) => String(value).length), 0)
}

/**
 * 处理 columnGridTrack 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function columnGridTrack(column: ResourceColumn, index: number) {
  const key = columnKey(column)
  const label = columnLabel(column)
  const field = fieldForColumn(key)
  const length = columnContentLength(key, label)
  if (props.schema.compactTable) return compactColumnGridTrack(key, field, length, index)
  if (key === 'status' || field?.type === 'statusSwitch') return { track: '96px', min: 96 }
  if (field?.type === 'number' || key.includes('count') || key.includes('total') || key.includes('rate')) return { track: '88px', min: 88 }
  if (key.includes('email')) return { track: 'minmax(190px, .95fr)', min: 190 }
  if (key.includes('time') || key.endsWith('_at')) return { track: 'minmax(156px, .72fr)', min: 156 }
  if (key.includes('smtp') || key.includes('host')) return { track: 'minmax(130px, .58fr)', min: 130 }
  if (key.includes('subject') || key.includes('description') || key.includes('template')) return { track: 'minmax(180px, 1fr)', min: 180 }
  if (index === 0) return { track: `minmax(${Math.min(Math.max(150, length * 14), 210)}px, 1.05fr)`, min: Math.min(Math.max(150, length * 14), 210) }
  return { track: `minmax(${Math.min(Math.max(112, length * 12), 180)}px, .72fr)`, min: Math.min(Math.max(112, length * 12), 180) }
}

/**
 * 处理 compactColumnGridTrack 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function compactColumnGridTrack(key: string, field: ResourceField | undefined, length: number, index: number) {
  const fill = Boolean(props.schema.compactTableFill)
  /** 根据最小宽度和比例生成紧凑表格列宽。 */
  const track = (min: number, fr = 1) => ({ track: fill ? `minmax(${min}px, ${fr}fr)` : `${min}px`, min })
  if (isFrpAuditResource.value) {
    if (key === 'created_at') return track(180, 1.15)
    if (key === 'actor') return track(130, .9)
    if (key === 'action') return track(150, 1)
    if (key === 'resource') return track(170, 1.1)
    if (key === 'ip_address') return track(130, .9)
  }
  if (key === 'status' || key.endsWith('_status') || field?.type === 'statusSwitch') return track(68, .62)
  if (field?.type === 'checkbox' || key.startsWith('is_') || key.endsWith('_enabled')) return track(46, .42)
  if (field?.type === 'number' || key.includes('count') || key.includes('total') || key.includes('port') || key.includes('rate')) return track(54, .5)
  if (key.includes('time') || key.endsWith('_at')) return track(132, .95)
  if (key.includes('host') || key.includes('ip') || key.includes('addr')) return track(100, .8)
  if (key.includes('source')) return track(82, .7)
  const width = Math.min(Math.max(index === 0 ? 86 : 66, length * 8 + 14), index === 0 ? 116 : 96)
  return track(width, index === 0 ? 1.05 : .78)
}

/**
 * 处理 columnKey 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function columnKey(column: ResourceColumn) {
  return Array.isArray(column) ? column[0] : column
}

/**
 * 处理 columnLabel 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function columnLabel(column: ResourceColumn) {
  return Array.isArray(column) ? column[1] : column
}

/**
 * 处理 rowTitle 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function rowTitle(item: any) {
  return item.title || item.name || item.key || item.cve_id || item.package_id || item.team || item.target || `记录 #${item.id ?? ''}`
}

/**
 * 处理 rowId 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function rowId(item: any) {
  return item[props.schema.idKey || 'id']
}

/**
 * 处理 isRowSelected 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function isRowSelected(item: any) {
  return selectedIds.value.includes(rowId(item))
}

/**
 * 处理 setRowSelected 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function setRowSelected(item: any, checked: boolean) {
  const id = rowId(item)
  if (id === undefined || id === null) return
  selectedIds.value = checked
    ? Array.from(new Set([...selectedIds.value, id]))
    : selectedIds.value.filter((selectedId) => selectedId !== id)
}

/**
 * 处理 toggleAllFiltered 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function toggleAllFiltered(checked: boolean) {
  const ids = visibleSelectableIds.value
  selectedIds.value = checked
    ? Array.from(new Set([...selectedIds.value, ...ids]))
    : selectedIds.value.filter((id) => !ids.includes(id))
}

/**
 * 处理 fieldOptions 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function fieldOptions(field: ResourceField) {
  return field.options || dynamicOptions[field.key] || []
}

/**
 * 处理 selectedOptionValues 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function selectedOptionValues(value: any) {
  return (Array.isArray(value) ? value : []).map((item) => String(item))
}

/**
 * 处理 selectedOptionsText 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function selectedOptionsText(field: ResourceField, value: any) {
  const selected = selectedOptionValues(value)
  if (!selected.length) return field.placeholder || '请选择'
  const labels = fieldOptions(field).filter(([optionValue]) => selected.includes(String(optionValue))).map(([, label]) => label)
  return labels.length ? labels.join('、') : field.placeholder || '请选择'
}

/**
 * 处理 toggleMultiSelect 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function toggleMultiSelect(key: string) {
  openMultiSelects[key] = !openMultiSelects[key]
}

/**
 * 处理 toggleMultiOption 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function toggleMultiOption(target: Record<string, any>, field: ResourceField, optionValue: string, checked: boolean) {
  const current = selectedOptionValues(target[field.key])
  target[field.key] = checked
    ? Array.from(new Set([...current, String(optionValue)]))
    : current.filter((item) => item !== String(optionValue))
}

/**
 * 处理 optionText 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function optionText(item: Record<string, any>, labelKey?: string) {
  if (labelKey && item[labelKey] !== undefined && item[labelKey] !== null && item[labelKey] !== '') return String(item[labelKey])
  return rowTitle(item)
}

/**
 * 处理 loadFieldOptions 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
async function loadFieldOptions(field: ResourceField) {
  if (!field.optionEndpoint || dynamicOptions[field.key]) return
  const connector = field.optionEndpoint.includes('?') ? '&' : '?'
  const result = await api(`${field.optionEndpoint}${connector}page_size=100`)
  const rows = Array.isArray(result) ? result : (result.results || [])
  dynamicOptions[field.key] = rows.map((item: Record<string, any>) => [
    String(item[field.optionValue || 'id']),
    optionText(item, field.optionLabel),
  ])
}

/**
 * 处理 loadActionOptions 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function loadActionOptions(action: ResourceAction) {
  for (const field of action.fields || []) {
    if (field.optionEndpoint) loadFieldOptions(field).catch((reason) => { actionResult.value = reason.message })
  }
}

/**
 * 处理 loadSchemaOptions 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function loadSchemaOptions() {
  for (const field of props.schema.fields) {
    if (field.optionEndpoint) loadFieldOptions(field).catch((reason) => { actionResult.value = reason.message })
  }
}

/**
 * 处理 formatDateTime 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function formatDateTime(date = new Date()) {
  /** 把单个日期数字补齐为两位文本。 */
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

/**
 * 处理 addressLine 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function addressLine(name?: string, email?: string) {
  const displayName = (name || '').trim()
  const address = (email || '').trim()
  if (displayName && address) return `${displayName} <${address}>`
  return displayName || address || '-'
}

/**
 * 处理 isPreviewAction 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function isPreviewAction(action: ResourceAction) {
  return action.label.includes('预览')
}

/**
 * 处理 sanitizePreviewHtml 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function sanitizePreviewHtml(value: any) {
  return String(value || '')
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/\son\w+="[^"]*"/gi, '')
    .replace(/\son\w+='[^']*'/gi, '')
}

/**
 * 处理 isEmptyHtml 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function isEmptyHtml(value: any) {
  return !String(value || '').replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim()
}

/**
 * 处理 showPreview 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function showPreview(action: ResourceAction, item: any, result: any) {
  previewData.value = result || {}
  previewTitle.value = `预览：${rowTitle(item) || action.label}`
  previewedAt.value = formatDateTime()
  actionModalOpen.value = false
  previewOpen.value = true
}

/**
 * 处理 actionLabel 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function actionLabel(action: ResourceAction, item: any = {}) {
  return action.labelFor ? action.labelFor(item) : action.label
}

/**
 * 处理 actionTone 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function actionTone(label: string) {
  if (label.includes('预览')) return 'preview'
  if (label.includes('克隆') || label.includes('复制')) return 'clone'
  if (label.includes('上传') || label.includes('导入')) return 'upload'
  if (label.includes('测试')) return 'test'
  if (label.includes('启停') || label.includes('启用') || label.includes('停用') || label.includes('禁用')) return 'toggle'
  if (label.includes('重发') || label.includes('重试')) return 'retry'
  if (label.includes('取消') || label.includes('删除')) return 'danger'
  if (label.includes('发送')) return 'send'
  return 'default'
}

/**
 * 处理 actionIcon 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function actionIcon(label: string) {
  if (label.includes('预览')) return Eye
  if (label.includes('查看')) return Eye
  if (label.includes('克隆') || label.includes('复制')) return Copy
  if (label.includes('上传') || label.includes('导入')) return Upload
  if (label.includes('测试')) return TestTube2
  if (label.includes('启停') || label.includes('启用') || label.includes('停用') || label.includes('禁用')) return Power
  if (label.includes('重发') || label.includes('重试')) return RotateCw
  if (label.includes('删除')) return Trash2
  if (label.includes('取消')) return XCircle
  if (label.includes('发送')) return Send
  return Play
}

/**
 * 处理 openCreate 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function openCreate() {
  editing.value = null
  loadSchemaOptions()
  for (const field of props.schema.fields) form[field.key] = defaultValue(field)
  for (const key of Object.keys(revealedSecrets)) delete revealedSecrets[key]
  for (const key of Object.keys(revealedPasswordValues)) delete revealedPasswordValues[key]
  for (const field of props.schema.fields) if (field.type === 'password') {
    visiblePasswords[field.key] = false
    revealingPasswords[field.key] = false
  }
  error.value = ''
  modalOpen.value = true
}

/**
 * 处理 openEdit 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function openEdit(item: any) {
  editing.value = item
  loadSchemaOptions()
  for (const field of props.schema.fields) {
    form[field.key] = valueToForm(field, item[field.key])
    const presenceKey = secretPresenceKey(field.key)
    if (field.type === 'password' && presenceKey && item[presenceKey]) form[field.key] = '********'
  }
  for (const key of Object.keys(revealedSecrets)) delete revealedSecrets[key]
  for (const key of Object.keys(revealedPasswordValues)) delete revealedPasswordValues[key]
  for (const field of props.schema.fields) if (field.type === 'password') {
    visiblePasswords[field.key] = false
    revealingPasswords[field.key] = false
  }
  error.value = ''
  modalOpen.value = true
}

/**
 * 处理 endpointFor 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function endpointFor(item?: any) {
  if (!item) return props.schema.endpoint
  return `${props.schema.endpoint}${item[props.schema.idKey || 'id']}/`
}

/**
 * 处理 templateEndpointFor 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function templateEndpointFor(action: ResourceAction, item: any) {
  if (!action.templateEndpoint) return ''
  return typeof action.templateEndpoint === 'function' ? action.templateEndpoint(item || {}) : action.templateEndpoint
}

/**
 * 处理 saveItem 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
async function saveItem() {
  saving.value = true
  error.value = ''
  try {
    const payload: Record<string, any> = {}
    for (const field of props.schema.fields) {
      if (field.type === 'file') continue
      if (field.type === 'password' && editing.value && field.key in revealedPasswordValues && form[field.key] === revealedPasswordValues[field.key]) continue
      if (field.required && field.type === 'richtext' && isEmptyHtml(form[field.key])) {
        throw new Error(`请填写${field.label}`)
      }
      if (!field.readonly) payload[field.key] = formToValue(field, form[field.key])
    }
    let savedItem: any = editing.value
    if (editing.value) {
      savedItem = await api(endpointFor(editing.value), { method: 'PATCH', body: JSON.stringify(payload) })
    } else {
      const created = await api(endpointFor(), { method: 'POST', body: JSON.stringify(payload) })
      savedItem = created
      if (created.secret_key) actionResult.value = `一次性 SecretKey：${created.secret_key}。请立即保存，后续不会再次显示。`
    }
    for (const field of props.schema.fields) {
      const file = form[field.key]
      if (field.type !== 'file' || !field.uploadEndpoint || !(file instanceof File)) continue
      const data = new FormData()
      data.append(field.fileField || 'file', file)
      const result = await apiForm(field.uploadEndpoint(savedItem), data, { method: 'POST' })
      actionResult.value = `附件已上传：${display(result.name || result.url || 'ok')}`
    }
    modalOpen.value = false
    emit('refresh')
  } catch (reason: any) {
    error.value = reason.message
  } finally {
    saving.value = false
  }
}

/**
 * 处理 askDelete 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function askDelete(item: any) {
  deleting.value = item
  deleteOpen.value = true
}

/**
 * 处理 confirmDelete 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
async function confirmDelete() {
  if (!deleting.value) return
  deletingNow.value = true
  try {
    await api(endpointFor(deleting.value), { method: 'DELETE' })
    deleteOpen.value = false
    deleting.value = null
    emit('refresh')
  } catch (reason: any) {
    actionResult.value = reason.message
  } finally {
    deletingNow.value = false
  }
}

/**
 * 处理 openAction 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function openAction(action: ResourceAction, item: any) {
  if (action.navigateTo) {
    router.push(action.navigateTo(item))
    return
  }
  loadActionOptions(action)
  if (action.requiresSelection && !selectedIds.value.length) {
    actionResult.value = '请选择需要操作的发送记录'
    return
  }
  runningAction.value = action
  actionItem.value = item
  actionFile.value = null
  for (const key of Object.keys(actionForm)) delete actionForm[key]
  for (const field of action.fields || []) actionForm[field.key] = defaultValue(field)
  if (action.fields?.length || action.upload) {
    actionModalOpen.value = true
    return
  }
  if (action.label.includes('删除')) {
    confirmingAction.value = action
    confirmingActionItem.value = item
    actionConfirmOpen.value = true
    return
  }
  runAction(action, item)
}

/**
 * 处理 runAction 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
async function runAction(action: ResourceAction, item: any, extraPayload: Record<string, any> = {}, selection: Array<string | number> = selectedIds.value) {
  if (action.requiresSelection && !selection.length) {
    actionResult.value = '请选择需要操作的发送记录'
    return
  }
  if (!action.endpoint) {
    actionResult.value = '该操作没有可调用接口'
    return
  }
  try {
    const method = action.method || 'POST'
    let result: any
    if (action.upload) {
      if (!actionFile.value) throw new Error('请选择需要上传的文件')
      const data = new FormData()
      data.append(action.fileField || 'file', actionFile.value)
      result = await apiForm(action.endpoint(item), data, { method })
    } else {
      const payload = { ...(action.body ? action.body(item, selection) : {}), ...extraPayload }
      result = await api(action.endpoint(item), {
        method,
        ...(method === 'GET' ? {} : { body: JSON.stringify(payload) }),
      })
    }
    if (isPreviewAction(action)) {
      showPreview(action, item, result)
      return
    }
    actionResult.value = `${actionLabel(action, item)}完成：${display(result.secret_key || result.detail || result.status || result.url || result.created_count || result.token || 'ok')}`
    actionModalOpen.value = false
    if (action.requiresSelection) selectedIds.value = []
    emit('refresh')
  } catch (reason: any) {
    actionResult.value = reason.message
  }
}

/**
 * 处理 confirmAction 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
async function confirmAction() {
  if (!confirmingAction.value) return
  actionConfirmLoading.value = true
  try {
    await runAction(confirmingAction.value, confirmingActionItem.value || {})
    actionConfirmOpen.value = false
    confirmingAction.value = null
    confirmingActionItem.value = null
  } finally {
    actionConfirmLoading.value = false
  }
}

/**
 * 处理 submitAction 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
async function submitAction() {
  if (!runningAction.value || !actionItem.value) return
  const payload: Record<string, any> = {}
  for (const field of runningAction.value.fields || []) payload[field.key] = formToValue(field, actionForm[field.key])
  await runAction(runningAction.value, actionItem.value, payload)
}

/**
 * 处理 downloadActionTemplate 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
async function downloadActionTemplate() {
  if (!runningAction.value) return
  const endpoint = templateEndpointFor(runningAction.value, actionItem.value || {})
  if (!endpoint) return
  downloadingTemplate.value = true
  try {
    const result = await api(endpoint, { method: 'GET' })
    if (!result.url) throw new Error('模板下载地址为空')
    const link = document.createElement('a')
    link.href = result.url
    link.download = result.filename || ''
    link.target = '_blank'
    link.rel = 'noopener'
    document.body.appendChild(link)
    link.click()
    link.remove()
  } catch (reason: any) {
    actionResult.value = reason.message
  } finally {
    downloadingTemplate.value = false
  }
}

/**
 * 处理 onActionFileChange 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function onActionFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  actionFile.value = input.files?.[0] || null
}

/**
 * 处理 onFormFileChange 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function onFormFileChange(field: ResourceField, event: Event) {
  const input = event.target as HTMLInputElement
  form[field.key] = input.files?.[0] || null
}

/**
 * 处理 FRP 列表分页跳转。
 * 参数：`page` 为目标页码。
 * 返回：无显式返回值。
 * 副作用：通知父组件加载目标页数据。
 */
function goPaginationPage(page: number) {
  const target = Math.min(Math.max(1, page), paginationTotalPages.value)
  emit('page', target)
}

/**
 * 处理 FRP 列表分页输入框跳转。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：通知父组件加载输入的目标页数据并清空输入框。
 */
function applyPaginationJump() {
  const target = Number(paginationJumpPage.value)
  if (target >= 1) goPaginationPage(target)
  paginationJumpPage.value = ''
}

watch(() => props.schema, () => {
  query.value = ''
  selectedIds.value = []
  modalOpen.value = false
  deleteOpen.value = false
  actionModalOpen.value = false
  actionConfirmOpen.value = false
  previewOpen.value = false
  actionResult.value = ''
  for (const key of Object.keys(dynamicOptions)) delete dynamicOptions[key]
  for (const key of Object.keys(openMultiSelects)) delete openMultiSelects[key]
  loadSchemaOptions()
})

loadSchemaOptions()
</script>

<template>
  <div class="crud-page" :class="{ 'frp-crud-page': isFrpResource, 'frp-audit-page': isFrpAuditResource }">
    <section class="crud-panel">
      <div v-if="!isFrpResource" class="section-head">
        <div v-if="!isFrpResource">
          <h2>{{ schema.title }}</h2>
          <p>{{ schema.description }}</p>
        </div>
        <div class="row-actions">
          <template v-for="action in schema.collectionActions || []" :key="action.label">
            <button
              v-if="canExecute"
              class="action-button"
              :class="`action-${actionTone(actionLabel(action))}`"
              type="button"
              :title="action.requiresSelection && !selectedIds.length ? '请先选择发送记录' : actionLabel(action)"
              :disabled="action.requiresSelection && !selectedIds.length"
              @click="openAction(action, {})"
            >
              <component :is="actionIcon(actionLabel(action))" :size="15" />
              <span>{{ actionLabel(action) }}</span>
            </button>
          </template>
          <button v-if="!schema.readonly && canCreate" class="primary" type="button" @click="openCreate"><Plus :size="16" />新增</button>
          <button class="icon-button" title="刷新" type="button" @click="emit('refresh')"><RefreshCw :size="16" /></button>
        </div>
      </div>

      <div class="toolbar" :class="{ 'frp-crud-toolbar': isFrpResource }">
        <template v-if="isFrpResource">
          <template v-for="action in schema.collectionActions || []" :key="action.label">
            <button
              v-if="canExecute"
              class="action-button"
              :class="`action-${actionTone(actionLabel(action))}`"
              type="button"
              :title="action.requiresSelection && !selectedIds.length ? '请先选择发送记录' : actionLabel(action)"
              :disabled="action.requiresSelection && !selectedIds.length"
              @click="openAction(action, {})"
            >
              <component :is="actionIcon(actionLabel(action))" :size="15" />
              <span>{{ actionLabel(action) }}</span>
            </button>
          </template>
          <button v-if="!schema.readonly && canCreate" class="primary frp-toolbar-create" type="button" @click="openCreate"><Plus :size="16" />新增</button>
          <div class="search-box frp-toolbar-search">
            <Search :size="16" />
            <input v-model="query" :placeholder="schema.searchPlaceholder || '搜索当前资源'" />
          </div>
          <button class="icon-button frp-toolbar-refresh" title="刷新" type="button" @click="emit('refresh')"><RefreshCw :size="16" /></button>
        </template>
        <template v-else>
          <div>
            <Search :size="16" />
            <input v-model="query" :placeholder="schema.searchPlaceholder || '搜索当前资源'" />
          </div>
          <span class="toolbar-count">{{ selectionHint }}</span>
        </template>
      </div>
      <p v-if="actionResult" class="form-hint">{{ actionResult }}</p>

      <div class="crud-table" :class="{ 'compact-table': schema.compactTable, 'fill-table': schema.compactTableFill, 'frp-audit-table': isFrpAuditResource }">
        <div class="crud-row dynamic-layout crud-header" :style="tableGridStyle">
          <span v-if="isSelectable" class="select-cell">
            <input type="checkbox" :checked="allFilteredSelected" :disabled="!visibleSelectableIds.length" title="全选当前列表" @change="toggleAllFiltered(($event.target as HTMLInputElement).checked)" />
          </span>
          <span v-for="column in schema.columns" :key="columnKey(column)">{{ columnLabel(column) }}</span>
          <span v-if="showActionColumn" class="action-column-head">操作</span>
        </div>
        <div v-for="item in filtered" :key="item.id || rowTitle(item)" class="crud-row dynamic-layout" :style="tableGridStyle">
          <span v-if="isSelectable" class="select-cell">
            <input type="checkbox" :checked="isRowSelected(item)" :title="`选择 ${rowTitle(item)}`" @change="setRowSelected(item, ($event.target as HTMLInputElement).checked)" />
          </span>
          <span v-for="column in schema.columns" :key="columnKey(column)" :class="`crud-cell-${columnKey(column)}`">
            <span v-if="isStatusColumn(columnKey(column))" class="badge crud-status-badge" :class="statusClass(item[columnKey(column)])" :title="displayCell(item, columnKey(column))">
              {{ displayCell(item, columnKey(column)) }}
            </span>
            <span v-else-if="isFrpAuditResource && columnKey(column) === 'actor'" class="frp-audit-actor">
              <i>{{ String(item.actor || '?').slice(0, 1).toUpperCase() }}</i>
              <small>{{ displayCell(item, columnKey(column)) }}</small>
            </span>
            <span v-else-if="isFrpAuditResource && columnKey(column) === 'action'" class="frp-audit-action" :class="`tone-${auditActionTone(item.action)}`" :title="displayCell(item, columnKey(column))">
              {{ auditActionLabel(item.action) }}
            </span>
            <span v-else-if="isFrpAuditResource && columnKey(column) === 'resource'" class="frp-audit-resource">{{ displayCell(item, columnKey(column)) }}</span>
            <code v-else-if="isFrpAuditResource && columnKey(column) === 'ip_address'" class="frp-audit-ip">{{ displayCell(item, columnKey(column)) }}</code>
            <strong v-else-if="columnKey(column) === firstColumnKey">{{ displayCell(item, columnKey(column)) }}</strong>
            <small v-else>{{ displayCell(item, columnKey(column)) }}</small>
          </span>
          <span v-if="showActionColumn" class="row-actions">
            <template v-for="action in schema.actions || []" :key="action.label">
              <button v-if="canRunAction(action)" class="action-button" :class="`action-${actionTone(actionLabel(action, item))}`" :title="actionLabel(action, item)" @click="openAction(action, item)">
                <component :is="actionIcon(actionLabel(action, item))" :size="15" />
                <span>{{ actionLabel(action, item) }}</span>
              </button>
            </template>
            <button v-if="!schema.readonly && canUpdate" class="action-button action-edit" title="编辑" @click="openEdit(item)"><Edit3 :size="15" /><span>编辑</span></button>
            <button v-if="!schema.readonly && canDelete" title="删除" class="action-button action-danger danger" @click="askDelete(item)"><Trash2 :size="15" /><span>删除</span></button>
          </span>
        </div>
      </div>

      <CrudPagination
        v-if="showPagination && !isFrpPaginatedResource"
        :page="paginationPage"
        :page-size="paginationPageSize"
        :total="paginationTotal"
        @go="emit('page', $event)"
      />
      <PaginationBar
        v-if="isFrpPaginatedResource && paginationTotal"
        v-model:jump-page="paginationJumpPage"
        :page-size="paginationPageSize"
        :current-page="paginationPage"
        :total-pages="paginationTotalPages"
        :page-start="paginationPageStart"
        :page-end="paginationPageEnd"
        :total="paginationTotal"
        @go="goPaginationPage"
        @move="goPaginationPage(paginationPage + $event)"
        @jump="applyPaginationJump"
      />
    </section>

    <ModalDialog :open="modalOpen" :title="editing ? `编辑${schema.title}` : `新增${schema.title}`" :description="schema.description" :width="formDialogWidth" :dialog-class="formDialogClass" @close="modalOpen = false">
      <form class="form-grid" :class="{ 'template-editor-form': hasRichTextForm, 'phishing-editor-form': hasPhishingForm, 'frp-resource-form': isFrpResource, 'frp-server-form': isFrpServerResource }" @submit.prevent="saveItem">
        <label v-for="field in schema.fields" :key="field.key" :class="{ wide: field.type === 'textarea' || field.type === 'json' || field.type === 'richtext' || field.type === 'multiselect', 'file-field': field.type === 'file', 'checkbox-field': field.type === 'checkbox' || field.type === 'statusSwitch', 'frp-server-control-field': isFrpServerResource && ['allow_register', 'max_agents', 'status'].includes(field.key) }">
          {{ field.label }}
          <textarea v-if="field.type === 'textarea' || field.type === 'json'" v-model="form[field.key]" :required="field.required" :placeholder="field.placeholder" :disabled="field.readonly" />
          <RichTextEditor v-else-if="field.type === 'richtext'" v-model="form[field.key]" :disabled="field.readonly" />
          <select v-else-if="field.type === 'select'" v-model="form[field.key]" :required="field.required" :disabled="field.readonly">
            <option v-if="field.optionEndpoint" value="">{{ field.placeholder || '--------' }}</option>
            <option v-for="[value, label] in fieldOptions(field)" :key="String(value)" :value="value">{{ label }}</option>
          </select>
          <span v-else-if="field.type === 'multiselect'" class="multi-check-select">
            <button type="button" :disabled="field.readonly" @click="toggleMultiSelect(field.key)">
              <span>{{ selectedOptionsText(field, form[field.key]) }}</span>
              <span>⌄</span>
            </button>
            <span v-if="openMultiSelects[field.key]" class="multi-check-options">
              <label v-for="[value, label] in fieldOptions(field)" :key="String(value)">
                <input type="checkbox" :checked="selectedOptionValues(form[field.key]).includes(String(value))" :disabled="field.readonly" @change="toggleMultiOption(form, field, String(value), ($event.target as HTMLInputElement).checked)" />
                <span>{{ label }}</span>
              </label>
            </span>
          </span>
          <input v-else-if="field.type === 'checkbox'" v-model="form[field.key]" class="checkbox-input" type="checkbox" :disabled="field.readonly" />
          <span v-else-if="field.type === 'statusSwitch'" class="status-switch-field">
            <input v-model="form[field.key]" type="checkbox" :disabled="field.readonly" />
            <span></span>
            <em>{{ form[field.key] ? '启用' : '禁用' }}</em>
          </span>
          <span v-else-if="field.type === 'password'" class="secret-input">
            <input v-model="form[field.key]" :type="visiblePasswords[field.key] ? 'text' : 'password'" :required="field.required" :placeholder="field.placeholder" :disabled="field.readonly" autocomplete="new-password" spellcheck="false" />
            <button v-if="!editing || !isFrpResource || canReveal" class="icon-button secret-visibility-button" type="button" :title="visiblePasswords[field.key] ? '隐藏密码' : '查看密码'" :disabled="revealingPasswords[field.key]" @click="togglePassword(field.key)">
              <EyeOff v-if="visiblePasswords[field.key]" :size="16" />
              <Eye v-else :size="16" />
            </button>
          </span>
          <span v-else-if="field.type === 'file'" class="file-input-wrap">
            <input type="file" :disabled="field.readonly" @change="onFormFileChange(field, $event)" />
            <small v-if="editing?.attachment_name">当前附件：{{ editing.attachment_name }}</small>
          </span>
          <input v-else v-model="form[field.key]" :type="field.type === 'number' ? 'number' : 'text'" :required="field.required" :placeholder="field.placeholder" :disabled="field.readonly" />
        </label>
        <p v-if="error" class="form-error">{{ error }}</p>
        <footer>
          <button class="secondary" type="button" @click="modalOpen = false">取消</button>
          <button class="primary" :disabled="saving">{{ saving ? '保存中' : '保存' }}</button>
        </footer>
      </form>
    </ModalDialog>

    <ConfirmDialog
      :open="deleteOpen"
      :title="`删除${schema.title}`"
      :message="`确认删除 ${rowTitle(deleting || {})}？此操作会写入审计日志。`"
      :loading="deletingNow"
      @cancel="deleteOpen = false"
      @confirm="confirmDelete"
    />

    <ConfirmDialog
      :open="actionConfirmOpen"
      :title="confirmingAction?.label || '确认操作'"
      :message="`确认操作已选择的 ${selectedIds.length} 条记录？此操作会写入审计日志。`"
      confirm-text="确认操作"
      :loading="actionConfirmLoading"
      @cancel="actionConfirmOpen = false"
      @confirm="confirmAction"
    />

    <ModalDialog :open="previewOpen" :title="previewTitle" width="1140px" dialog-class="preview-dialog" @close="previewOpen = false">
      <div class="mail-preview">
        <section class="mail-preview-frame">
          <header class="mail-preview-subject">
            <strong>{{ previewSubject }}</strong>
            <span>★</span>
          </header>
          <div class="mail-preview-summary">
            <div>
              <strong>{{ previewData?.from_name || previewData?.from_email || '-' }}</strong>
              <span>发给 {{ previewData?.to_name || previewData?.to_email || '-' }}</span>
            </div>
            <time>{{ previewedAt }}</time>
          </div>
          <dl class="mail-preview-meta">
            <dt>发件人:</dt>
            <dd>{{ addressLine(previewData?.from_name, previewData?.from_email) }}</dd>
            <dt>收件人:</dt>
            <dd>{{ addressLine(previewData?.to_name, previewData?.to_email) }}</dd>
            <dt>时间:</dt>
            <dd>{{ previewedAt }}</dd>
            <dt>大小:</dt>
            <dd>{{ previewSize }}</dd>
          </dl>
          <div class="mail-preview-body">
            <div v-if="previewHtml" class="mail-preview-html" v-html="previewHtml"></div>
            <pre v-else class="mail-preview-text">{{ previewText }}</pre>
          </div>
        </section>
      </div>
      <template #footer>
        <button class="secondary" type="button" @click="previewOpen = false">关闭</button>
      </template>
    </ModalDialog>

    <ModalDialog :open="actionModalOpen" :title="runningAction?.label || '操作'" :description="rowTitle(actionItem || {})" @close="actionModalOpen = false">
      <form class="form-grid" @submit.prevent="submitAction">
        <div v-if="runningAction?.upload && runningAction?.templateEndpoint" class="action-template-download wide">
          <button class="secondary" type="button" :disabled="downloadingTemplate" @click="downloadActionTemplate">
            <Download :size="16" />
            {{ downloadingTemplate ? '下载中' : (runningAction.templateLabel || '下载模板') }}
          </button>
        </div>
        <label v-if="runningAction?.upload" class="wide">
          文件
          <input type="file" @change="onActionFileChange" />
        </label>
        <label v-for="field in runningAction?.fields || []" :key="field.key" :class="{ wide: field.type === 'textarea' || field.type === 'json' || field.type === 'richtext' || field.type === 'multiselect', 'checkbox-field': field.type === 'checkbox' || field.type === 'statusSwitch' }">
          {{ field.label }}
          <textarea v-if="field.type === 'textarea' || field.type === 'json'" v-model="actionForm[field.key]" :required="field.required" :placeholder="field.placeholder" />
          <RichTextEditor v-else-if="field.type === 'richtext'" v-model="actionForm[field.key]" />
          <select v-else-if="field.type === 'select'" v-model="actionForm[field.key]" :required="field.required">
            <option v-if="field.optionEndpoint" value="">{{ field.placeholder || '--------' }}</option>
            <option v-for="[value, label] in fieldOptions(field)" :key="String(value)" :value="value">{{ label }}</option>
          </select>
          <span v-else-if="field.type === 'multiselect'" class="multi-check-select">
            <button type="button" @click="toggleMultiSelect(`action-${field.key}`)">
              <span>{{ selectedOptionsText(field, actionForm[field.key]) }}</span>
              <span>⌄</span>
            </button>
            <span v-if="openMultiSelects[`action-${field.key}`]" class="multi-check-options">
              <label v-for="[value, label] in fieldOptions(field)" :key="String(value)">
                <input type="checkbox" :checked="selectedOptionValues(actionForm[field.key]).includes(String(value))" @change="toggleMultiOption(actionForm, field, String(value), ($event.target as HTMLInputElement).checked)" />
                <span>{{ label }}</span>
              </label>
            </span>
          </span>
          <input v-else-if="field.type === 'checkbox'" v-model="actionForm[field.key]" class="checkbox-input" type="checkbox" />
          <span v-else-if="field.type === 'statusSwitch'" class="status-switch-field">
            <input v-model="actionForm[field.key]" type="checkbox" />
            <span></span>
            <em>{{ actionForm[field.key] ? '启用' : '禁用' }}</em>
          </span>
          <input v-else v-model="actionForm[field.key]" :type="field.type === 'number' ? 'number' : 'text'" :required="field.required" :placeholder="field.placeholder" />
        </label>
        <footer>
          <button class="secondary" type="button" @click="actionModalOpen = false">取消</button>
          <button class="primary" type="submit">确定</button>
        </footer>
      </form>
    </ModalDialog>
  </div>
</template>
