<script setup lang="ts">
import {
  Building2, ChevronDown, ChevronRight, Copy, Edit3, Eye, Folder, PanelLeftClose, PanelLeftOpen,
  Plus, RefreshCw, Search, ShieldCheck, Trash2,
} from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'

import { api } from '../../../api'
import ConfirmDialog from '../../../components/ConfirmDialog.vue'
import CustomSelect from '../../../components/CustomSelect.vue'
import ModalDialog from '../../../components/ModalDialog.vue'
import { actionPermissionForPath } from '../../../permissions'
import { useAuthStore } from '../../../stores/auth'
import PaginationBar from './PaginationBar.vue'
import PermissionTreeNode from './PermissionTreeNode.vue'
import type { DepartmentRow, PermissionGroup, PermissionPage, PermissionPolicyRow, PermissionRuleRow, UserRow } from './types'
import { displayName, formatDateTime } from './types'
import { usePager } from './usePager'

type RuleEffect = 'allow' | 'deny'
type VisibleDepartment = {
  department: DepartmentRow
  depth: number
  hasChildren: boolean
}

const props = defineProps<{
  users: UserRow[]
  departments: DepartmentRow[]
  policies: PermissionPolicyRow[]
  catalog: PermissionGroup[]
  loading?: boolean
}>()
const emit = defineEmits<{ reload: [] }>()
const auth = useAuthStore()

const canCreate = computed(() => auth.can(actionPermissionForPath('/admin/permissions', 'create')))
const canUpdate = computed(() => auth.can(actionPermissionForPath('/admin/permissions', 'update')))
const canDelete = computed(() => auth.can(actionPermissionForPath('/admin/permissions', 'delete')))

const query = ref('')
const subjectFilter = ref('')
const selectedDepartmentId = ref<number | null>(null)
const expandedDepartmentIds = ref<Set<number>>(new Set())
const knownDepartmentIds = ref<Set<number>>(new Set())
const departmentPanelCollapsed = ref(false)
const modalOpen = ref(false)
const detailModalOpen = ref(false)
const deleteOpen = ref(false)
const editing = ref<PermissionPolicyRow | null>(null)
const detailPolicy = ref<PermissionPolicyRow | null>(null)
const deleting = ref<PermissionPolicyRow | null>(null)
const saving = ref(false)
const deletingNow = ref(false)
const cloningId = ref<number | null>(null)
const error = ref('')
const expandedGroups = ref<Set<string>>(new Set())
const expandedPages = ref<Set<string>>(new Set())

const ruleState = reactive<Record<string, RuleEffect>>({})
const form = reactive({
  name: '',
  subject_type: 'department' as 'department' | 'user',
  department: null as number | null,
  user: null as number | null,
  priority: 50,
  status: 'available' as 'available' | 'disabled',
  remark: '',
})

