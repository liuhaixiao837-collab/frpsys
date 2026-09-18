<script setup lang="ts">
import {
  Building2, ChevronRight, Edit3, Folder, Plus, RefreshCw, Search, Trash2, UserPlus, UsersRound, UserX,
} from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'

import { api } from '../../../api'
import ConfirmDialog from '../../../components/ConfirmDialog.vue'
import CustomSelect from '../../../components/CustomSelect.vue'
import ModalDialog from '../../../components/ModalDialog.vue'
import { actionPermissionForPath } from '../../../permissions'
import { useAuthStore } from '../../../stores/auth'
import PaginationBar from './PaginationBar.vue'
import type { DepartmentRow, RoleRow, UserRow } from './types'
import { displayName, formatDateTime, roleLabel } from './types'
import { usePager } from './usePager'

type DepartmentTreeRow = {
  department: DepartmentRow
  depth: number
  hasChildren: boolean
  path: string[]
  branchId: number | null
}

const props = defineProps<{
  users: UserRow[]
  departments: DepartmentRow[]
  roles: RoleRow[]
  loading?: boolean
}>()
const emit = defineEmits<{ reload: [] }>()
const auth = useAuthStore()
const canCreate = computed(() => auth.can(actionPermissionForPath('/admin/departments', 'create')))
const canUpdate = computed(() => auth.can(actionPermissionForPath('/admin/departments', 'update')))
const canDelete = computed(() => auth.can(actionPermissionForPath('/admin/departments', 'delete')))

const query = ref('')
const parentFilter = ref<number | ''>('')
const modalOpen = ref(false)
const memberModalOpen = ref(false)
const deleteOpen = ref(false)
const removeMemberOpen = ref(false)
const editing = ref<DepartmentRow | null>(null)
const deleting = ref<DepartmentRow | null>(null)
const selectedDepartment = ref<DepartmentRow | null>(null)
const removingMember = ref<UserRow | null>(null)
const members = ref<UserRow[]>([])
const membersLoading = ref(false)
const saving = ref(false)
const deletingNow = ref(false)
const error = ref('')
const expandedDepartmentIds = ref<Set<number>>(new Set())
const knownDepartmentIds = ref<Set<number>>(new Set())
const branchPageSize = ref(10)

const form = reactive({
  name: '',
  slug: '',
  description: '',
  parent_id: null as number | null,
})

const memberForm = reactive({
  user_id: null as number | null,
  role: 'member',
})

