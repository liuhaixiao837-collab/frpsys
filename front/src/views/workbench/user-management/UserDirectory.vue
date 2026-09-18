<script setup lang="ts">
import {
  Building2, CheckCircle2, ChevronDown, ChevronRight, Download, Edit3, FileSpreadsheet,
  Folder, KeyRound, Plus, PanelLeftClose, PanelLeftOpen, RefreshCw, Search, Trash2,
  Upload, UserRoundCheck, UsersRound, XCircle,
} from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'

import { api, apiForm, downloadFile } from '../../../api'
import ConfirmDialog from '../../../components/ConfirmDialog.vue'
import CustomSelect from '../../../components/CustomSelect.vue'
import ModalDialog from '../../../components/ModalDialog.vue'
import PasswordInput from '../../../components/PasswordInput.vue'
import { actionPermissionForPath } from '../../../permissions'
import { useAuthStore } from '../../../stores/auth'
import PaginationBar from './PaginationBar.vue'
import type { DepartmentRow, PasswordPolicy, RoleRow, UserRow } from './types'
import { displayName, roleLabel } from './types'
import { usePager } from './usePager'

const props = defineProps<{
  users: UserRow[]
  departments: DepartmentRow[]
  roles: RoleRow[]
  passwordPolicy: PasswordPolicy
  loading?: boolean
}>()
const emit = defineEmits<{ reload: [] }>()
const auth = useAuthStore()
const canCreate = computed(() => auth.can(actionPermissionForPath('/admin/users', 'create')))
const canUpdate = computed(() => auth.can(actionPermissionForPath('/admin/users', 'update')))
const canDelete = computed(() => auth.can(actionPermissionForPath('/admin/users', 'delete')))
const canDisable = computed(() => auth.can(actionPermissionForPath('/admin/users', 'disable')))
const canResetOtp = computed(() => auth.can(actionPermissionForPath('/admin/users', 'reset_otp')))
const canImport = computed(() => auth.can(actionPermissionForPath('/admin/users', 'import')))

type VisibleDepartment = {
  department: DepartmentRow
  depth: number
  hasChildren: boolean
}

type UserImportRow = {
  row_number: number
  username: string
  name: string
  department: string
  status: 'valid' | 'invalid'
  errors: string[]
}

type UserImportResult = {
  total_rows: number
  valid_rows: number
  invalid_rows: number
  can_import: boolean
  rows: UserImportRow[]
}

const query = ref('')
const selectedDepartmentId = ref<number | null>(null)
const expandedDepartmentIds = ref<Set<number>>(new Set())
const departmentPanelCollapsed = ref(false)
const importModalOpen = ref(false)
const importFileInput = ref<HTMLInputElement | null>(null)
const importFile = ref<File | null>(null)
const importResult = ref<UserImportResult | null>(null)
const downloadingTemplate = ref(false)
const precheckingImport = ref(false)
const importingUsers = ref(false)
const modalOpen = ref(false)
const deleteOpen = ref(false)
const activeOpen = ref(false)
const otpResetOpen = ref(false)
const editing = ref<UserRow | null>(null)
const deleting = ref<UserRow | null>(null)
const activeTarget = ref<UserRow | null>(null)
const otpResetTarget = ref<UserRow | null>(null)
const saving = ref(false)
const deletingNow = ref(false)
const activeNow = ref(false)
const otpResetting = ref(false)
const error = ref('')
const feedback = ref('')
const importError = ref('')
const passwordError = ref('')

const form = reactive({
  username: '',
  full_name: '',
  email: '',
  password: '',
  role: '',
  title: '',
  phone: '',
  department_id: null as number | null,
  is_active: true,
  otp_policy: 'inherit' as UserRow['otp_policy'],
})

const departmentById = computed(() => new Map(props.departments.map((department) => [department.id, department])))
const selectedDepartment = computed(() => (
  selectedDepartmentId.value === null ? null : departmentById.value.get(selectedDepartmentId.value) || null
))
const canCreateInSelectedDepartment = computed(() => Boolean(
  selectedDepartment.value && !selectedDepartment.value.is_default && !selectedDepartment.value.is_root,
))
const selectedDepartmentScopeIds = computed(() => {
  const selected = selectedDepartment.value
  const scopeIds = new Set<number>()
  if (!selected) return scopeIds
  if (selected.is_default || selected.is_root) {
    props.departments.forEach((department) => scopeIds.add(department.id))
    return scopeIds
  }
  const pending = [selected.id]
  while (pending.length) {
    const departmentId = pending.shift()
    if (departmentId === undefined || scopeIds.has(departmentId)) continue
    scopeIds.add(departmentId)
    props.departments.forEach((department) => {
      if (department.parent_id === departmentId) pending.push(department.id)
    })
  }
  return scopeIds
})