const departmentById = computed(() => new Map(props.departments.map((department) => [department.id, department])))
const userById = computed(() => new Map(props.users.map((user) => [user.id, user])))
const selectedDepartment = computed(() => (
  selectedDepartmentId.value === null ? null : departmentById.value.get(selectedDepartmentId.value) || null
))
const selectedDepartmentAncestorIds = computed(() => {
  const ancestorIds = new Set<number>()
  let current = selectedDepartment.value
  while (current?.parent_id && !ancestorIds.has(current.parent_id)) {
    ancestorIds.add(current.parent_id)
    current = departmentById.value.get(current.parent_id) || null
  }
  return ancestorIds
})
const departmentChildren = computed(() => {
  const children = new Map<number | null, DepartmentRow[]>()
  props.departments.forEach((department) => {
    const parentId = department.parent_id && departmentById.value.has(department.parent_id) && department.parent_id !== department.id
      ? department.parent_id
      : null
    children.set(parentId, [...(children.get(parentId) || []), department])
  })
  children.forEach((items) => items.sort((left, right) => (
    Number(right.is_default) - Number(left.is_default) || left.name.localeCompare(right.name, 'zh-CN')
  )))
  return children
})
const visibleDepartments = computed<VisibleDepartment[]>(() => {
  const rows: VisibleDepartment[] = []
  const visited = new Set<number>()
  /** 按展开状态递归生成权限策略左侧可见的部门节点。 */
  const append = (parentId: number | null, depth: number) => {
    for (const department of departmentChildren.value.get(parentId) || []) {
      if (visited.has(department.id)) continue
      visited.add(department.id)
      const childItems = departmentChildren.value.get(department.id) || []
      rows.push({ department, depth, hasChildren: childItems.length > 0 })
      if (childItems.length && expandedDepartmentIds.value.has(department.id)) append(department.id, depth + 1)
    }
  }
  append(null, 0)
  props.departments.forEach((department) => {
    if (!visited.has(department.id)) rows.push({ department, depth: 0, hasChildren: false })
  })
  return rows
})
const policyUserOptions = computed(() => props.users.filter((user) => {
  if (selectedDepartment.value?.is_default || selectedDepartment.value?.is_root) return true
  const departmentId = user.department_id ?? user.organization_id
  return departmentId === selectedDepartmentId.value
}))
const departmentPolicies = computed(() => props.policies.filter((policy) => policyBelongsToSelectedDepartment(policy)))
const filteredPolicies = computed(() => departmentPolicies.value.filter((policy) => {
  const text = `${policy.name} ${policy.subject_label} ${policy.remark}`.toLowerCase()
  return (!query.value || text.includes(query.value.toLowerCase()))
    && (!subjectFilter.value || policy.subject_type === subjectFilter.value)
}))
const subjectCounts = computed(() => {
  const counts = { department: 0, user: 0 }
  departmentPolicies.value.forEach((policy) => { counts[policy.subject_type] += 1 })
  return counts
})
const authorizationModeCounts = computed(() => {
  const counts = { direct: 0, inherited: 0 }
  departmentPolicies.value.forEach((policy) => { counts[authorizationMode(policy)] += 1 })
  return counts
})

const {
  pageSize, currentPage, jumpPage, totalPages, paginatedItems,
  pageStart, pageEnd, goPage, movePage, applyJump, resetPage,
} = usePager(filteredPolicies, 10)

watch([query, subjectFilter, selectedDepartmentId], resetPage)
watch(() => props.departments, (departments) => {
  const availableIds = new Set(departments.map((department) => department.id))
  const nextExpandedIds = new Set([...expandedDepartmentIds.value].filter((departmentId) => availableIds.has(departmentId)))
  departments.forEach((department) => {
    if (!knownDepartmentIds.value.has(department.id) && department.children_count > 0) nextExpandedIds.add(department.id)
  })
  expandedDepartmentIds.value = nextExpandedIds
  knownDepartmentIds.value = availableIds
  if (selectedDepartmentId.value === null || !availableIds.has(selectedDepartmentId.value)) {
    selectedDepartmentId.value = departments.find((department) => department.is_default)?.id ?? departments[0]?.id ?? null
  }
}, { immediate: true, deep: true })

/** 返回策略授权对象实际所属的部门编号。 */
function policyDepartmentId(policy: PermissionPolicyRow) {
  if (policy.subject_type === 'department') return policy.department ?? null
  const user = policy.user ? userById.value.get(policy.user) : null
  return user?.department_id ?? user?.organization_id ?? null
}

/** 判断策略是否直接归属于当前部门或从当前部门上级继承；默认组织展示全部策略。 */
function policyBelongsToSelectedDepartment(policy: PermissionPolicyRow) {
  if (selectedDepartment.value?.is_default || selectedDepartment.value?.is_root) return true
  const departmentId = policyDepartmentId(policy)
  if (departmentId === selectedDepartmentId.value) return true
  return policy.subject_type === 'department'
    && departmentId !== null
    && selectedDepartmentAncestorIds.value.has(departmentId)
}

