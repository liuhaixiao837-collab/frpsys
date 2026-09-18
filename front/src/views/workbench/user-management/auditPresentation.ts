import type { AuditLogRow } from './types'

export type AuditDetailItem = { label: string; value: string }

const actionLabels: Record<string, string> = {
  'auth.login': '登录系统',
  'auth.login.success': '登录成功',
  'auth.login.failed': '登录失败',
  'auth.switch_org': '切换部门',
  'User.create': '新增用户',
  'User.update': '编辑用户',
  'User.delete': '删除用户',
  'User.import': '批量导入用户',
  'User.otp_bind': '绑定 OTP',
  'User.otp_reset': '重置 OTP',
  'User.password_expired_disable': '密码过期禁用用户',
  'User.password_expired_lock_restored': '解除超级管理员密码过期锁定',
  'Organization.create': '新增部门',
  'Organization.update': '编辑部门',
  'Organization.delete': '删除部门',
  'Organization.add_member': '添加部门成员',
  'Organization.invite_member': '邀请部门成员',
  'Organization.remove_member': '移出部门成员',
  'Role.create': '新增角色',
  'Role.update': '编辑角色',
  'Role.delete': '删除角色',
  'PermissionPolicy.create': '新增权限策略',
  'PermissionPolicy.update': '编辑权限策略',
  'PermissionPolicy.delete': '删除权限策略',
  'SystemSetting.create': '新增平台设置',
  'SystemSetting.update': '编辑平台设置',
  'SystemSetting.delete': '删除平台设置',
  'SystemSetting.license_import': '导入 Licence',
  'SystemSetting.test_email': '发送测试邮件',
  'SystemSetting.test_sms': '发送测试短信',
  'MenuOrder.update': '调整主菜单顺序',
  'AuditLog.export': '导出日志',
}

const resourceNames: Record<string, string> = {
  User: '用户', Organization: '部门', Role: '角色', PermissionPolicy: '权限策略', AuditLog: '日志',
  SystemSetting: '平台设置', MenuOrder: '菜单排序', auth: '账号安全',
}

const endpointNames: Record<string, string> = {
  users: '用户', organizations: '部门', roles: '角色', permissions: '权限策略',
  settings: '平台设置',
}

const fieldLabels: Record<string, string> = {
  id: '记录编号', role: '角色', status: '状态', parent_id: '上级编号', is_default: '是否默认',
  user_id: '用户编号', username: '用户名', moved_to: '转移到部门', subject_type: '授权对象类型',
  files: '文件数量', decision: '审批决定', ticket: '审批单编号', result: '执行结果',
  file_path: '文件位置', updated: '处理数量', type: '类型', rows: '数据条数',
  command_log_id: '命令记录编号', command: '执行命令', blocked: '是否阻断', risk_level: '风险等级',
  reason: '原因', asset: '资产编号', template: '模板编号', detail: '处理说明', message: '处理说明',
  auth_method: '登录方式',
  gateway: '访问网关', duration: '持续时间', session_id: '会话编号', account_id: '账号编号',
  asset_id: '资产编号', summary: '统计摘要', sections: '变更配置项', key: '配置项',
  before_order: '调整前顺序', after_order: '调整后顺序',
  otp_policy: 'OTP 策略',
  channel: '通知渠道',
  start_time: '开始时间', end_time: '结束时间',
}

const valueLabels: Record<string, string> = {
  available: '可用', unavailable: '不可用', disabled: '已禁用', enabled: '已启用',
  pending: '待处理', processing: '处理中', approved: '已通过', rejected: '已驳回',
  completed: '已完成', failed: '失败', cancelled: '已取消', success: '成功',
  allow: '允许', deny: '拒绝', user: '用户', department: '部门', all: '全部对象',
  approval: '需要审批', direct: '直接执行', upload: '上传', download: '下载', copy: '服务器间拷贝',
  inherit: '跟随平台', required: '强制启用', exempt: '免于认证',
  email: '邮件', sms: '短信',
}

const operationWords: Record<string, string> = {
  create: '新增资源', update: '编辑资源', delete: '删除资源', enable: '启用资源', disable: '禁用资源',
  save: '保存设置', test: '执行测试', check: '执行检查', approve: '通过审批', reject: '驳回审批',
  cancel: '取消操作', connect: '建立连接', disconnect: '断开连接', execute: '执行操作',
  generate: '生成内容', download: '下载文件', upload: '上传文件', cleanup: '清理数据', share: '分享资源',
}

const httpActionLabels: Record<string, string> = {
  post: '新增或提交操作',
  put: '编辑操作',
  patch: '编辑操作',
  delete: '删除操作',
}