const visibleDepartments = computed<VisibleDepartment[]>(() => {
  const children = new Map<number | null, DepartmentRow[]>()
  props.departments.forEach((department) => {
    const parentId = department.parent_id && departmentById.value.has(department.parent_id)
      ? department.parent_id
      : null
    children.set(parentId, [...(children.get(parentId) || []), department])
  })
  children.forEach((items) => items.sort((left, right) => (
    Number(right.is_default) - Number(left.is_default) || left.name.localeCompare(right.name, 'zh-CN')
  )))

  const rows: VisibleDepartment[] = []
  /** 按展开状态递归追加当前父节点下的可见部门。 */
  const append = (parentId: number | null, depth: number) => {
    for (const department of children.get(parentId) || []) {
      const childItems = children.get(department.id) || []
      rows.push({ department, depth, hasChildren: childItems.length > 0 })
      if (childItems.length && expandedDepartmentIds.value.has(department.id)) {
        append(department.id, depth + 1)
      }
    }
  }
  append(null, 0)
  return rows
})

const filteredUsers = computed(() => props.users.filter((user) => {
  const departmentId = user.department_id ?? user.organization_id ?? null
  const selected = selectedDepartment.value
  const matchesDepartment = departmentId === null
    ? Boolean(selected?.is_default || selected?.is_root)
    : selectedDepartmentScopeIds.value.has(departmentId)
  if (!matchesDepartment) return false
  const text = [
    user.username,
    displayName(user),
    user.email,
    user.phone,
    user.role,
    user.role_name,
    user.title,
    user.otp_status_label,
  ].join(' ').toLowerCase()
  return text.includes(query.value.trim().toLowerCase())
}))

const passwordPolicyHint = computed(() => {
  const requirements = []
  if (props.passwordPolicy.require_uppercase) requirements.push('大写字母')
  if (props.passwordPolicy.require_lowercase) requirements.push('小写字母')
  if (props.passwordPolicy.require_number) requirements.push('数字')
  if (props.passwordPolicy.require_special) requirements.push('特殊字符')
  const rules = [`至少 ${props.passwordPolicy.min_length} 位`]
  if (requirements.length) rules.push(`必须包含${requirements.join('、')}`)
  if (props.passwordPolicy.exclude_username) rules.push('不能包含用户名')
  if (props.passwordPolicy.max_age_days > 0) {
    rules.push(editing.value?.is_system_admin
      ? '系统超级管理员 admin 不受修改周期限制'
      : `${props.passwordPolicy.max_age_days} 天未修改会禁用账号`)
  }
  rules.push(editing.value ? '留空不修改原密码' : '留空则自动生成合规密码')
  return `${rules.join('；')}。`
})

const {
  pageSize, currentPage, jumpPage, totalPages, paginatedItems: paginatedUsers,
  pageStart, pageEnd, goPage, movePage, applyJump, resetPage,
} = usePager(filteredUsers, 10)

watch([query, selectedDepartmentId], resetPage)
watch(() => props.departments, (departments) => {
  const availableIds = new Set(departments.map((department) => department.id))
  expandedDepartmentIds.value = new Set(
    departments.filter((department) => department.children_count > 0).map((department) => department.id),
  )
  if (selectedDepartmentId.value === null || !availableIds.has(selectedDepartmentId.value)) {
    selectedDepartmentId.value = departments.find((department) => department.is_default)?.id ?? departments[0]?.id ?? null
  }
}, { immediate: true, deep: true })

/** 切换部门节点展开状态，只影响当前页面树形展示。 */
function toggleDepartment(departmentId: number) {
  const next = new Set(expandedDepartmentIds.value)
  if (next.has(departmentId)) next.delete(departmentId)
  else next.add(departmentId)
  expandedDepartmentIds.value = next
}

/** 切换左侧组织架构面板的展开状态，并保留当前选中的部门。 */
function toggleDepartmentPanel() {
  departmentPanelCollapsed.value = !departmentPanelCollapsed.value
}