const rootDepartment = computed(() => props.departments.find((item) => item.is_default || !item.parent_id) || props.departments[0] || null)
const canAddSelectedDepartmentMember = computed(() => Boolean(
  selectedDepartment.value && !selectedDepartment.value.is_default && !selectedDepartment.value.is_root,
))
const availableUsers = computed(() => props.users.filter((user) => (user.department_id ?? user.organization_id) !== selectedDepartment.value?.id))
const departmentById = computed(() => new Map(props.departments.map((department) => [department.id, department])))
const directMemberCountByDepartment = computed(() => {
  const counts = new Map<number, number>()
  props.users.forEach((user) => {
    const departmentId = user.department_id ?? user.organization_id
    if (departmentId) counts.set(departmentId, (counts.get(departmentId) || 0) + 1)
  })
  return counts
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
const departmentTreeRows = computed<DepartmentTreeRow[]>(() => {
  const rows: DepartmentTreeRow[] = []
  const visited = new Set<number>()
  /** 按父级关系递归生成稳定排序的部门树行，并记录完整部门路径。 */
  const append = (parentId: number | null, depth: number, parentPath: string[], parentBranchId: number | null) => {
    for (const department of departmentChildren.value.get(parentId) || []) {
      if (visited.has(department.id)) continue
      visited.add(department.id)
      const path = [...parentPath, department.name]
      const branchId = depth === 0 ? null : parentBranchId || department.id
      rows.push({
        department,
        depth,
        hasChildren: Boolean(departmentChildren.value.get(department.id)?.length),
        path,
        branchId,
      })
      append(department.id, depth + 1, path, branchId)
    }
  }
  append(null, 0, [], null)
  props.departments.forEach((department) => {
    if (visited.has(department.id)) return
    rows.push({ department, depth: 0, hasChildren: false, path: [department.name], branchId: null })
  })
  return rows
})
const departmentOptions = computed(() => departmentTreeRows.value.map((row) => ({
  id: row.department.id,
  label: row.path.join(' / '),
})))
const selectedFormParentRow = computed(() => departmentTreeRows.value.find((row) => row.department.id === form.parent_id) || null)
const selectedFormDepartmentLevel = computed(() => (selectedFormParentRow.value?.depth ?? -1) + 2)
const selectedFormDepartmentPath = computed(() => [
  ...(selectedFormParentRow.value?.path || []),
  form.name || '新部门',
].join(' / '))
const visibleDepartmentRows = computed(() => {
  const normalizedQuery = query.value.trim().toLowerCase()
  const selectedParentId = parentFilter.value === '' ? null : Number(parentFilter.value)
  const scopeIds = new Set<number>()
  if (selectedParentId) {
    const pending = [selectedParentId]
    while (pending.length) {
      const departmentId = pending.shift()
      if (departmentId === undefined || scopeIds.has(departmentId)) continue
      scopeIds.add(departmentId)
      ;(departmentChildren.value.get(departmentId) || []).forEach((child) => pending.push(child.id))
    }
  } else {
    props.departments.forEach((department) => scopeIds.add(department.id))
  }

  const matchedIds = new Set(departmentTreeRows.value
    .filter((row) => {
      if (!scopeIds.has(row.department.id)) return false
      if (!normalizedQuery) return true
      const text = `${row.department.name} ${row.department.slug} ${row.department.description} ${row.path.join(' ')}`.toLowerCase()
      return text.includes(normalizedQuery)
    })
    .map((row) => row.department.id))
  const displayIds = new Set(matchedIds)
  matchedIds.forEach((departmentId) => {
    let current = departmentById.value.get(departmentId)
    const visited = new Set<number>()
    while (current?.parent_id && !visited.has(current.parent_id)) {
      visited.add(current.parent_id)
      displayIds.add(current.parent_id)
      current = departmentById.value.get(current.parent_id)
    }
  })

  const forceExpanded = Boolean(normalizedQuery || selectedParentId)
  return departmentTreeRows.value.filter((row) => {
    if (!displayIds.has(row.department.id)) return false
    if (forceExpanded) return true
    let current = row.department
    const visited = new Set<number>()
    while (current.parent_id && !visited.has(current.parent_id)) {
      visited.add(current.parent_id)
      if (!expandedDepartmentIds.value.has(current.parent_id)) return false
      const parent = departmentById.value.get(current.parent_id)
      if (!parent) break
      current = parent
    }
    return true
  })
})
const visibleDepartmentBranches = computed(() => visibleDepartmentRows.value.filter((row) => row.depth === 1))
const {
  currentPage: currentBranchPage,
  jumpPage: branchJumpPage,
  totalPages: totalBranchPages,
  paginatedItems: paginatedDepartmentBranches,
  pageStart: branchPageStart,
  pageEnd: branchPageEnd,
  goPage: goBranchPage,
  movePage: moveBranchPage,
  applyJump: applyBranchJump,
  resetPage: resetBranchPage,
} = usePager(visibleDepartmentBranches, branchPageSize)
const paginatedVisibleDepartmentRows = computed(() => {
  const branchIds = new Set(paginatedDepartmentBranches.value.map((row) => row.department.id))
  return visibleDepartmentRows.value.filter((row) => row.depth === 0 || (row.branchId !== null && branchIds.has(row.branchId)))
})
const departmentSequenceById = computed(() => new Map(
  departmentTreeRows.value.map((row, index) => [row.department.id, index + 1]),
))

watch([query, parentFilter], resetBranchPage)

watch(() => props.departments, (departments) => {
  const availableIds = new Set(departments.map((department) => department.id))
  const nextExpandedIds = new Set([...expandedDepartmentIds.value].filter((departmentId) => availableIds.has(departmentId)))
  departments.forEach((department) => {
    if (!knownDepartmentIds.value.has(department.id) && department.children_count > 0) nextExpandedIds.add(department.id)
  })
  expandedDepartmentIds.value = nextExpandedIds
  knownDepartmentIds.value = availableIds
}, { immediate: true, deep: true })

/** 切换单个部门节点的展开状态，不改变部门数据。 */
function toggleDepartment(departmentId: number) {
  const next = new Set(expandedDepartmentIds.value)
  if (next.has(departmentId)) next.delete(departmentId)
  else next.add(departmentId)
  expandedDepartmentIds.value = next
}

/** 展开当前组织架构中的全部父级部门。 */
function expandAllDepartments() {
  expandedDepartmentIds.value = new Set(departmentTreeRows.value.filter((row) => row.hasChildren).map((row) => row.department.id))
}

/** 收起全部部门，仅保留组织架构的根节点。 */
function collapseAllDepartments() {
  expandedDepartmentIds.value = new Set()
}

/** 判断候选上级是否为当前编辑部门本身或其下级，避免形成循环层级。 */
function isParentOptionDisabled(row: DepartmentTreeRow) {
  if (!editing.value) return false
  if (row.department.id === editing.value.id) return true
  let current = row.department
  const visited = new Set<number>()
  while (current.parent_id && !visited.has(current.parent_id)) {
    if (current.parent_id === editing.value.id) return true
    visited.add(current.parent_id)
    const parent = departmentById.value.get(current.parent_id)
    if (!parent) break
    current = parent
  }
  return false
}

/**
 * 将 resetForm 管理的界面或业务状态恢复到初始值。
 * 参数：`department` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function resetForm(department?: DepartmentRow) {
  editing.value = department || null
  Object.assign(form, {
    name: department?.name || '',
    slug: department?.slug || '',
    description: department?.description || '',
    parent_id: department?.parent_id ?? rootDepartment.value?.id ?? null,
  })
  error.value = ''
}

/**
 * 准备 openCreate 所需数据并打开对应交互界面。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function openCreate(parent?: DepartmentRow) {
  resetForm()
  if (parent) form.parent_id = parent.id
  modalOpen.value = true
}

/**
 * 准备 openEdit 所需数据并打开对应交互界面。
 * 参数：`department` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function openEdit(department: DepartmentRow) {
  resetForm(department)
  modalOpen.value = true
}

/**
 * 校验当前输入并完成 saveDepartment 对应的数据保存操作。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function saveDepartment() {
  saving.value = true
  error.value = ''
  const payload = {
    ...form,
    parent_id: editing.value?.is_default ? null : form.parent_id,
    org_type: editing.value?.is_default ? 'company' : 'department',
    is_default: Boolean(editing.value?.is_default),
  }
  try {
    if (editing.value) {
      await api(`/orgs/${editing.value.id}/`, { method: 'PATCH', body: JSON.stringify(payload) })
    } else {
      await api('/orgs/', { method: 'POST', body: JSON.stringify(payload) })
    }
    modalOpen.value = false
    emit('reload')
  } catch (reason: any) {
    error.value = reason.message || '保存部门失败'
  } finally {
    saving.value = false
  }
}

/**
 * 处理 askDelete 对应的确认交互，并在确认后执行目标操作。
 * 参数：`department` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function askDelete(department: DepartmentRow) {
  deleting.value = department
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
  error.value = ''
  try {
    await api(`/orgs/${deleting.value.id}/`, { method: 'DELETE' })
    deleteOpen.value = false
    deleting.value = null
    emit('reload')
  } catch (reason: any) {
    error.value = reason.message || '删除部门失败'
  } finally {
    deletingNow.value = false
  }
}

/**
 * 准备 openMembers 所需数据并打开对应交互界面。
 * 参数：`department` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
async function openMembers(department: DepartmentRow) {
  selectedDepartment.value = department
  memberForm.user_id = null
  memberModalOpen.value = true
  await loadMembers()
}

/**
 * 从后端或当前状态加载 loadMembers 所需的最新业务数据。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function loadMembers() {
  if (!selectedDepartment.value) return
  membersLoading.value = true
  error.value = ''
  try {
    members.value = await api(`/orgs/${selectedDepartment.value.id}/members/`)
  } catch (reason: any) {
    error.value = reason.message || '加载成员失败'
  } finally {
    membersLoading.value = false
  }
}

/**
 * 校验当前输入并完成 saveMember 对应的数据保存操作。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function saveMember() {
  const department = selectedDepartment.value
  if (!department || department.is_default || department.is_root || !memberForm.user_id) return
  saving.value = true
  error.value = ''
  try {
    await api(`/orgs/${department.id}/members/`, {
      method: 'POST',
      body: JSON.stringify(memberForm),
    })
    memberForm.user_id = null
    await loadMembers()
    emit('reload')
  } catch (reason: any) {
    error.value = reason.message || '添加成员失败'
  } finally {
    saving.value = false
  }
}


/**
 * 处理 askRemoveMember 对应的确认交互，并在确认后执行目标操作。
 * 参数：`user` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function askRemoveMember(user: UserRow) {
  removingMember.value = user
  removeMemberOpen.value = true
}

/**
 * 处理 confirmRemoveMember 对应的确认交互，并在确认后执行目标操作。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function confirmRemoveMember() {
  if (!selectedDepartment.value || !removingMember.value) return
  deletingNow.value = true
  error.value = ''
  try {
    await api(`/orgs/${selectedDepartment.value.id}/members/${removingMember.value.id}/`, { method: 'DELETE' })
    removeMemberOpen.value = false
    removingMember.value = null
    await loadMembers()
    emit('reload')
  } catch (reason: any) {
    error.value = reason.message || '移出成员失败'
  } finally {
    deletingNow.value = false
  }
}
</script>

<template>
  <section class="governance-page">

    <div class="governance-card user-governance-card">
      <div class="governance-toolbar department-toolbar crud-toolbar">
        <button v-if="canCreate" class="primary toolbar-primary-action" type="button" @click="openCreate()">
          <Plus :size="16" />&#26032;&#22686;&#37096;&#38376;
        </button>
        <div class="department-toolbar-controls">
          <label class="search-box">
            <Search :size="16" />
            <input v-model="query" placeholder="搜索部门名称、Slug 或说明" />
          </label>
          <CustomSelect v-model="parentFilter" class="toolbar-filter-select">
            <option value="">全部上级</option>
            <option v-for="department in departmentOptions" :key="department.id" :value="department.id">
              {{ department.label }}
            </option>
          </CustomSelect>
          <div class="toolbar-actions">
            <button class="secondary department-tree-control" type="button" @click="expandAllDepartments">全部展开</button>
            <button class="secondary department-tree-control" type="button" @click="collapseAllDepartments">全部收起</button>
            <button class="secondary action-refresh" type="button" :disabled="loading" @click="emit('reload')">
              <RefreshCw :size="16" :class="{ spin: loading }" />刷新
            </button>
          </div>
        </div>
      </div>

      <div class="governance-table department-table">
        <div class="governance-table-row table-head">
          <span class="sequence-col">序号</span>
          <span>部门</span>
          <span>上级路径</span>
          <span>成员</span>
          <span>更新时间</span>
          <span>操作</span>
        </div>
        <div
          v-for="row in paginatedVisibleDepartmentRows"
          :key="row.department.id"
          :class="['governance-table-row', 'department-tree-table-row', { 'department-root-row': row.depth === 0 }]"
        >
          <span class="sequence-col">{{ departmentSequenceById.get(row.department.id) || 0 }}</span>
          <span
            :class="['department-tree-cell', { 'has-parent': row.depth > 0 }]"
            :style="{ '--department-table-depth': row.depth }"
          >
            <button
              v-if="row.hasChildren"
              class="department-tree-toggle"
              type="button"
              :title="expandedDepartmentIds.has(row.department.id) ? '收起下级部门' : '展开下级部门'"
              @click="toggleDepartment(row.department.id)"
            >
              <ChevronRight :size="15" :class="{ expanded: expandedDepartmentIds.has(row.department.id) || query || parentFilter !== '' }" />
            </button>
            <span v-else class="department-tree-toggle-placeholder" />
            <span class="department-tree-icon" :class="{ root: row.department.is_default || row.department.is_root }">
              <Building2 v-if="row.department.is_default || row.department.is_root" :size="16" />
              <Folder v-else :size="16" />
            </span>
            <span class="department-tree-title">
              <strong>{{ row.department.name }}</strong>
              <small v-if="row.department.is_default || row.department.is_root">组织根节点</small>
              <small v-else-if="row.department.children_count">{{ row.department.children_count }} 个直属下级</small>
            </span>
          </span>
          <span class="department-parent-path" :title="row.path.slice(0, -1).join(' / ') || '公司根节点'">
            {{ row.path.slice(0, -1).join(' / ') || '公司根节点' }}
          </span>
          <span>
            <span class="department-member-summary">
              <b>全部 {{ row.department.member_count || 0 }}</b>
              <small>直属 {{ directMemberCountByDepartment.get(row.department.id) || 0 }}</small>
            </span>
          </span>
          <span>{{ formatDateTime(row.department.updated_at) }}</span>
          <span class="row-actions">
            <button v-if="canCreate" class="action-child" title="新增下级部门" @click="openCreate(row.department)"><Plus :size="15" />下级</button>
            <button v-if="canUpdate" class="action-member" title="成员" @click="openMembers(row.department)"><UsersRound :size="15" />成员</button>
            <button v-if="canUpdate" class="action-edit" title="编辑" @click="openEdit(row.department)"><Edit3 :size="15" />编辑</button>
            <button
              v-if="canDelete"
              title="删除"
              class="danger"
              :disabled="row.department.is_default || row.department.is_root"
              @click="askDelete(row.department)"
            >
              <Trash2 :size="15" />删除
            </button>
          </span>
        </div>
        <p v-if="!paginatedVisibleDepartmentRows.length" class="empty-list">没有匹配的部门</p>
      </div>
      <PaginationBar
        v-if="visibleDepartmentBranches.length"
        v-model:jump-page="branchJumpPage"
        v-model:page-size="branchPageSize"
        :page-size-options="[10, 20, 50]"
        :current-page="currentBranchPage"
        :total-pages="totalBranchPages"
        :page-start="branchPageStart"
        :page-end="branchPageEnd"
        :total="visibleDepartmentBranches.length"
        unit-label="个一级部门"
        :detail="`本页展示 ${paginatedVisibleDepartmentRows.length} 个节点 / 全部 ${departments.length} 个部门`"
        @go="goBranchPage"
        @move="moveBranchPage"
        @jump="applyBranchJump"
      />
      <div v-else class="department-tree-footer">
        共 {{ departments.length }} 个部门，当前展示 {{ paginatedVisibleDepartmentRows.length }} 个节点
      </div>
    </div>
  </section>

  <ModalDialog
    :open="modalOpen"
    :title="editing ? '编辑部门' : '新增部门'"
    description="部门默认挂在默认组织下；默认组织本身作为公司根不能删除。"
    @close="modalOpen = false"
  >
    <form class="form-grid" @submit.prevent="saveDepartment">
      <label>部门名称<input v-model.trim="form.name" required /></label>
      <label v-if="!editing">Slug<input v-model.trim="form.slug" required /></label>
      <label class="department-parent-field">上级部门
        <CustomSelect
          v-model.number="form.parent_id"
          class="department-parent-select"
          :disabled="Boolean(editing?.is_default)"
        >
          <option
            v-for="row in departmentTreeRows"
            :key="row.department.id"
            :value="row.department.id"
            :disabled="isParentOptionDisabled(row)"
            data-option-kind="tree"
            :data-depth="row.depth"
            :data-description="row.depth === 0 ? '第 1 级 · 组织根节点' : `第 ${row.depth + 1} 级 · 上级：${row.department.parent_name || '默认组织'}`"
          >
            {{ row.department.name }}
          </option>
        </CustomSelect>
        <small v-if="selectedFormParentRow" class="department-parent-hint">
          <b>第 {{ selectedFormDepartmentLevel }} 级</b>
          <span :title="selectedFormDepartmentPath">{{ selectedFormDepartmentPath }}</span>
        </small>
      </label>
      <label class="wide">说明<textarea v-model.trim="form.description" /></label>
      <p v-if="error" class="form-error">{{ error }}</p>
      <footer>
        <button class="secondary" type="button" @click="modalOpen = false">取消</button>
        <button class="primary" :disabled="saving">{{ saving ? '处理中' : (editing ? '保存' : '确定') }}</button>
      </footer>
    </form>
  </ModalDialog>

  <ModalDialog
    :open="memberModalOpen"
    :title="`${selectedDepartment?.name || ''} 成员`"
    description="成员属于一个部门，也可以直接分配数据库角色。"
    width="960px"
    @close="memberModalOpen = false"
  >
    <div class="member-modal-layout">
      <form class="member-add-bar" @submit.prevent="saveMember">
        <CustomSelect v-model.number="memberForm.user_id" required>
          <option :value="null" disabled>选择用户</option>
          <option v-for="user in availableUsers" :key="user.id" :value="user.id">
            {{ displayName(user) }} / {{ user.username }} / {{ user.department || user.organization || '未分配' }}
          </option>
        </CustomSelect>
        <button
          class="primary"
          :disabled="saving || !availableUsers.length || !canAddSelectedDepartmentMember"
          :title="canAddSelectedDepartmentMember ? '添加到当前部门' : '默认组织不能添加用户，请选择具体部门'"
        >
          <UserPlus :size="15" />添加成员
        </button>
      </form>

      <div class="member-table">
        <div class="member-table-row table-head">
          <span class="sequence-col">序号</span>
          <span>姓名</span>
          <span>邮箱</span>
          <span>角色</span>
          <span>操作</span>
        </div>
        <div v-for="(user, rowIndex) in members" :key="user.id" class="member-table-row">
          <span class="sequence-col">{{ rowIndex + 1 }}</span>
          <span>{{ displayName(user) }}</span>
          <span>{{ user.email || '未设置' }}</span>
          <span>
            <b class="badge role-badge">{{ roleLabel(user.role, roles) }}</b>
          </span>
          <span class="row-actions">
            <button
              title="移出部门"
              class="danger"
              type="button"
              :disabled="selectedDepartment?.is_default || selectedDepartment?.is_root"
              @click="askRemoveMember(user)"
            >
              <UserX :size="15" />移出
            </button>
          </span>
        </div>
        <p v-if="membersLoading" class="empty-list">成员加载中...</p>
        <p v-else-if="!members.length" class="empty-list">当前部门暂无成员</p>
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
    </div>
  </ModalDialog>

  <ConfirmDialog
    :open="deleteOpen"
    title="删除部门"
    :message="`确认删除部门 ${deleting?.name || ''}？有成员、设备、事件或子部门时后端会拒绝删除。`"
    :loading="deletingNow"
    @cancel="deleteOpen = false"
    @confirm="confirmDelete"
  />
  <ConfirmDialog
    :open="removeMemberOpen"
    title="移出部门成员"
    :message="`确认把 ${removingMember ? displayName(removingMember) : ''} 移出 ${selectedDepartment?.name || ''}？该用户会回到默认组织。`"
    confirm-text="确认移出"
    :loading="deletingNow"
    @cancel="removeMemberOpen = false"
    @confirm="confirmRemoveMember"
  />
</template>