/** 统计指定部门直接策略、个人策略以及从全部上级部门继承的策略数量。 */
function departmentPolicyCount(department: DepartmentRow) {
  if (department.is_default || department.is_root) return props.policies.length
  const effectiveDepartmentIds = new Set([department.id])
  let current = department
  while (current.parent_id && !effectiveDepartmentIds.has(current.parent_id)) {
    effectiveDepartmentIds.add(current.parent_id)
    const parent = departmentById.value.get(current.parent_id)
    if (!parent) break
    current = parent
  }
  return props.policies.filter((policy) => {
    const departmentId = policyDepartmentId(policy)
    if (policy.subject_type === 'user') return departmentId === department.id
    return departmentId !== null && effectiveDepartmentIds.has(departmentId)
  }).length
}

/** 选中部门并让右侧策略列表切换到对应组织范围。 */
function selectDepartment(departmentId: number) {
  selectedDepartmentId.value = departmentId
}

/** 切换权限策略左侧单个部门节点的展开状态。 */
function toggleDepartment(departmentId: number) {
  const next = new Set(expandedDepartmentIds.value)
  if (next.has(departmentId)) next.delete(departmentId)
  else next.add(departmentId)
  expandedDepartmentIds.value = next
}

/** 切换权限策略组织架构面板的展开和折叠状态。 */
function toggleDepartmentPanel() {
  departmentPanelCollapsed.value = !departmentPanelCollapsed.value
}

/** 返回策略授权类型的用户友好名称。 */
function authorizationTypeLabel(policy: PermissionPolicyRow) {
  return policy.subject_type === 'department' ? '部门' : '个人'
}

/** 返回部门名称或个人姓名作为策略授权对象。 */
function authorizationTargetName(policy: PermissionPolicyRow) {
  if (policy.subject_type === 'department') return policy.subject_name
  const user = policy.user ? userById.value.get(policy.user) : null
  return user ? displayName(user) : policy.subject_name
}

/** 返回策略相对当前查看部门的授权模式。 */
function authorizationMode(policy: PermissionPolicyRow): 'direct' | 'inherited' {
  if (selectedDepartment.value?.is_default || selectedDepartment.value?.is_root) return 'direct'
  if (policy.subject_type === 'department' && policy.department !== selectedDepartmentId.value) return 'inherited'
  return 'direct'
}

/** 返回直接授权或继承授权的中文名称。 */
function authorizationModeLabel(policy: PermissionPolicyRow) {
  return authorizationMode(policy) === 'inherited' ? '继承授权' : '直接授权'
}

/** 打开权限策略只读详情弹窗。 */
function openPolicyDetail(policy: PermissionPolicyRow) {
  detailPolicy.value = policy
  detailModalOpen.value = true
}

const allPermissionCodes = computed(() => {
  const codes: string[] = []
  for (const group of props.catalog) {
    codes.push(group.code)
    for (const page of group.pages || []) collectPageCodes(page, codes)
  }
  return codes
})
const permissionLabelByCode = computed(() => {
  const labels = new Map<string, string>()
  /** 递归记录页面及操作权限代码对应的中文名称。 */
  const appendPage = (page: PermissionPage, groupName: string) => {
    labels.set(page.code, `${groupName} / ${page.name}`)
    for (const action of page.actions || []) labels.set(actionCode(page, action.code), `${page.name} / ${action.name}`)
    for (const child of page.children || []) appendPage(child, groupName)
  }
  for (const group of props.catalog) {
    labels.set(group.code, group.name)
    for (const page of group.pages || []) appendPage(page, group.name)
  }
  return labels
})