/** 打开批量导入弹窗并清除上一次选择的文件和预检查结果。 */
function openImportModal() {
  importFile.value = null
  importResult.value = null
  importError.value = ''
  if (importFileInput.value) importFileInput.value.value = ''
  importModalOpen.value = true
}

/** 关闭批量导入弹窗；处理进行中时禁止中断当前请求。 */
function closeImportModal() {
  if (precheckingImport.value || importingUsers.value) return
  importModalOpen.value = false
  importError.value = ''
}

/** 下载包含当前可见部门和身份下拉项的最新 Excel 模板。 */
async function downloadImportTemplate() {
  downloadingTemplate.value = true
  importError.value = ''
  try {
    await downloadFile('/users/import/template/', 'user-import-template.xlsx')
  } catch (reason: any) {
    importError.value = reason.message || '下载用户导入模板失败'
  } finally {
    downloadingTemplate.value = false
  }
}

/** 保存用户新选择的 Excel 文件，并使旧预检查结果立即失效。 */
function handleImportFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  importFile.value = input.files?.[0] || null
  importResult.value = null
  importError.value = ''
}

/** 上传所选 Excel 执行无落库预检查，并展示逐行异常原因。 */
async function precheckUserImport() {
  if (!importFile.value) {
    importError.value = '请先选择要预检查的 Excel 文件'
    return
  }
  precheckingImport.value = true
  importError.value = ''
  try {
    const formData = new FormData()
    formData.append('file', importFile.value)
    importResult.value = await apiForm('/users/import/precheck/', formData)
  } catch (reason: any) {
    importResult.value = null
    importError.value = reason.message || '用户导入预检查失败'
  } finally {
    precheckingImport.value = false
  }
}

/** 再次上传已预检查文件，由后端重新校验后整批事务导入。 */
async function confirmUserImport() {
  if (!importFile.value || !importResult.value?.can_import) return
  importingUsers.value = true
  importError.value = ''
  try {
    const formData = new FormData()
    formData.append('file', importFile.value)
    const result = await apiForm('/users/import/confirm/', formData)
    feedback.value = result.detail || '用户导入成功'
    importModalOpen.value = false
    emit('reload')
  } catch (reason: any) {
    importResult.value = null
    importError.value = reason.message || '用户导入失败，请重新预检查'
  } finally {
    importingUsers.value = false
  }
}

/** 选中部门并让右侧列表展示该部门及全部下级部门用户。 */
function selectDepartment(departmentId: number) {
  selectedDepartmentId.value = departmentId
}

/** 重置新增或编辑表单；新增时部门固定为左侧当前选中部门。 */
function resetForm(user?: UserRow) {
  editing.value = user || null
  Object.assign(form, {
    username: user?.username || '',
    full_name: user ? displayName(user) : '',
    email: user?.email || '',
    password: '',
    role: user?.role || '',
    title: user?.title || '',
    phone: user?.phone || '',
    department_id: user?.department_id ?? user?.organization_id ?? selectedDepartmentId.value,
    is_active: user?.is_active ?? true,
    otp_policy: user?.otp_policy || 'inherit',
  })
  error.value = ''
  passwordError.value = ''
}

/** 打开新增用户窗口；默认组织或没有选中具体部门时不允许新增。 */
function openCreate() {
  if (!canCreateInSelectedDepartment.value) return
  resetForm()
  modalOpen.value = true
}

/** 打开编辑窗口并保持用户原部门不变。 */
function openEdit(user: UserRow) {
  resetForm(user)
  modalOpen.value = true
}

/** 关闭用户表单并清理本次校验消息。 */
function closeModal() {
  if (saving.value) return
  modalOpen.value = false
  error.value = ''
  passwordError.value = ''
}

