import { formatPlatformDateTime } from '../../../utils/dateTime'

export type UserRow = {
  id: number
  username: string
  first_name: string
  last_name: string
  email: string
  is_active: boolean
  is_system_admin: boolean
  role: string
  role_id?: number | null
  role_name?: string
  permissions?: string[]
  title: string
  phone: string
  organization: string
  organization_id?: number | null
  department?: string
  department_id?: number | null
  password_changed_at?: string | null
  password_expired_locked?: boolean
  otp_policy: 'inherit' | 'required' | 'exempt'
  otp_effective_enabled: boolean
  otp_bound: boolean
  otp_status: 'disabled' | 'pending' | 'bound' | 'locked' | 'exempt'
  otp_status_label: string
  date_joined?: string
  last_login?: string | null
}

export type PasswordPolicy = {
  min_length: number
  require_uppercase: boolean
  require_lowercase: boolean
  require_number: boolean
  require_special: boolean
  exclude_username: boolean
  max_age_days: number
}

export type DepartmentRow = {
  id: number
  name: string
  slug: string
  description: string
  region: string
  parent_id?: number | null
  parent_name?: string
  org_type: 'company' | 'department' | string
  is_default: boolean
  is_root: boolean
  member_count: number
  children_count: number
  created_at: string
  updated_at: string
  children?: DepartmentRow[]
}

export type OrganizationRow = DepartmentRow

export type RoleRow = {
  id: number
  code: string
  name: string
  description: string
  rank: number
  is_system: boolean
  is_active: boolean
  assigned_count: number
  created_at: string
  updated_at: string
}

export type AuditLogRow = {
  id: number
  actor: string
  action: string
  resource: string
  ip_address: string
  detail: Record<string, unknown>
  organization?: number | null
  created_at: string
  updated_at: string
}

export type PermissionAction = {
  code: string
  name: string
}

export type PermissionPage = {
  code: string
  name: string
  path: string
  actions: PermissionAction[]
  children?: PermissionPage[]
}

export type PermissionGroup = {
  code: string
  name: string
  pages: PermissionPage[]
}

export type PermissionRuleRow = {
  id?: number
  permission_code: string
  effect: 'allow' | 'deny'
  effect_label?: string
}

export type PermissionPolicyRow = {
  id: number
  name: string
  subject_type: 'department' | 'user'
  subject_name: string
  subject_label: string
  department?: number | null
  user?: number | null
  priority: number
  status: 'available' | 'disabled'
  remark: string
  rules: PermissionRuleRow[]
  created_at: string
  updated_at: string
}

/**
 * 封装 roleLabel 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`role` 表示该步骤所需的业务参数；`roles` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function roleLabel(role: string, roles: RoleRow[] = []) {
  return roles.find((item) => item.code === role)?.name || role || '未设置'
}

/**
 * 将业务值转换为 displayName 对应的用户友好文字。
 * 参数：`user` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function displayName(user: UserRow) {
  const fullName = `${user.last_name || ''}${user.first_name || ''}`.trim()
  return fullName || user.username
}

/**
 * 将业务值转换为 formatDateTime 对应的用户友好文字。
 * 参数：`value` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function formatDateTime(value?: string | null) {
  return formatPlatformDateTime(value)
}