/**
 * 根据页面权限代码和操作代码生成完整操作权限代码。
 * 参数：`page` 表示该步骤所需的业务参数；`action` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function actionCode(page: PermissionPage, action: string) {
  return `${page.code.replace(/\.view$/, '')}.${action}`
}

/**
 * 计算并返回 collectPageCodes 对应的业务数据。
 * 参数：`page` 表示该步骤所需的业务参数；`codes` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function collectPageCodes(page: PermissionPage, codes: string[]) {
  codes.push(page.code)
  for (const action of page.actions || []) codes.push(actionCode(page, action.code))
  for (const child of page.children || []) collectPageCodes(child, codes)
}

/**
 * 以默认拒绝为基础重建权限策略编辑状态。
 * 参数：`rules` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function resetRuleState(rules: PermissionRuleRow[] = []) {
  for (const key of Object.keys(ruleState)) delete ruleState[key]
  for (const code of allPermissionCodes.value) ruleState[code] = 'deny'
  const validCodes = new Set(allPermissionCodes.value)
  for (const rule of rules) {
    if (validCodes.has(rule.permission_code)) ruleState[rule.permission_code] = rule.effect
  }
}

/**
 * 封装 expandInitialTree 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`rules` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function expandInitialTree(rules: PermissionRuleRow[] = []) {
  const groupCodes = new Set<string>()
  const pageCodes = new Set<string>()
  const configured = new Set(rules.map((rule) => rule.permission_code))

  for (const group of props.catalog) {
    const groupTouched = configured.has(group.code)
    const hasConfiguredChild = (group.pages || []).some((page) => markExpandedPage(page, configured, pageCodes))
    if (groupTouched || hasConfiguredChild || groupCodes.size < 1) groupCodes.add(group.code)
  }

  expandedGroups.value = groupCodes
  expandedPages.value = pageCodes
}

/**
 * 封装 markExpandedPage 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`page` 表示该步骤所需的业务参数；`configured` 表示该步骤所需的业务参数；`pageCodes` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function markExpandedPage(page: PermissionPage, configured: Set<string>, pageCodes: Set<string>) {
  const pageTouched = configured.has(page.code) || (page.actions || []).some((action) => configured.has(actionCode(page, action.code)))
  const childTouched = (page.children || []).some((child) => markExpandedPage(child, configured, pageCodes))
  if (pageTouched || childTouched) pageCodes.add(page.code)
  return pageTouched || childTouched
}

/**
 * 将 resetForm 管理的界面或业务状态恢复到初始值。
 * 参数：`policy` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function resetForm(policy?: PermissionPolicyRow) {
  editing.value = policy || null
  Object.assign(form, {
    name: policy?.name || '',
    subject_type: policy?.subject_type || 'department',
    department: policy?.department ?? selectedDepartmentId.value ?? props.departments[0]?.id ?? null,
    user: policy?.user ?? policyUserOptions.value[0]?.id ?? props.users[0]?.id ?? null,
    priority: policy?.priority ?? 50,
    status: policy?.status || 'available',
    remark: policy?.remark || '',
  })
  resetRuleState(policy?.rules || [])
  expandInitialTree(policy?.rules || [])
  error.value = ''
}

/**
 * 准备 openCreate 所需数据并打开对应交互界面。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function openCreate() {
  resetForm()
  modalOpen.value = true
}

/**
 * 准备 openEdit 所需数据并打开对应交互界面。
 * 参数：`policy` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function openEdit(policy: PermissionPolicyRow) {
  resetForm(policy)
  modalOpen.value = true
}

/**
 * 封装 clonePolicy 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`policy` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
async function clonePolicy(policy: PermissionPolicyRow) {
  cloningId.value = policy.id
  error.value = ''
  try {
    await api(`/permission-policies/${policy.id}/clone/`, {
      method: 'POST',
      body: JSON.stringify({ name: `${policy.name} 副本` }),
    })
    emit('reload')
  } catch (reason: any) {
    error.value = reason.message || '克隆权限策略失败'
  } finally {
    cloningId.value = null
  }
}

/**
 * 封装 policyRules 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function policyRules() {
  const validCodes = new Set(allPermissionCodes.value)
  return Object.entries(ruleState)
    .filter(([permission_code]) => validCodes.has(permission_code))
    .map(([permission_code, effect]) => ({ permission_code, effect }))
}

/**
 * 校验当前输入并完成 savePolicy 对应的数据保存操作。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function savePolicy() {
  saving.value = true
  error.value = ''
  try {
    const payload = {
      name: form.name,
      subject_type: form.subject_type,
      department: form.subject_type === 'department' ? form.department : null,
      user: form.subject_type === 'user' ? form.user : null,
      priority: Number(form.priority) || 50,
      status: form.status,
      remark: form.remark,
      rules: policyRules(),
    }
    if (editing.value) {
      await api(`/permission-policies/${editing.value.id}/`, { method: 'PATCH', body: JSON.stringify(payload) })
    } else {
      await api('/permission-policies/', { method: 'POST', body: JSON.stringify(payload) })
    }
    modalOpen.value = false
    emit('reload')
  } catch (reason: any) {
    error.value = reason.message || '保存权限策略失败'
  } finally {
    saving.value = false
  }
}

/**
 * 处理 askDelete 对应的确认交互，并在确认后执行目标操作。
 * 参数：`policy` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function askDelete(policy: PermissionPolicyRow) {
  deleting.value = policy
  deleteOpen.value = true
}

/**
 * 处理 confirmDelete 对应的确认交互，并在确认后执行目标操作。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function confirmDelete() {
  if (!deleting.value) return
  deletingNow.value = true
  try {
    await api(`/permission-policies/${deleting.value.id}/`, { method: 'DELETE' })
    deleteOpen.value = false
    deleting.value = null
    emit('reload')
  } finally {
    deletingNow.value = false
  }
}

/**
 * 封装 statusLabel 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`value` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function statusLabel(value: string) {
  return value === 'available' ? '可用' : '已禁用'
}

/**
 * 封装 subjectTypeLabel 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`value` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function subjectTypeLabel(value: string) {
  return value === 'department' ? '部门' : '用户'
}

/**
 * 封装 effectCount 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`policy` 表示该步骤所需的业务参数；`effect` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function effectCount(policy: PermissionPolicyRow, effect: 'allow' | 'deny') {
  return (policy.rules || []).filter((rule) => rule.effect === effect).length
}

/**
 * 封装 setState 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`code` 表示该步骤所需的业务参数；`state` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function setState(code: string, state: RuleEffect) {
  ruleState[code] = state
}

/**
 * 切换 toggleGroup 对应的界面或业务状态。
 * 参数：`code` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function toggleGroup(code: string) {
  const next = new Set(expandedGroups.value)
  if (next.has(code)) next.delete(code)
  else next.add(code)
  expandedGroups.value = next
}

/**
 * 切换 togglePage 对应的界面或业务状态。
 * 参数：`code` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function togglePage(code: string) {
  const next = new Set(expandedPages.value)
  if (next.has(code)) next.delete(code)
  else next.add(code)
  expandedPages.value = next
}

/**
 * 判断 isGroupOpen 对应的业务条件是否成立。
 * 参数：`code` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function isGroupOpen(code: string) {
  return expandedGroups.value.has(code)
}

/**
 * 同步设置页面访问权限及页面全部真实操作权限。
 * 参数：`page` 表示该步骤所需的业务参数；`state` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function setPageWithActions(page: PermissionPage, state: RuleEffect) {
  setState(page.code, state)
  for (const action of page.actions || []) setState(actionCode(page, action.code), state)
  for (const child of page.children || []) setPageWithActions(child, state)
}

/**
 * 同步设置菜单组及其全部页面和操作权限。
 * 参数：`group` 表示该步骤所需的业务参数；`state` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function setGroupWithChildren(group: PermissionGroup, state: RuleEffect) {
  setState(group.code, state)
  for (const page of group.pages || []) setPageWithActions(page, state)
}
</script>

<template>
  <section class="governance-page permission-policy-page">
    <div :class="['permission-policy-workspace', { 'department-panel-collapsed': departmentPanelCollapsed }]">
      <aside :class="['permission-policy-department-panel', { collapsed: departmentPanelCollapsed }]">
        <header class="permission-policy-department-head">
          <div v-if="!departmentPanelCollapsed">
            <span>授权组织</span>
            <small>{{ departments.length }} 个部门</small>
          </div>
          <button
            class="icon-button"
            type="button"
            :title="departmentPanelCollapsed ? '展开组织架构' : '折叠组织架构'"
            @click="toggleDepartmentPanel"
          >
            <PanelLeftOpen v-if="departmentPanelCollapsed" :size="17" />
            <PanelLeftClose v-else :size="17" />
          </button>
        </header>
        <div v-if="!departmentPanelCollapsed" class="permission-policy-department-tree">
          <button
            v-for="row in visibleDepartments"
            :key="row.department.id"
            :class="['permission-policy-department-row', { active: selectedDepartmentId === row.department.id }]"
            :style="{ '--permission-department-depth': row.depth }"
            type="button"
            @click="selectDepartment(row.department.id)"
          >
            <span
              :class="['permission-department-expand', { placeholder: !row.hasChildren }]"
              @click.stop="row.hasChildren && toggleDepartment(row.department.id)"
            >
              <ChevronRight :size="14" :class="{ expanded: expandedDepartmentIds.has(row.department.id) }" />
            </span>
            <Building2 v-if="row.department.is_default || row.department.is_root" :size="16" />
            <Folder v-else :size="16" />
            <span class="permission-department-name" :title="row.department.name">{{ row.department.name }}</span>
            <b>{{ departmentPolicyCount(row.department) }}</b>
          </button>
        </div>
      </aside>

      <div class="governance-card permission-policy-card permission-policy-pane">
        <header class="permission-policy-context-head">
          <div>
            <span class="permission-policy-context-icon"><ShieldCheck :size="18" /></span>
            <div>
              <h2>{{ selectedDepartment?.name || '请选择部门' }}</h2>
            </div>
          </div>
          <div class="permission-policy-context-stats">
            <span><b>{{ departmentPolicies.length }}</b> 全部</span>
            <span><b>{{ authorizationModeCounts.direct }}</b> 直接</span>
            <span><b>{{ authorizationModeCounts.inherited }}</b> 继承</span>
            <span><b>{{ subjectCounts.user }}</b> 个人</span>
          </div>
        </header>

        <div class="governance-toolbar permission-policy-toolbar crud-toolbar">
          <button v-if="canCreate" class="primary toolbar-primary-action" type="button" @click="openCreate">
            <Plus :size="16" />&#26032;&#22686;&#26435;&#38480;&#31574;&#30053;
          </button>
          <label class="search-box">
            <Search :size="16" />
            <input v-model="query" placeholder="搜索策略名称、授权对象或备注" />
          </label>
          <div class="toolbar-actions">
            <button class="secondary action-refresh" type="button" :disabled="loading" @click="emit('reload')">
              <RefreshCw :size="16" :class="{ spin: loading }" />刷新
            </button>
          </div>
        </div>

        <nav class="permission-policy-subject-tabs" aria-label="权限策略授权对象筛选">
          <button type="button" :class="{ active: subjectFilter === '' }" @click="subjectFilter = ''">
            全部策略 <b>{{ departmentPolicies.length }}</b>
          </button>
          <button type="button" :class="{ active: subjectFilter === 'department' }" @click="subjectFilter = 'department'">
            部门授权 <b>{{ subjectCounts.department }}</b>
          </button>
          <button type="button" :class="{ active: subjectFilter === 'user' }" @click="subjectFilter = 'user'">
            个人授权 <b>{{ subjectCounts.user }}</b>
          </button>
        </nav>

        <div class="governance-table permission-policy-table">
          <div class="governance-table-row table-head">
            <span class="sequence-col">序号</span>
            <span>策略名称</span>
            <span>授权类型</span>
            <span>授权模式</span>
            <span>授权部门/个人</span>
            <span>允许</span>
            <span>拒绝</span>
            <span>优先级</span>
            <span>状态</span>
            <span>更新时间</span>
            <span>操作</span>
          </div>
          <div
            v-for="(policy, rowIndex) in paginatedItems"
            :key="policy.id"
            :class="['governance-table-row', 'permission-policy-list-row', { 'inherited-policy-row': authorizationMode(policy) === 'inherited' }]"
          >
            <span class="sequence-col">{{ (currentPage - 1) * pageSize + rowIndex + 1 }}</span>
            <span class="permission-policy-name-static">
              <strong>{{ policy.name }}</strong>
              <small v-if="policy.remark">{{ policy.remark }}</small>
            </span>
            <span><b :class="['policy-subject-type', policy.subject_type]">{{ authorizationTypeLabel(policy) }}</b></span>
            <span><b :class="['policy-authorization-mode', authorizationMode(policy)]">{{ authorizationModeLabel(policy) }}</b></span>
            <span class="permission-policy-target" :title="authorizationTargetName(policy)">{{ authorizationTargetName(policy) }}</span>
            <span><b class="badge healthy">{{ effectCount(policy, 'allow') }} 项</b></span>
            <span><b class="badge offline">{{ effectCount(policy, 'deny') }} 项</b></span>
            <span><b class="badge role-badge">{{ policy.priority }}</b></span>
            <span><b :class="['badge', policy.status === 'available' ? 'healthy' : 'offline']">{{ statusLabel(policy.status) }}</b></span>
            <span>{{ formatDateTime(policy.updated_at) }}</span>
            <span class="row-actions">
              <button title="详情" @click="openPolicyDetail(policy)"><Eye :size="15" />详情</button>
              <button v-if="canCreate && authorizationMode(policy) === 'direct'" title="克隆" :disabled="cloningId === policy.id" @click="clonePolicy(policy)"><Copy :size="15" />克隆</button>
              <button v-if="canUpdate && authorizationMode(policy) === 'direct'" class="action-edit" title="编辑" @click="openEdit(policy)"><Edit3 :size="15" />编辑</button>
              <button v-if="canDelete && authorizationMode(policy) === 'direct'" title="删除" class="danger" @click="askDelete(policy)"><Trash2 :size="15" />删除</button>
            </span>
          </div>
          <p v-if="!filteredPolicies.length" class="empty-list">当前部门范围内暂无权限策略</p>
        </div>

        <PaginationBar
          v-model:jump-page="jumpPage"
          :page-size="pageSize"
          :current-page="currentPage"
          :total-pages="totalPages"
          :page-start="pageStart"
          :page-end="pageEnd"
          :total="filteredPolicies.length"
          @go="goPage"
          @move="movePage"
          @jump="applyJump"
        />
      </div>
    </div>
  </section>

  <ModalDialog
    :open="detailModalOpen"
    title="权限策略详情"
    description="查看策略授权对象、状态和完整权限配置。"
    width="980px"
    @close="detailModalOpen = false"
  >
    <div v-if="detailPolicy" class="permission-policy-view">
      <header>
        <div>
          <span class="permission-policy-context-icon"><ShieldCheck :size="18" /></span>
          <div>
            <h3>{{ detailPolicy.name }}</h3>
            <p v-if="detailPolicy.remark">{{ detailPolicy.remark }}</p>
          </div>
        </div>
        <b :class="['badge', detailPolicy.status === 'available' ? 'healthy' : 'offline']">{{ statusLabel(detailPolicy.status) }}</b>
      </header>
      <section class="permission-policy-view-meta">
        <span><small>授权类型</small><strong>{{ authorizationTypeLabel(detailPolicy) }}</strong></span>
        <span><small>授权模式</small><strong>{{ authorizationModeLabel(detailPolicy) }}</strong></span>
        <span><small>授权对象</small><strong>{{ authorizationTargetName(detailPolicy) }}</strong></span>
        <span><small>优先级</small><strong>{{ detailPolicy.priority }}</strong></span>
        <span><small>更新时间</small><strong>{{ formatDateTime(detailPolicy.updated_at) }}</strong></span>
      </section>
      <div class="permission-policy-view-rules">
        <section class="allow-detail">
          <header><strong>允许权限</strong><b>{{ effectCount(detailPolicy, 'allow') }} 项</b></header>
          <div>
            <span v-for="rule in detailPolicy.rules.filter((item) => item.effect === 'allow')" :key="rule.permission_code">
              {{ permissionLabelByCode.get(rule.permission_code) || rule.permission_code }}
            </span>
            <small v-if="!effectCount(detailPolicy, 'allow')">未配置允许权限</small>
          </div>
        </section>
        <section class="deny-detail">
          <header><strong>拒绝权限</strong><b>{{ effectCount(detailPolicy, 'deny') }} 项</b></header>
          <div>
            <span v-for="rule in detailPolicy.rules.filter((item) => item.effect === 'deny')" :key="rule.permission_code">
              {{ permissionLabelByCode.get(rule.permission_code) || rule.permission_code }}
            </span>
            <small v-if="!effectCount(detailPolicy, 'deny')">未配置拒绝权限</small>
          </div>
        </section>
      </div>
      <footer><button class="primary" type="button" @click="detailModalOpen = false">关闭</button></footer>
    </div>
  </ModalDialog>

  <ModalDialog :open="modalOpen" :title="editing ? '编辑权限策略' : '新增权限策略'" width="1120px" @close="modalOpen = false">
    <form class="permission-policy-form" @submit.prevent="savePolicy">
      <section class="permission-policy-basic">
        <label>
          <span>策略名称</span>
          <input v-model.trim="form.name" required placeholder="例如：运维一部基础设施权限" />
        </label>
        <label>
          <span>授权对象类型</span>
          <CustomSelect v-model="form.subject_type">
            <option value="department">部门</option>
            <option value="user">用户</option>
          </CustomSelect>
        </label>
        <label v-if="form.subject_type === 'department'">
          <span>选择部门</span>
          <CustomSelect v-model.number="form.department" required>
            <option v-for="department in departments" :key="department.id" :value="department.id">{{ department.name }}</option>
          </CustomSelect>
        </label>
        <label v-else>
          <span>选择用户</span>
          <CustomSelect v-model.number="form.user" required>
            <option v-for="user in policyUserOptions" :key="user.id" :value="user.id">
              {{ displayName(user) }} / {{ user.username }} / {{ user.department || user.organization || '未分配部门' }}
            </option>
          </CustomSelect>
        </label>
        <label>
          <span>优先级</span>
          <input v-model.number="form.priority" min="0" max="1000" type="number" />
        </label>
        <label>
          <span>状态</span>
          <CustomSelect v-model="form.status">
            <option value="available">可用</option>
            <option value="disabled">已禁用</option>
          </CustomSelect>
        </label>
        <label class="wide">
          <span>备注</span>
          <textarea v-model.trim="form.remark" placeholder="说明这个策略给谁用、为什么配置" />
        </label>
      </section>

      <div class="permission-tree-editor">
        <div class="permission-editor-head">
          <strong><ShieldCheck :size="16" /> 权限配置</strong>
          <span>{{ subjectTypeLabel(form.subject_type) }}授权，权限项与实际页面按钮一致；父级设置会同步到下级页面和按钮。</span>
        </div>

        <section v-for="group in catalog" :key="group.code" class="permission-tree-group">
          <header class="permission-tree-group-head">
            <button class="permission-tree-toggle" type="button" @click="toggleGroup(group.code)">
              <ChevronDown v-if="isGroupOpen(group.code)" :size="16" />
              <ChevronRight v-else :size="16" />
              <span>
                <strong>{{ group.name }}</strong>
                <small>一级菜单</small>
              </span>
            </button>
            <div class="permission-state-buttons">
              <button class="allow" type="button" :class="{ active: ruleState[group.code] === 'allow' }" :aria-pressed="ruleState[group.code] === 'allow'" @click="setGroupWithChildren(group, 'allow')">允许</button>
              <button class="deny" type="button" :class="{ active: ruleState[group.code] === 'deny' }" :aria-pressed="ruleState[group.code] === 'deny'" @click="setGroupWithChildren(group, 'deny')">拒绝</button>
            </div>
          </header>

          <div v-if="isGroupOpen(group.code)" class="permission-tree-pages">
            <PermissionTreeNode
              v-for="page in group.pages"
              :key="page.code"
              :page="page"
              :rule-state="ruleState"
              :expanded-pages="expandedPages"
              @toggle-page="togglePage"
              @set-state="setState"
              @set-page-tree="setPageWithActions"
            />
          </div>
        </section>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>
      <footer>
        <button class="secondary" type="button" @click="modalOpen = false">取消</button>
        <button class="primary" :disabled="saving">{{ saving ? '处理中' : (editing ? '保存' : '确定') }}</button>
      </footer>
    </form>
  </ModalDialog>

  <ConfirmDialog
    :open="deleteOpen"
    title="删除权限策略"
    :message="`确认删除权限策略 ${deleting?.name || ''}？删除后该策略下的允许和拒绝规则都会失效。`"
    :loading="deletingNow"
    @cancel="deleteOpen = false"
    @confirm="confirmDelete"
  />
</template>