/** 按平台密码策略校验本次手工输入的密码。 */
function passwordPolicyError() {
  const value = form.password
  if (!value) return ''
  const characters = Array.from(value)
  const failures: string[] = []
  if (characters.length < props.passwordPolicy.min_length) failures.push(`密码长度不能少于 ${props.passwordPolicy.min_length} 位`)
  if (props.passwordPolicy.require_uppercase && !characters.some((character) => /\p{Lu}/u.test(character))) failures.push('密码必须包含大写字母')
  if (props.passwordPolicy.require_lowercase && !characters.some((character) => /\p{Ll}/u.test(character))) failures.push('密码必须包含小写字母')
  if (props.passwordPolicy.require_number && !characters.some((character) => /\p{Nd}/u.test(character))) failures.push('密码必须包含数字')
  if (props.passwordPolicy.require_special && !characters.some((character) => !/[\p{L}\p{N}]/u.test(character))) failures.push('密码必须包含特殊字符')
  const username = form.username.trim().toLocaleLowerCase()
  if (props.passwordPolicy.exclude_username && username && value.toLocaleLowerCase().includes(username)) failures.push('密码不能包含用户名')
  return failures.join('；')
}

/** 将用户可用状态转换为列表徽标。 */
function userStatusBadge(user: UserRow) {
  if (user.password_expired_locked) return { label: '密码过期', tone: 'offline' }
  return user.is_active ? { label: '已启用', tone: 'healthy' } : { label: '已禁用', tone: 'offline' }
}

/** 将用户 OTP 状态转换为列表徽标。 */
function otpStatusBadge(user: UserRow) {
  if (user.otp_status === 'bound') return { label: user.otp_status_label, tone: 'healthy' }
  if (user.otp_status === 'pending' || user.otp_status === 'locked') return { label: user.otp_status_label, tone: 'pending' }
  if (user.otp_status === 'exempt') return { label: user.otp_status_label, tone: 'info' }
  return { label: user.otp_status_label || '未启用', tone: 'offline' }
}

/** 保存用户；只有新增用户时才写入左侧选中的部门。 */
async function saveUser() {
  error.value = ''
  passwordError.value = passwordPolicyError()
  if (passwordError.value) return
  saving.value = true
  const payload: Record<string, unknown> = {
    username: form.username,
    first_name: '',
    last_name: form.full_name,
    email: form.email,
    password: form.password,
    title: form.title,
    phone: form.phone,
    is_active: form.is_active,
    otp_policy: form.otp_policy,
  }
  if (!editing.value) payload.department_id = form.department_id
  if (!payload.password) delete payload.password
  try {
    if (editing.value) await api(`/users/${editing.value.id}/`, { method: 'PATCH', body: JSON.stringify(payload) })
    else await api('/users/', { method: 'POST', body: JSON.stringify(payload) })
    modalOpen.value = false
    emit('reload')
  } catch (reason: any) {
    error.value = reason.message || '保存用户失败'
  } finally {
    saving.value = false
  }
}

/** 打开用户启用或停用确认窗口。 */
function askToggleActive(user: UserRow) {
  activeTarget.value = user
  activeOpen.value = true
}

/** 提交用户启用状态变更并刷新列表。 */
async function confirmToggleActive() {
  if (!activeTarget.value) return
  activeNow.value = true
  try {
    await api(`/users/${activeTarget.value.id}/`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: !activeTarget.value.is_active }),
    })
    activeOpen.value = false
    activeTarget.value = null
    emit('reload')
  } finally {
    activeNow.value = false
  }
}

/** 打开目标用户的 OTP 重置确认窗口。 */
function askResetOtp(user: UserRow) {
  if (!user.otp_bound) return
  otpResetTarget.value = user
  otpResetOpen.value = true
}

/** 销毁目标用户 OTP 绑定并刷新列表。 */
async function confirmResetOtp() {
  if (!otpResetTarget.value) return
  otpResetting.value = true
  error.value = ''
  try {
    await api(`/users/${otpResetTarget.value.id}/reset-otp/`, { method: 'POST', body: JSON.stringify({}) })
    otpResetOpen.value = false
    otpResetTarget.value = null
    emit('reload')
  } catch (reason: any) {
    error.value = reason.message || '重置 OTP 失败'
  } finally {
    otpResetting.value = false
  }
}

/** 打开删除用户确认窗口，并保护当前登录用户。 */
function askDelete(user: UserRow) {
  if (user.username === auth.user?.username) {
    error.value = '不能删除当前登录用户'
    resetForm(user)
    modalOpen.value = true
    return
  }
  deleting.value = user
  deleteOpen.value = true
}

/** 删除目标用户并刷新当前部门列表。 */
async function confirmDelete() {
  if (!deleting.value) return
  deletingNow.value = true
  try {
    await api(`/users/${deleting.value.id}/`, { method: 'DELETE' })
    deleteOpen.value = false
    deleting.value = null
    emit('reload')
  } finally {
    deletingNow.value = false
  }
}
</script>