/**
 * 封装 actionResourceName 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`action` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function actionResourceName(action: string) {
  const parts = action.split('.')
  for (const part of parts) {
    if (resourceNames[part]) return resourceNames[part]
  }
  return '业务资源'
}

/**
 * 判断 isTechnicalAudit 对应的业务条件是否成立。
 * 参数：`log` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function isTechnicalAudit(log: AuditLogRow) {
  return /^http\./i.test(log.action) || /^\/api\//i.test(log.resource || '') && /^http/i.test(log.action)
}

/**
 * 封装 auditActionLabel 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`action` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function auditActionLabel(action: string) {
  if (actionLabels[action]) return actionLabels[action]
  if (/^http\./i.test(action)) {
    const method = action.split('.').at(-1)?.toLowerCase()
    return httpActionLabels[method || ''] || '执行业务操作'
  }
  if (/^[\u3400-\u9fff]/.test(action)) return action
  const operation = action.split('.').at(-1) || action
  const operationLabel = operationWords[operation]
  if (operationLabel) {
    const resource = actionResourceName(action)
    return operationLabel.replace('资源', resource)
  }
  return '执行业务操作'
}

/**
 * 封装 auditActionKind 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`action` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function auditActionKind(action: string) {
  const normalized = action.toLowerCase()
  if (normalized.includes('login')) return 'login'
  if (normalized.includes('delete') || normalized.includes('cleanup')) return 'delete'
  if (normalized.includes('create') || normalized.includes('invite') || normalized.includes('add_')) return 'create'
  if (normalized.includes('update') || normalized.includes('save') || normalized.includes('rotate')) return 'update'
  if (normalized.includes('enable') || normalized.includes('unlock')) return 'enable'
  if (normalized.includes('disable') || normalized.includes('lock')) return 'disable'
  if (normalized.includes('approve')) return 'approve'
  if (normalized.includes('reject')) return 'reject'
  if (normalized.includes('connect')) return 'connect'
  if (normalized.includes('disconnect') || normalized.includes('cancel')) return 'disconnect'
  if (normalized.includes('upload')) return 'upload'
  if (normalized.includes('download') || normalized.includes('export')) return 'download'
  if (normalized.includes('execute') || normalized.includes('command') || normalized.includes('run')) return 'execute'
  return 'other'
}

/**
 * 封装 auditActionTone 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`action` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function auditActionTone(action: string) {
  const kind = auditActionKind(action)
  if (kind === 'delete' || kind === 'reject') return 'audit-tone-danger'
  if (kind === 'disable' || kind === 'disconnect') return 'audit-tone-warning'
  if (kind === 'create' || kind === 'enable' || kind === 'approve') return 'audit-tone-success'
  return 'audit-tone-info'
}

/**
 * 封装 auditResourceType 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`log` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function auditResourceType(log: AuditLogRow) {
  const first = log.action.split('.')[0]
  if (resourceNames[first]) return resourceNames[first]
  const model = log.action.split('.')[0]
  if (resourceNames[model]) return resourceNames[model]
  if (log.resource?.startsWith('/api/')) {
    const endpoint = log.resource.split('/').filter(Boolean).find((part) => endpointNames[part])
    if (endpoint) return endpointNames[endpoint]
  }
  return '其他资源'
}

/**
 * 封装 auditResourceLabel 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`log` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function auditResourceLabel(log: AuditLogRow) {
  const resource = String(log.resource || '').trim()
  const type = auditResourceType(log)
  if (!resource) return type
  const frameworkObject = resource.match(/^[A-Za-z_][\w.]*\s+object\s+\(([^)]+)\)$/i)
  if (frameworkObject) return `${type} #${frameworkObject[1]}`
  if (resource.startsWith('/api/')) {
    const parts = resource.split('/').filter(Boolean)
    const endpointIndex = parts.findIndex((part) => Boolean(endpointNames[part]))
    const id = endpointIndex >= 0 ? parts[endpointIndex + 1] : ''
    return id && /^\d+$/.test(id) ? `${type} #${id}` : type
  }
  if (resource === type || resource.startsWith(`${type}：`)) return resource
  return `${type}：${resource}`
}

/**
 * 将审计详情值转换为安全且用户友好的展示文字。
 * 参数：`value` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function detailValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未设置'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return String(value)
  if (typeof value === 'string') return valueLabels[value.toLowerCase()] || value
  if (Array.isArray(value)) return value.length ? value.map(detailValue).join('、') : '无'
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !/(password|secret|token|credential)/i.test(key))
      .map(([key, nested]) => `${fieldLabels[key] || '相关信息'}：${detailValue(nested)}`)
    return entries.length ? entries.join('；') : '无补充信息'
  }
  return String(value)
}

/**
 * 封装 auditDetailItems 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`detail` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function auditDetailItems(detail: Record<string, unknown> = {}): AuditDetailItem[] {
  return Object.entries(detail)
    .filter(([key]) => !/(password|secret|token|credential)/i.test(key))
    .map(([key, value]) => ({ label: fieldLabels[key] || '相关信息', value: detailValue(value) }))
}