<template>
  <section class="governance-page">
    <div :class="['user-department-workspace', { 'department-panel-collapsed': departmentPanelCollapsed }]">
      <aside :class="['user-department-panel', { collapsed: departmentPanelCollapsed }]">
        <header class="user-department-head">
          <div v-if="!departmentPanelCollapsed">
            <span>组织架构</span>
            <small>{{ departments.length }} 个节点</small>
          </div>
          <div class="user-department-actions">
            <button v-if="canImport && !departmentPanelCollapsed" class="icon-button" type="button" title="批量导入用户" @click="openImportModal">
              <FileSpreadsheet :size="17" />
            </button>
            <button
              class="icon-button"
              type="button"
              :title="departmentPanelCollapsed ? '展开组织架构' : '折叠组织架构'"
              :aria-label="departmentPanelCollapsed ? '展开组织架构' : '折叠组织架构'"
              :aria-expanded="!departmentPanelCollapsed"
              @click="toggleDepartmentPanel"
            >
              <PanelLeftOpen v-if="departmentPanelCollapsed" :size="17" />
              <PanelLeftClose v-else :size="17" />
            </button>
          </div>
        </header>
        <div v-if="!departmentPanelCollapsed && visibleDepartments.length" class="user-department-tree">
          <button
            v-for="item in visibleDepartments"
            :key="item.department.id"
            type="button"
            :class="['user-department-tree-row', { active: selectedDepartmentId === item.department.id }]"
            :style="{ '--department-depth': item.depth }"
            @click="selectDepartment(item.department.id)"
          >
            <span
              :class="['department-expand', { placeholder: !item.hasChildren }]"
              @click.stop="item.hasChildren && toggleDepartment(item.department.id)"
            >
              <ChevronDown v-if="item.hasChildren && expandedDepartmentIds.has(item.department.id)" :size="15" />
              <ChevronRight v-else-if="item.hasChildren" :size="15" />
            </span>
            <Building2 v-if="item.department.is_default || item.department.org_type === 'company'" :size="16" />
            <Folder v-else :size="16" />
            <span class="department-tree-name" :title="item.department.name">{{ item.department.name }}</span>
            <b>{{ item.department.member_count || 0 }}</b>
          </button>
        </div>
        <p v-else-if="!departmentPanelCollapsed" class="department-tree-empty">暂无部门，请先到部门管理中创建</p>
      </aside>

      <div class="governance-card user-governance-card user-directory-pane">
        <header class="user-directory-title">
          <div>
            <span class="user-directory-icon"><UsersRound :size="18" /></span>
            <div>
              <h2>{{ selectedDepartment?.name || '请选择部门' }}</h2>
            </div>
          </div>
        </header>

        <div class="governance-toolbar user-toolbar crud-toolbar">
          <button
            v-if="canCreate"
            class="primary toolbar-primary-action"
            type="button"
            :disabled="!canCreateInSelectedDepartment"
            :title="canCreateInSelectedDepartment ? `新增到 ${selectedDepartment?.name}` : '默认组织不能新增用户，请选择具体部门'"
            @click="openCreate"
          >
            <Plus :size="16" />新增用户
          </button>
          <label class="search-box">
            <Search :size="16" />
            <input v-model="query" placeholder="搜索用户名、姓名、邮箱、手机号或角色" />
          </label>
          <div class="toolbar-actions">
            <button class="secondary action-refresh" type="button" :disabled="loading" @click="emit('reload')">
              <RefreshCw :size="16" :class="{ spin: loading }" />刷新
            </button>
          </div>
        </div>

        <p v-if="feedback" class="bastion-feedback user-directory-feedback">{{ feedback }}</p>

        <div class="governance-table user-table">
          <div class="governance-table-row table-head">
            <span class="sequence-col">序号</span>
            <span>用户名</span>
            <span>姓名</span>
            <span>邮箱</span>
            <span>手机</span>
            <span>角色</span>
            <span>状态</span>
            <span>OTP 状态</span>
            <span>操作</span>
          </div>
          <div v-for="(user, rowIndex) in paginatedUsers" :key="user.id" class="governance-table-row">
            <span class="sequence-col">{{ (currentPage - 1) * pageSize + rowIndex + 1 }}</span>
            <span>{{ user.username }}</span>
            <span>{{ displayName(user) }}</span>
            <span>{{ user.email || '未设置' }}</span>
            <span>{{ user.phone || '—' }}</span>
            <span><b class="badge role-badge">{{ user.is_system_admin ? '超级管理员' : roleLabel(user.role, roles) }}</b></span>
            <span><b :class="['badge', userStatusBadge(user).tone]">{{ userStatusBadge(user).label }}</b></span>
            <span><b :class="['badge', otpStatusBadge(user).tone]">{{ otpStatusBadge(user).label }}</b></span>
            <span class="row-actions">
              <button v-if="canUpdate" class="action-edit" title="编辑" @click="openEdit(user)"><Edit3 :size="15" />编辑</button>
              <button v-if="canDisable && !user.is_system_admin" :class="user.is_active ? 'action-toggle' : 'action-success'" :title="user.is_active ? '停用' : '启用'" @click="askToggleActive(user)">
                <UserRoundCheck :size="15" />{{ user.is_active ? '停用' : '启用' }}
              </button>
              <button v-if="canResetOtp" title="重置 OTP" :disabled="!user.otp_bound" @click="askResetOtp(user)">
                <KeyRound :size="15" />重置OTP
              </button>
              <button v-if="canDelete && !user.is_system_admin" title="删除" class="danger" @click="askDelete(user)"><Trash2 :size="15" />删除</button>
            </span>
          </div>
          <p v-if="!filteredUsers.length" class="empty-list">该部门暂无匹配用户</p>
        </div>

        <PaginationBar
          v-model:jump-page="jumpPage"
          :page-size="pageSize"
          :current-page="currentPage"
          :total-pages="totalPages"
          :page-start="pageStart"
          :page-end="pageEnd"
          :total="filteredUsers.length"
          @go="goPage"
          @move="movePage"
          @jump="applyJump"
        />
      </div>
    </div>
  </section>

  <ModalDialog
    :open="modalOpen"
    :title="editing ? '编辑用户' : '新增用户'"
    :description="editing ? '编辑用户资料不会改变其所属部门；部门调整请到部门管理完成。' : `新用户将加入部门：${selectedDepartment?.name || ''}`"
    @close="closeModal"
  >
    <form class="form-grid" @submit.prevent="saveUser">
      <label>用户名<input v-model.trim="form.username" required :disabled="Boolean(editing?.is_system_admin)" /></label>
      <label>邮箱<input v-model.trim="form.email" type="email" /></label>
      <label>姓名<input v-model.trim="form.full_name" /></label>
      <label>职位<input v-model.trim="form.title" /></label>
      <label>电话<input v-model.trim="form.phone" /></label>
      <label>密码
        <PasswordInput
          v-model="form.password"
          :min-length="passwordPolicy.min_length"
          autocomplete="new-password"
          :placeholder="editing ? '留空表示不修改密码' : `至少 ${passwordPolicy.min_length} 位；留空则自动生成`"
        />
        <small class="field-hint">{{ passwordPolicyHint }}</small>
        <small v-if="passwordError" class="field-hint password-policy-error">{{ passwordError }}</small>
      </label>
      <label>OTP 策略
        <CustomSelect v-model="form.otp_policy">
          <option value="inherit">跟随平台</option>
          <option value="required">强制启用</option>
          <option value="exempt">免于认证</option>
        </CustomSelect>
        <small class="field-hint">用户独立策略优先于平台默认 OTP 开关。</small>
      </label>
      <label class="check"><input v-model="form.is_active" type="checkbox" :disabled="Boolean(editing?.is_system_admin)" />允许登录</label>
      <p v-if="error" class="form-error">{{ error }}</p>
      <footer>
        <button class="secondary" type="button" @click="closeModal">取消</button>
        <button class="primary" :disabled="saving">{{ saving ? '处理中' : (editing ? '保存' : '确定') }}</button>
      </footer>
    </form>
  </ModalDialog>

  <ModalDialog
    :open="importModalOpen"
    title="批量导入用户"
    description="先下载最新模板填写，上传后必须通过全部预检查才能正式导入。"
    width="820px"
    @close="closeImportModal"
  >
    <form class="bastion-form user-import-form" @submit.prevent="confirmUserImport">
      <section class="user-import-steps wide">
        <article>
          <span>1</span>
          <div><strong>下载模板</strong><small>模板实时包含当前可用部门路径和身份。</small></div>
          <button class="secondary" type="button" :disabled="downloadingTemplate" @click="downloadImportTemplate">
            <Download :size="16" />{{ downloadingTemplate ? '下载中...' : '下载 Excel 模板' }}
          </button>
        </article>
        <article>
          <span>2</span>
          <div><strong>选择文件</strong><small>只支持最新模板填写的 .xlsx，最大 5 MB、1000 行。</small></div>
          <label class="user-import-file-button">
            <Upload :size="16" />选择 Excel
            <input ref="importFileInput" type="file" accept=".xlsx" @change="handleImportFileChange" />
          </label>
        </article>
        <article>
          <span>3</span>
          <div><strong>预检查</strong><small>{{ importFile?.name || '尚未选择文件' }}</small></div>
          <button class="secondary" type="button" :disabled="!importFile || precheckingImport" @click="precheckUserImport">
            <CheckCircle2 :size="16" />{{ precheckingImport ? '检查中...' : '开始预检查' }}
          </button>
        </article>
      </section>

      <p v-if="importError" class="form-error wide">{{ importError }}</p>
      <section v-if="importResult" class="user-import-result wide">
        <header>
          <div><span>总行数</span><b>{{ importResult.total_rows }}</b></div>
          <div class="valid"><span>通过</span><b>{{ importResult.valid_rows }}</b></div>
          <div :class="{ invalid: importResult.invalid_rows > 0 }"><span>异常</span><b>{{ importResult.invalid_rows }}</b></div>
        </header>
        <p :class="importResult.can_import ? 'bastion-feedback' : 'bastion-error'">
          {{ importResult.can_import ? '全部数据检查通过，可以正式导入。' : '存在异常数据，整批暂不允许导入，请修正 Excel 后重新上传。' }}
        </p>
        <div class="user-import-preview">
          <div class="user-import-preview-row table-head">
            <span>Excel 行</span><span>用户名</span><span>姓名</span><span>所属部门</span><span>检查结果</span>
          </div>
          <div v-for="row in importResult.rows" :key="row.row_number" class="user-import-preview-row">
            <span>{{ row.row_number }}</span>
            <span>{{ row.username }}</span>
            <span>{{ row.name }}</span>
            <span :title="row.department">{{ row.department }}</span>
            <span :class="row.status === 'valid' ? 'import-row-valid' : 'import-row-invalid'">
              <CheckCircle2 v-if="row.status === 'valid'" :size="15" />
              <XCircle v-else :size="15" />
              {{ row.errors.length ? row.errors.join('；') : '通过' }}
            </span>
          </div>
        </div>
      </section>

      <footer>
        <button class="secondary" type="button" :disabled="precheckingImport || importingUsers" @click="closeImportModal">取消</button>
        <button class="primary" type="submit" :disabled="!importResult?.can_import || importingUsers">
          {{ importingUsers ? '导入中...' : '确认导入' }}
        </button>
      </footer>
    </form>
  </ModalDialog>

  <ConfirmDialog
    :open="deleteOpen"
    title="删除用户"
    :message="`确认删除用户 ${deleting?.username || ''}？删除后该账号将无法登录。`"
    :loading="deletingNow"
    @cancel="deleteOpen = false"
    @confirm="confirmDelete"
  />
  <ConfirmDialog
    :open="activeOpen"
    :title="activeTarget?.is_active ? '禁用用户' : '启用用户'"
    :message="`确定${activeTarget?.is_active ? '禁用' : '启用'}用户 ${activeTarget?.username || ''}？${activeTarget?.password_expired_locked ? '启用后会重新计算密码修改周期。' : ''}`"
    :confirm-text="activeTarget?.is_active ? '确定禁用' : '确定启用'"
    :loading="activeNow"
    @cancel="activeOpen = false"
    @confirm="confirmToggleActive"
  />
  <ConfirmDialog
    :open="otpResetOpen"
    title="重置 OTP"
    :message="`确认重置用户 ${otpResetTarget?.username || ''} 的 OTP？旧令牌和已登录会话将立即失效；如果当前策略要求 OTP，下次登录必须重新绑定。`"
    confirm-text="确定重置"
    :loading="otpResetting"
    @cancel="otpResetOpen = false"
    @confirm="confirmResetOtp"
  />
</template>
