<script setup lang="ts">
import { Bot, CheckCircle2, Edit3, FileKey2, KeyRound, ListFilter, LoaderCircle, LogIn, Mail, MessageSquareText, Plus, RadioTower, Send, ShieldBan, ShieldCheck, Stamp, Trash2, Upload } from 'lucide-vue-next'
import { computed, reactive, ref } from 'vue'

import { api } from '../../api'
import CustomSelect from '../../components/CustomSelect.vue'
import ModalDialog from '../../components/ModalDialog.vue'
import PasswordInput from '../../components/PasswordInput.vue'
import SystemWatermark from '../../components/SystemWatermark.vue'
import { actionPermissionForPath } from '../../permissions'
import { useAuthStore } from '../../stores/auth'
import { usePlatformStore } from '../../stores/platform'
import PaginationBar from './user-management/PaginationBar.vue'
import { usePager } from './user-management/usePager'

type SettingRow = {
  id?: number
  key: string
  value?: Record<string, any>
  description?: string
}

type AccessEntry = {
  address: string
  description: string
}

type SecurityTab = 'whitelist' | 'password' | 'login' | 'llm' | 'notification' | 'watermark' | 'license'
type LoginEditSection = 'authentication' | 'lock'
type NotificationEditChannel = 'email' | 'sms'
type NotificationTestChannel = 'email' | 'sms'
type LlmProviderStatus = 'unchecked' | 'available' | 'unavailable'
type LlmProvider = {
  name: string
  code: string
  model: string
  priority: number
  enabled: boolean
  api_key: string
  base_url: string
  status: LlmProviderStatus
  last_checked_at: string
  description: string
}

const props = defineProps<{
  activeTab: SecurityTab
  items: SettingRow[]
}>()
const emit = defineEmits<{ refresh: [] }>()
const auth = useAuthStore()
const platform = usePlatformStore()
const canCreate = computed(() => auth.can(actionPermissionForPath('/settings', 'create')))
const canUpdate = computed(() => auth.can(actionPermissionForPath('/settings', 'update')))
const canTestEmail = computed(() => auth.can(actionPermissionForPath('/settings', 'test_email')))
const canTestSms = computed(() => auth.can(actionPermissionForPath('/settings', 'test_sms')))
const canTestLlm = computed(() => canUpdate.value)

const modalOpen = ref(false)
const loginEditSection = ref<LoginEditSection>('authentication')
const notificationEditChannel = ref<NotificationEditChannel>('email')
const saving = ref(false)
const error = ref('')
const notificationTestOpen = ref(false)
const notificationTestChannel = ref<NotificationTestChannel>('email')
const notificationTesting = ref(false)
const notificationTestError = ref('')
const notificationTestResult = ref('')
const notificationTestForm = reactive({ recipient: '', phone: '' })
const editingLlmCode = ref('deepseek')
const llmTestingCode = ref('')
const llmTestMessages = reactive<Record<string, { kind: 'success' | 'error', text: string }>>({})
const llmStatusOverrides = reactive<Record<string, { status: LlmProviderStatus, last_checked_at: string }>>({})
const whitelistEntries = ref<AccessEntry[]>([])
const whitelistForm = reactive({ enabled: false })
const blacklistEntries = ref<AccessEntry[]>([])
const blacklistForm = reactive({ enabled: false })
const accessPageSize = 10
const whitelistRows = computed(() => whitelistEntries.value.map((entry, index) => ({ entry, index })))
const blacklistRows = computed(() => blacklistEntries.value.map((entry, index) => ({ entry, index })))
const {
  currentPage: whitelistPage,
  jumpPage: whitelistJumpPage,
  totalPages: whitelistTotalPages,
  paginatedItems: paginatedWhitelistRows,
  pageStart: whitelistPageStart,
  pageEnd: whitelistPageEnd,
  goPage: goWhitelistPage,
  movePage: moveWhitelistPage,
  applyJump: applyWhitelistJump,
  resetPage: resetWhitelistPage,
} = usePager(whitelistRows, accessPageSize)
const {
  currentPage: blacklistPage,
  jumpPage: blacklistJumpPage,
  totalPages: blacklistTotalPages,
  paginatedItems: paginatedBlacklistRows,
  pageStart: blacklistPageStart,
  pageEnd: blacklistPageEnd,
  goPage: goBlacklistPage,
  movePage: moveBlacklistPage,
  applyJump: applyBlacklistJump,
  resetPage: resetBlacklistPage,
} = usePager(blacklistRows, accessPageSize)
const licenseContent = ref('')
const licenseFileName = ref('')
const passwordForm = reactive({
  min_length: 8,
  require_uppercase: true,
  require_lowercase: true,
  require_number: true,
  require_special: true,
  exclude_username: true,
  max_age_days: 30,
})
const loginForm = reactive({
  captcha_enabled: true,
  slider_captcha_enabled: true,
  otp_enabled: false,
  sms_login_enabled: false,
  login_failure_limit: 5,
  login_lock_minutes: 30,
  ip_failure_limit: 20,
  ip_lock_minutes: 30,
  otp_failure_limit: 5,
  otp_lock_minutes: 20,
  sms_failure_limit: 5,
  sms_lock_minutes: 20,
})
const watermarkForm = reactive({
  enabled: false,
  content_type: 'username_ip' as 'username' | 'username_ip' | 'platform' | 'custom',
  custom_text: '',
  layout: 'tiled' as 'tiled' | 'center',
  show_time: true,
  font_size: 14,
  font_weight: 500 as 400 | 500 | 600,
  color: '#64748b',
  opacity: 0.14,
  rotate: -24,
  horizontal_gap: 220,
  vertical_gap: 140,
})
const notificationForm = reactive({
  email: {
    enabled: false,
    smtp_host: '',
    smtp_port: 465,
    security: 'ssl',
    sender_email: '',
    username: '',
    password: '',
    recipient_limit_per_minute: 5,
    recipient_limit_per_hour: 100,
    recipient_limit_per_day: 500,
  },
  sms: {
    enabled: false,
    provider: 'aliyun',
    access_key_id: '',
    access_key_secret: '',
    secret_id: '',
    secret_key: '',
    sdk_app_id: '',
    sign_name: '',
    signature_id: '',
    authorization_token: '',
    api_key: '',
    app_key: '',
    app_secret: '',
    template_code: '',
    recipient_limit_per_minute: 1,
    recipient_limit_per_hour: 10,
    recipient_limit_per_day: 50,
  },
})
const llmProviderDefaults: LlmProvider[] = [
  { name: '深度求索', code: 'deepseek', model: 'deepseek-v4', priority: 10, enabled: false, api_key: '', base_url: 'https://api.deepseek.com/v1', status: 'unchecked', last_checked_at: '', description: 'DeepSeek 通用大语言模型服务。' },
  { name: '通义千问', code: 'qwen', model: 'qwen-plus', priority: 20, enabled: false, api_key: '', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', status: 'unchecked', last_checked_at: '', description: '阿里云百炼通义千问模型服务。' },
  { name: '智谱清言', code: 'glm', model: 'glm-4.5', priority: 30, enabled: false, api_key: '', base_url: 'https://open.bigmodel.cn/api/paas/v4', status: 'unchecked', last_checked_at: '', description: '智谱 AI GLM 系列模型服务。' },
  { name: '月之暗面', code: 'kimi', model: 'kimi-k2-turbo-preview', priority: 40, enabled: false, api_key: '', base_url: 'https://api.moonshot.cn/v1', status: 'unchecked', last_checked_at: '', description: 'Moonshot AI Kimi 系列模型服务。' },
  { name: 'OpenAI', code: 'openai', model: 'gpt-5.6', priority: 50, enabled: false, api_key: '', base_url: 'https://api.openai.com/v1', status: 'unchecked', last_checked_at: '', description: 'OpenAI GPT 系列模型服务。' },
  { name: '小米 MiMo', code: 'mimo', model: 'MiMo-V2.5', priority: 60, enabled: false, api_key: '', base_url: 'https://api.xiaomimimo.com/v1', status: 'unchecked', last_checked_at: '', description: '小米 MiMo 系列模型服务。' },
]
const llmForm = reactive<LlmProvider>({ ...llmProviderDefaults[0] })

const settingKeys: Record<SecurityTab, string> = {
  whitelist: 'security.login_whitelist',
  password: 'security.password_policy',
  login: 'security.login',
  llm: 'llm.providers',
  notification: 'notification.delivery',
  watermark: 'security.watermark',
  license: 'license.management',
}

const currentSetting = computed(() => props.items.find((item) => item.key === settingKeys[props.activeTab]))
const canEdit = computed(() => currentSetting.value?.id ? canUpdate.value : canCreate.value)
const whitelistValue = computed(() => ({
  enabled: false,
  entries: [] as string[],
  descriptions: {} as Record<string, string>,
  ...(props.items.find((item) => item.key === settingKeys.whitelist)?.value || {}),
}))
const blacklistValue = computed(() => ({
  enabled: false,
  entries: [] as string[],
  descriptions: {} as Record<string, string>,
  ...(props.items.find((item) => item.key === 'security.login_blacklist')?.value || {}),
}))
const licenseValue = computed(() => ({
  configured: false,
  status: 'unconfigured',
  status_label: '未配置',
  instance_id: '',
  license_id: '',
  customer: '',
  license_type: '',
  effective_time: '',
  expire_time: '',
  max_users: 0,
  max_concurrency: 0,
  days_remaining: 0,
  verification: '',
  unavailable_reason: '',
  ...(props.items.find((item) => item.key === settingKeys.license)?.value || {}),
}))
const passwordValue = computed(() => ({
  min_length: 8,
  require_uppercase: true,
  require_lowercase: true,
  require_number: true,
  require_special: true,
  exclude_username: true,
  max_age_days: 30,
  ...(props.items.find((item) => item.key === settingKeys.password)?.value || {}),
}))
const loginValue = computed(() => ({
  captcha_enabled: true,
  slider_captcha_enabled: true,
  otp_enabled: false,
  sms_login_enabled: false,
  login_failure_limit: 5,
  login_lock_minutes: 30,
  ip_failure_limit: 20,
  ip_lock_minutes: 30,
  otp_failure_limit: 5,
  otp_lock_minutes: 20,
  sms_failure_limit: 5,
  sms_lock_minutes: 20,
  ...(props.items.find((item) => item.key === settingKeys.login)?.value || {}),
}))
const watermarkValue = computed(() => ({
  enabled: false,
  content_type: 'username_ip' as 'username' | 'username_ip' | 'platform' | 'custom',
  custom_text: '',
  layout: 'tiled' as 'tiled' | 'center',
  show_time: true,
  font_size: 14,
  font_weight: 500 as 400 | 500 | 600,
  color: '#64748b',
  opacity: 0.14,
  rotate: -24,
  horizontal_gap: 220,
  vertical_gap: 140,
  ...(props.items.find((item) => item.key === settingKeys.watermark)?.value || {}),
}))
const notificationValue = computed(() => {
  const saved = props.items.find((item) => item.key === settingKeys.notification)?.value || {}
  return {
    email: {
      enabled: false,
      smtp_host: '',
      smtp_port: 465,
      security: 'ssl',
      sender_email: '',
      username: '',
      password: '',
      recipient_limit_per_minute: 5,
      recipient_limit_per_hour: 100,
      recipient_limit_per_day: 500,
      ...(saved.email || {}),
    },
    sms: {
      enabled: false,
      provider: 'aliyun',
      access_key_id: '',
      access_key_secret: '',
      secret_id: '',
      secret_key: '',
      sdk_app_id: '',
      sign_name: '',
      signature_id: '',
      authorization_token: '',
      api_key: '',
      app_key: '',
      app_secret: '',
      template_code: '',
      recipient_limit_per_minute: 1,
      recipient_limit_per_hour: 10,
      recipient_limit_per_day: 50,
      ...(saved.sms || {}),
    },
  }
})
const llmValue = computed<LlmProvider[]>(() => {
  const saved = props.items.find((item) => item.key === settingKeys.llm)?.value?.providers
  const savedProviders = Array.isArray(saved) ? saved : []
  return llmProviderDefaults.map((fallback) => {
    const provider = savedProviders.find((item: LlmProvider) => item?.code === fallback.code) || {}
    const override = llmStatusOverrides[fallback.code] || {}
    return { ...fallback, ...provider, ...override }
  })
})
const smsProviders = [
  { code: 'aliyun', name: '阿里云短信', required: ['access_key_id', 'access_key_secret', 'sign_name', 'template_code'] },
  { code: 'tencent', name: '腾讯云短信', required: ['secret_id', 'secret_key', 'sdk_app_id', 'sign_name', 'template_code'] },
  { code: 'baidu', name: '百度云短信', required: ['access_key_id', 'access_key_secret', 'signature_id', 'template_code'] },
  { code: 'upyun', name: '又拍云短信', required: ['authorization_token', 'template_code'] },
  { code: 'qiniu', name: '七牛云短信', required: ['access_key_id', 'access_key_secret', 'template_code'] },
  { code: 'yunpian', name: '云片网短信', required: ['api_key', 'template_code'] },
  { code: 'netease', name: '网易云信短信', required: ['app_key', 'app_secret', 'template_code'] },
] as const

/**
 * 获取指定代码对应的短信服务商配置元数据。
 * 参数：`provider` 为短信服务商代码。
 * 返回：匹配的服务商配置，未知代码回退到阿里云。
 * 副作用：无。
 */
function smsProvider(provider: string) {
  return smsProviders.find((item) => item.code === provider) || smsProviders[0]
}

/**
 * 获取短信服务商的中文展示名称。
 * 参数：`provider` 为短信服务商代码。
 * 返回：服务商中文名称。
 * 副作用：无。
 */
function smsProviderLabel(provider: string) {
  return smsProvider(provider).name
}

const smsOverviewFields = computed(() => {
  const sms = notificationValue.value.sms as Record<string, any>
  const fields: Record<string, Array<{ key: string, label: string, sensitive?: boolean }>> = {
    aliyun: [
      { key: 'access_key_id', label: 'AccessKey ID' },
      { key: 'access_key_secret', label: 'AccessKey Secret', sensitive: true },
      { key: 'sign_name', label: '短信签名' },
    ],
    tencent: [
      { key: 'secret_id', label: 'SecretId', sensitive: true },
      { key: 'secret_key', label: 'SecretKey', sensitive: true },
      { key: 'sdk_app_id', label: 'SmsSdkAppId' },
      { key: 'sign_name', label: '短信签名' },
    ],
    baidu: [
      { key: 'access_key_id', label: 'AccessKey ID' },
      { key: 'access_key_secret', label: 'AccessKey Secret', sensitive: true },
      { key: 'signature_id', label: '签名 ID' },
    ],
    upyun: [{ key: 'authorization_token', label: 'Authorization Token', sensitive: true }],
    qiniu: [
      { key: 'access_key_id', label: 'AccessKey ID' },
      { key: 'access_key_secret', label: 'AccessKey Secret', sensitive: true },
    ],
    yunpian: [{ key: 'api_key', label: 'API Key', sensitive: true }],
    netease: [
      { key: 'app_key', label: 'AppKey' },
      { key: 'app_secret', label: 'AppSecret', sensitive: true },
    ],
  }
  return (fields[sms.provider] || fields.aliyun).map((field) => ({
    ...field,
    value: field.sensitive ? (sms[field.key] ? '已安全配置' : '未配置') : (sms[field.key] || '未配置'),
  }))
})
const platformDisplayName = computed(() => platform.name || 'Ongrid')
const emailTestReady = computed(() => {
  const email = notificationValue.value.email
  return Boolean(email.enabled && email.smtp_host && email.smtp_port && email.sender_email && email.username && email.password)
})
const smsTestReady = computed(() => {
  const sms = notificationValue.value.sms as Record<string, any>
  return Boolean(sms.enabled && smsProvider(sms.provider).required.every((field) => sms[field]))
})
const notificationTestTitle = computed(() => (
  notificationTestChannel.value === 'email' ? '发送测试邮件' : '发送测试短信'
))
const notificationTestDescription = computed(() => (
  notificationTestChannel.value === 'email'
    ? '向指定邮箱发送一封格式化测试邮件。'
    : `使用已保存的${smsProviderLabel(notificationValue.value.sms.provider)}模板发送验证码。`
))

const tabTitle = computed(() => ({
  whitelist: '访问限制',
  password: '密码策略',
  login: '登录设置',
  llm: 'LLM配置',
  notification: '通知设置',
  watermark: '水印设置',
  license: 'Licence管理',
}[props.activeTab]))
const modalTitle = computed(() => {
  if (props.activeTab === 'llm') return `编辑 ${llmForm.name}`
  if (props.activeTab === 'notification') {
    return notificationEditChannel.value === 'email' ? '编辑发件箱邮箱' : '编辑短信网关'
  }
  if (props.activeTab !== 'login') return `编辑${tabTitle.value}`
  return loginEditSection.value === 'authentication' ? '编辑登录认证设置' : '编辑登录锁定策略'
})

const licenseStatusClass = computed(() => ({
  valid: 'healthy',
  expired: 'offline',
  unavailable: 'offline',
  unconfigured: 'pending',
}[licenseValue.value.status] || 'pending'))

/** 返回水印内容类型对应的商业化展示名称。 */
function watermarkContentLabel(contentType: string) {
  return {
    username: '登录用户',
    username_ip: '登录用户 + 访问 IP',
    platform: '平台名称',
    custom: '自定义文字',
  }[contentType] || contentType
}

/** 返回水印布局代码对应的中文名称。 */
function watermarkLayoutLabel(layout: string) {
  return layout === 'center' ? '页面居中' : '全屏平铺'
}

/**
 * 返回邮件连接安全代码对应的显示名称。
 * 参数：`security` 为邮件连接安全方式代码。
 * 返回：SSL、STARTTLS 或不加密的中文显示文字。
 * 副作用：不修改配置或页面状态。
 */
function emailSecurityLabel(security: string) {
  return {
    ssl: 'SSL/TLS',
    starttls: 'STARTTLS',
    none: '不加密',
  }[security] || security
}

/**
 * 将密码策略布尔值转换为统一状态文字。
 * 参数：`enabled` 表示规则是否启用。
 * 返回：启用或不要求的中文状态。
 * 副作用：不修改持久化数据。
 */
function ruleLabel(enabled: boolean) {
  return enabled ? '必须包含' : '不作要求'
}

/**
 * 将 Licence ISO 时间转换为中文本地时间。
 * 参数：`value` 为后端返回的 ISO 8601 时间。
 * 返回：中文日期时间，空值返回未设置。
 * 副作用：不修改持久化数据。
 */
function formatDateTime(value: string) {
  if (!value) return '未设置'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(new Date(value))
}

/**
 * 按当前 Tab 把已保存配置填入编辑表单并打开弹窗。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：更新当前组件表单和弹窗状态。
 */
function openEdit() {
  if (!canEdit.value) return
  error.value = ''
  if (props.activeTab === 'whitelist') {
    whitelistForm.enabled = Boolean(whitelistValue.value.enabled)
    whitelistEntries.value = (whitelistValue.value.entries || []).map((address) => ({
      address,
      description: whitelistValue.value.descriptions?.[address] || '',
    }))
    blacklistForm.enabled = Boolean(blacklistValue.value.enabled)
    blacklistEntries.value = (blacklistValue.value.entries || []).map((address) => ({
      address,
      description: blacklistValue.value.descriptions?.[address] || '',
    }))
    resetWhitelistPage()
    resetBlacklistPage()
  } else if (props.activeTab === 'password') {
    Object.assign(passwordForm, passwordValue.value)
  } else if (props.activeTab === 'login') {
    Object.assign(loginForm, loginValue.value)
  } else if (props.activeTab === 'llm') {
    const provider = llmValue.value.find((item) => item.code === editingLlmCode.value)
    if (provider) Object.assign(llmForm, provider)
  } else if (props.activeTab === 'notification') {
    if (notificationEditChannel.value === 'email') {
      Object.assign(notificationForm.email, notificationValue.value.email)
    } else {
      Object.assign(notificationForm.sms, notificationValue.value.sms)
    }
  } else if (props.activeTab === 'watermark') {
    Object.assign(watermarkForm, watermarkValue.value)
  } else {
    licenseContent.value = ''
    licenseFileName.value = ''
  }
  modalOpen.value = true
}

/**
 * 打开指定 LLM 厂商的独立编辑弹窗。
 * 参数：`code` 为六家内置厂商之一。
 * 返回：无显式返回值。
 * 副作用：切换正在编辑的厂商并打开设置弹窗。
 */
function openLlmEdit(code: string) {
  editingLlmCode.value = code
  openEdit()
}

/**
 * 返回 LLM 检测状态对应的中文名称。
 * 参数：`providerStatus` 为未检测、可用或不可用状态。
 * 返回：用于卡片展示的状态文字。
 * 副作用：无。
 */
function llmStatusLabel(providerStatus: LlmProviderStatus) {
  return { unchecked: '未检测', available: '可用', unavailable: '不可用' }[providerStatus]
}

/**
 * 返回 LLM 检测状态对应的现有徽标样式。
 * 参数：`providerStatus` 为厂商检测状态。
 * 返回：健康、离线或待处理样式名称。
 * 副作用：无。
 */
function llmStatusClass(providerStatus: LlmProviderStatus) {
  return { unchecked: 'pending', available: 'healthy', unavailable: 'offline' }[providerStatus]
}

/**
 * 将 LLM 最近检测时间转换为中文本地时间。
 * 参数：`value` 为后端返回的 ISO 8601 时间。
 * 返回：本地日期时间，未检测时返回空字符串。
 * 副作用：无。
 */
function formatLlmCheckedAt(value: string) {
  if (!value) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(new Date(value))
}

/**
 * 调用后端真实检测指定 LLM 厂商并刷新卡片状态。
 * 参数：`provider` 为当前卡片厂商配置。
 * 返回：无显式返回值。
 * 副作用：发送检测请求、更新临时状态并重新读取平台设置。
 */
async function testLlmProvider(provider: LlmProvider) {
  if (!canTestLlm.value || llmTestingCode.value) return
  llmTestingCode.value = provider.code
  delete llmTestMessages[provider.code]
  try {
    const result = await api('/system-settings/llm/test/', {
      method: 'POST',
      body: JSON.stringify({ provider: provider.code }),
    })
    llmStatusOverrides[provider.code] = {
      status: 'available',
      last_checked_at: result.last_checked_at || new Date().toISOString(),
    }
    llmTestMessages[provider.code] = { kind: 'success', text: result.detail || '模型服务连接正常' }
  } catch (reason: any) {
    llmStatusOverrides[provider.code] = { status: 'unavailable', last_checked_at: new Date().toISOString() }
    llmTestMessages[provider.code] = { kind: 'error', text: reason.message || '模型服务检测失败' }
  } finally {
    llmTestingCode.value = ''
    emit('refresh')
  }
}

/**
 * 打开登录设置中指定区域的独立编辑弹窗。
 * 参数：`section` 表示登录认证设置或登录锁定策略。
 * 返回：无显式返回值。
 * 副作用：切换登录编辑区域并打开对应弹窗。
 */
function openLoginEdit(section: LoginEditSection) {
  loginEditSection.value = section
  openEdit()
}

/**
 * 打开通知设置中指定渠道的独立编辑弹窗。
 * 参数：`channel` 表示发件箱邮箱或短信网关。
 * 返回：无显式返回值。
 * 副作用：切换通知编辑渠道并打开只包含该渠道字段的弹窗。
 */
function openNotificationEdit(channel: NotificationEditChannel) {
  notificationEditChannel.value = channel
  openEdit()
}

/**
 * 打开指定通知渠道的测试发送弹窗。
 * 参数：`channel` 表示邮件或短信渠道。
 * 返回：无显式返回值。
 * 副作用：清空上次发送结果并打开独立测试弹窗。
 */
function openNotificationTest(channel: NotificationTestChannel) {
  const allowed = channel === 'email' ? canTestEmail.value : canTestSms.value
  const ready = channel === 'email' ? emailTestReady.value : smsTestReady.value
  if (!allowed || !ready) return
  notificationTestChannel.value = channel
  notificationTestError.value = ''
  notificationTestResult.value = ''
  notificationTestOpen.value = true
}

/**
 * 使用数据库已保存的渠道配置发送测试通知。
 * 参数：无，接收地址取自当前测试表单。
 * 返回：无显式返回值。
 * 副作用：请求后端发送邮件或短信，并在弹窗内展示结果。
 */
async function sendNotificationTest() {
  if (notificationTesting.value) return
  notificationTesting.value = true
  notificationTestError.value = ''
  notificationTestResult.value = ''
  const emailChannel = notificationTestChannel.value === 'email'
  try {
    const result = await api(`/system-settings/notification/test/${notificationTestChannel.value}/`, {
      method: 'POST',
      body: JSON.stringify(emailChannel
        ? { recipient: notificationTestForm.recipient.trim() }
        : { phone: notificationTestForm.phone.trim() }),
    })
    notificationTestResult.value = result.detail || (emailChannel ? '测试邮件已发送。' : '测试短信已发送。')
  } catch (reason: any) {
    notificationTestError.value = reason.message || '测试发送失败，请检查渠道配置'
  } finally {
    notificationTesting.value = false
  }
}

/**
 * 将白名单输入行整理为后端可校验的地址数组。
 * 参数：无。
 * 返回：去除空白和重复项后的 IP/CIDR 数组。
 * 副作用：不修改持久化数据。
 */
function parsedWhitelistEntries() {
  return [...new Set(
    whitelistEntries.value.map((entry) => entry.address.trim()).filter(Boolean),
  )]
}

/**
 * 将黑名单输入行整理为后端可校验的地址数组。
 * 参数：无。
 * 返回：去除空白和重复项后的 IP/CIDR 数组。
 * 副作用：不修改持久化数据。
 */
function parsedBlacklistEntries() {
  return [...new Set(
    blacklistEntries.value.map((entry) => entry.address.trim()).filter(Boolean),
  )]
}

/**
 * 整理指定访问限制名单中每个地址对应的用途说明。
 * 参数：`entries` 为弹窗中的地址与说明编辑行。
 * 返回：去除空白地址、空说明后的地址说明映射。
 * 副作用：不修改表单或持久化数据。
 */
function parsedAccessDescriptions(entries: AccessEntry[]) {
  return Object.fromEntries(entries
    .map((entry) => [entry.address.trim(), entry.description.trim()] as const)
    .filter(([address, description]) => Boolean(address && description)))
}

/**
 * 组合访问限制地址及其说明，供设置详情区展示。
 * 参数：`address` 为 IP/CIDR，`descriptions` 为地址说明映射。
 * 返回：有说明时附带说明的用户友好文字。
 * 副作用：不修改配置或页面状态。
 */
function accessEntryLabel(address: string, descriptions: Record<string, string>) {
  const description = descriptions?.[address]
  return description ? `${address}（${description}）` : address
}

/**
 * 向指定访问限制名单追加一条空白地址输入行。
 * 参数：`type` 表示白名单或黑名单。
 * 返回：无显式返回值。
 * 副作用：修改弹窗内对应名单的临时编辑数组。
 */
function addAccessEntry(type: 'whitelist' | 'blacklist') {
  const entries = type === 'whitelist' ? whitelistEntries : blacklistEntries
  entries.value.push({ address: '', description: '' })
  if (type === 'whitelist') goWhitelistPage(whitelistTotalPages.value)
  else goBlacklistPage(blacklistTotalPages.value)
}

/**
 * 删除指定访问限制名单中的一条地址输入行。
 * 参数：`type` 表示白名单或黑名单，`index` 为需要删除的行下标。
 * 返回：无显式返回值。
 * 副作用：修改弹窗内对应名单的临时编辑数组。
 */
function removeAccessEntry(type: 'whitelist' | 'blacklist', index: number) {
  const entries = type === 'whitelist' ? whitelistEntries : blacklistEntries
  entries.value.splice(index, 1)
  if (type === 'whitelist') goWhitelistPage(whitelistPage.value)
  else goBlacklistPage(blacklistPage.value)
}

/**
 * 读取用户选择的本地 Licence 文件到文本输入区。
 * 参数：`event` 为文件输入框变更事件。
 * 返回：异步读取完成后的 Promise。
 * 副作用：更新文件名、Licence 文本和校验错误，不上传其他本地文件。
 */
async function handleLicenseFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  error.value = ''
  const extension = file.name.includes('.') ? `.${file.name.split('.').pop()?.toLowerCase()}` : ''
  if (!['.lic', '.license', '.json', '.txt'].includes(extension)) {
    error.value = '仅支持 .lic、.license、.json 或 .txt 文件'
    input.value = ''
    return
  }
  if (file.size > 64 * 1024) {
    error.value = 'Licence 文件不能超过 64 KB'
    input.value = ''
    return
  }
  licenseContent.value = await file.text()
  licenseFileName.value = file.name
}

/**
 * 组装当前安全设置 Tab 对应的数据库配置请求体。
 * 参数：无。
 * 返回：包含设置键、中文说明和值的请求对象。
 * 副作用：不修改持久化数据。
 */
function currentPayload() {
  if (props.activeTab === 'whitelist') {
    return {
      key: settingKeys.whitelist,
      description: '登录来源 IP 白名单',
      value: {
        enabled: whitelistForm.enabled,
        entries: parsedWhitelistEntries(),
        descriptions: parsedAccessDescriptions(whitelistEntries.value),
      },
    }
  }
  if (props.activeTab === 'password') {
    return {
      key: settingKeys.password,
      description: '平台用户密码复杂度策略',
      value: {
        ...passwordForm,
        min_length: Number(passwordForm.min_length),
        max_age_days: Number(passwordForm.max_age_days),
      },
    }
  }
  if (props.activeTab === 'login') {
    return {
      key: settingKeys.login,
      description: '平台登录认证设置',
      value: {
        captcha_enabled: loginForm.captcha_enabled,
        slider_captcha_enabled: loginForm.slider_captcha_enabled,
        otp_enabled: loginForm.otp_enabled,
        sms_login_enabled: loginForm.sms_login_enabled,
        login_failure_limit: Number(loginForm.login_failure_limit),
        login_lock_minutes: Number(loginForm.login_lock_minutes),
        ip_failure_limit: Number(loginForm.ip_failure_limit),
        ip_lock_minutes: Number(loginForm.ip_lock_minutes),
        otp_failure_limit: Number(loginForm.otp_failure_limit),
        otp_lock_minutes: Number(loginForm.otp_lock_minutes),
        sms_failure_limit: Number(loginForm.sms_failure_limit),
        sms_lock_minutes: Number(loginForm.sms_lock_minutes),
      },
    }
  }
  if (props.activeTab === 'notification') {
    const editingEmail = notificationEditChannel.value === 'email'
    return {
      key: settingKeys.notification,
      description: '平台邮件与短信通知渠道配置',
      value: {
        email: {
          ...(editingEmail ? notificationForm.email : notificationValue.value.email),
          smtp_port: Number(
            editingEmail ? notificationForm.email.smtp_port : notificationValue.value.email.smtp_port,
          ),
        },
        sms: {
          ...(editingEmail ? notificationValue.value.sms : notificationForm.sms),
        },
      },
    }
  }
  if (props.activeTab === 'llm') {
    return {
      key: settingKeys.llm,
      description: '平台大语言模型厂商配置',
      value: {
        providers: llmValue.value.map((provider) => provider.code === editingLlmCode.value
          ? {
              ...provider,
              ...llmForm,
              priority: Number(llmForm.priority),
            }
          : provider),
      },
    }
  }
  if (props.activeTab === 'license') {
    return {
      key: settingKeys.license,
      description: '平台 Licence 授权配置',
      value: { license_secret: licenseContent.value.trim() },
    }
  }
  return {
    key: settingKeys.watermark,
    description: '平台工作台全局水印设置',
    value: {
      ...watermarkForm,
      font_size: Number(watermarkForm.font_size),
      font_weight: Number(watermarkForm.font_weight),
      opacity: Number(watermarkForm.opacity),
      rotate: Number(watermarkForm.rotate),
      horizontal_gap: Number(watermarkForm.horizontal_gap),
      vertical_gap: Number(watermarkForm.vertical_gap),
    },
  }
}

/**
 * 按设置是否已存在选择新增或更新接口。
 * 参数：`payload` 为设置请求体；`setting` 为对应的现有设置记录。
 * 返回：后端保存请求完成后的 Promise。
 * 副作用：写入一项平台设置并由后端记录系统日志。
 */
async function persistSetting(payload: Record<string, any>, setting?: SettingRow) {
  if (setting?.id) {
    await api(`/settings/${setting.id}/`, { method: 'PATCH', body: JSON.stringify(payload) })
  } else {
    await api('/settings/', { method: 'POST', body: JSON.stringify(payload) })
  }
}

/**
 * 保存当前安全设置并通知父页面重新读取数据库配置。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：请求后端写入平台设置并关闭编辑弹窗。
 */
async function saveSetting() {
  if (!canEdit.value) return
  saving.value = true
  error.value = ''
  try {
    if (props.activeTab === 'whitelist') {
      const whitelistSetting = props.items.find((item) => item.key === settingKeys.whitelist)
      const blacklistSetting = props.items.find((item) => item.key === 'security.login_blacklist')
      await persistSetting({
        key: settingKeys.whitelist,
        description: '登录来源 IP 白名单',
        value: {
          enabled: whitelistForm.enabled,
          entries: parsedWhitelistEntries(),
          descriptions: parsedAccessDescriptions(whitelistEntries.value),
        },
      }, whitelistSetting)
      await persistSetting({
        key: 'security.login_blacklist',
        description: '登录来源 IP 黑名单',
        value: {
          enabled: blacklistForm.enabled,
          entries: parsedBlacklistEntries(),
          descriptions: parsedAccessDescriptions(blacklistEntries.value),
        },
      }, blacklistSetting)
    } else {
      await persistSetting(currentPayload(), currentSetting.value)
    }
    if (props.activeTab === 'login' || props.activeTab === 'watermark') {
      await platform.loadPublic(true)
    }
    modalOpen.value = false
    emit('refresh')
  } catch (reason: any) {
    error.value = reason.message || '保存平台设置失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="platform-security-settings">
    <section v-if="activeTab === 'whitelist'" class="platform-settings-card platform-security-card">
      <div class="platform-settings-card-head">
        <span class="settings-icon"><ListFilter :size="18" /></span>
        <div><h3>登录访问限制</h3><p>黑名单优先于白名单执行，统一控制登录来源地址。</p></div>
        <button v-if="canEdit" class="secondary settings-edit-button" type="button" @click="openEdit"><Edit3 :size="16" />编辑</button>
      </div>
      <div class="access-restriction-group">
        <h4><ShieldCheck :size="17" />白名单限制</h4>
        <dl class="settings-list">
          <dt>状态</dt><dd><span :class="['badge', whitelistValue.enabled ? 'healthy' : 'offline']">{{ whitelistValue.enabled ? '已启用' : '已禁用' }}</span></dd>
          <dt>地址数量</dt><dd>{{ whitelistValue.entries.length }} 个</dd>
          <dt>允许地址</dt><dd>{{ whitelistValue.entries.length ? whitelistValue.entries.map((address) => accessEntryLabel(address, whitelistValue.descriptions)).join('、') : '未设置' }}</dd>
        </dl>
      </div>
      <div class="access-restriction-group">
        <h4><ShieldBan :size="17" />黑名单限制</h4>
        <dl class="settings-list">
          <dt>状态</dt><dd><span class="badge offline">{{ blacklistValue.enabled ? '已启用' : '已禁用' }}</span></dd>
          <dt>地址数量</dt><dd>{{ blacklistValue.entries.length }} 个</dd>
          <dt>拒绝地址</dt><dd>{{ blacklistValue.entries.length ? blacklistValue.entries.map((address) => accessEntryLabel(address, blacklistValue.descriptions)).join('、') : '未设置' }}</dd>
        </dl>
      </div>
    </section>

    <section v-else-if="activeTab === 'password'" class="platform-settings-card platform-security-card">
      <div class="platform-settings-card-head">
        <span class="settings-icon"><KeyRound :size="18" /></span>
        <div><h3>用户密码策略</h3><p>约束新增用户和修改密码时的密码复杂度。</p></div>
        <button v-if="canEdit" class="secondary settings-edit-button" type="button" @click="openEdit"><Edit3 :size="16" />编辑</button>
      </div>
      <dl class="settings-list">
        <dt>最小长度</dt><dd>{{ passwordValue.min_length }} 位</dd>
        <dt>大写字母</dt><dd>{{ ruleLabel(passwordValue.require_uppercase) }}</dd>
        <dt>小写字母</dt><dd>{{ ruleLabel(passwordValue.require_lowercase) }}</dd>
        <dt>数字</dt><dd>{{ ruleLabel(passwordValue.require_number) }}</dd>
        <dt>特殊字符</dt><dd>{{ ruleLabel(passwordValue.require_special) }}</dd>
        <dt>排除用户名</dt><dd>{{ passwordValue.exclude_username ? '不允许包含' : '不作要求' }}</dd>
        <dt>修改周期</dt><dd>{{ Number(passwordValue.max_age_days) > 0 ? `${passwordValue.max_age_days} 天（admin 除外）` : '不启用' }}</dd>
      </dl>
    </section>

    <template v-else-if="activeTab === 'login'">
      <section class="platform-settings-card platform-security-card">
        <div class="platform-settings-card-head">
          <span class="settings-icon"><LogIn :size="18" /></span>
          <div><h3>登录认证设置</h3><p>管理登录环节使用的身份校验方式。</p></div>
          <button v-if="canEdit" class="secondary settings-edit-button" type="button" @click="openLoginEdit('authentication')"><Edit3 :size="16" />编辑</button>
        </div>
        <div class="login-setting-list">
          <article><ShieldCheck :size="18" /><span><strong>登录验证码</strong><small>字符验证码</small></span><b :class="['badge', loginValue.captcha_enabled ? 'healthy' : 'offline']">{{ loginValue.captcha_enabled ? '已启用' : '已禁用' }}</b></article>
          <article><ShieldCheck :size="18" /><span><strong>图形拖拽验证</strong><small>拼图滑块验证</small></span><b :class="['badge', loginValue.slider_captcha_enabled ? 'healthy' : 'offline']">{{ loginValue.slider_captcha_enabled ? '已启用' : '已禁用' }}</b></article>
          <article><ShieldCheck :size="18" /><span><strong>OTP 认证</strong><small>平台默认策略，用户独立策略优先</small></span><b :class="['badge', loginValue.otp_enabled ? 'healthy' : 'offline']">{{ loginValue.otp_enabled ? '已启用' : '已禁用' }}</b></article>
          <article><MessageSquareText :size="18" /><span><strong>短信登录</strong><small>短信验证码通过后继续验证 OTP</small></span><b :class="['badge', loginValue.sms_login_enabled ? 'healthy' : 'offline']">{{ loginValue.sms_login_enabled ? '已启用' : '已禁用' }}</b></article>
        </div>
      </section>

      <section class="platform-settings-card platform-security-card login-lock-card">
        <div class="platform-settings-card-head">
          <span class="settings-icon warning"><ShieldBan :size="18" /></span>
          <div><h3>登录锁定策略</h3><p>限制连续输入错误，降低密码和动态口令被暴力尝试的风险。</p></div>
          <button v-if="canEdit" class="secondary settings-edit-button" type="button" @click="openLoginEdit('lock')"><Edit3 :size="16" />编辑</button>
        </div>
        <div class="login-lock-grid">
          <article>
            <span><strong>IP 防暴力保护</strong><small>同一来源 IP 跨账号累计登录失败次数</small></span>
            <b>{{ loginValue.ip_failure_limit }} 次</b>
            <em>锁定 {{ loginValue.ip_lock_minutes }} 分钟</em>
          </article>
          <article>
            <span><strong>密码错误锁定</strong><small>连续失败达到阈值后临时锁定账号</small></span>
            <b>{{ loginValue.login_failure_limit }} 次</b>
            <em>锁定 {{ loginValue.login_lock_minutes }} 分钟</em>
          </article>
          <article>
            <span><strong>OTP 错误锁定</strong><small>动态口令共用 OTP 失败计数</small></span>
            <b>{{ loginValue.otp_failure_limit }} 次</b>
            <em>锁定 {{ loginValue.otp_lock_minutes }} 分钟</em>
          </article>
          <article>
            <span><strong>短信验证码错误锁定</strong><small>连续输入错误达到阈值后锁定短信验证</small></span>
            <b>{{ loginValue.sms_failure_limit }} 次</b>
            <em>锁定 {{ loginValue.sms_lock_minutes }} 分钟</em>
          </article>
        </div>
      </section>
    </template>

    <div v-else-if="activeTab === 'llm'" class="llm-provider-grid">
      <section v-for="provider in llmValue" :key="provider.code" class="platform-settings-card platform-security-card llm-provider-card">
        <div class="platform-settings-card-head">
          <span class="settings-icon"><Bot :size="18" /></span>
          <div><h3>{{ provider.name }}</h3><p>{{ provider.code }}</p></div>
          <button v-if="canEdit" class="secondary settings-edit-button" type="button" @click="openLlmEdit(provider.code)"><Edit3 :size="16" />编辑</button>
        </div>
        <dl class="settings-list llm-settings-list">
          <dt>中文名称</dt><dd>{{ provider.name }}</dd>
          <dt>厂商</dt><dd>{{ provider.code }}</dd>
          <dt>模型</dt><dd>{{ provider.model }}</dd>
          <dt>优先级</dt><dd>{{ provider.priority }}</dd>
          <dt>状态</dt>
          <dd class="llm-provider-status">
            <span :class="['badge', llmStatusClass(provider.status)]">{{ llmStatusLabel(provider.status) }}</span>
            <button
              v-if="canTestLlm"
              class="llm-test-button"
              type="button"
              :disabled="Boolean(llmTestingCode) || !provider.api_key || !provider.model"
              :title="provider.api_key ? '检测模型服务连通性' : '请先编辑并保存 API Key'"
              @click="testLlmProvider(provider)"
            >
              <LoaderCircle v-if="llmTestingCode === provider.code" class="spin" :size="15" />
              <RadioTower v-else :size="15" />
              {{ llmTestingCode === provider.code ? '检测中' : '检测' }}
            </button>
            <small v-if="provider.last_checked_at">{{ formatLlmCheckedAt(provider.last_checked_at) }}</small>
          </dd>
          <dt>说明</dt><dd>{{ provider.description || '未填写' }}</dd>
        </dl>
        <p v-if="llmTestMessages[provider.code]" :class="['llm-test-message', llmTestMessages[provider.code].kind]">
          {{ llmTestMessages[provider.code].text }}
        </p>
      </section>
    </div>

    <template v-else-if="activeTab === 'notification'">
      <section class="platform-settings-card platform-security-card">
        <div class="platform-settings-card-head">
          <span class="settings-icon"><Mail :size="18" /></span>
          <div><h3>发件箱邮箱</h3><p>配置平台统一使用的 SMTP 发件通道。</p></div>
          <div v-if="canTestEmail || canEdit" class="settings-card-actions notification-card-actions">
            <button
              v-if="canTestEmail"
              class="secondary settings-edit-button notification-test-button"
              type="button"
              :disabled="!emailTestReady"
              :title="emailTestReady ? '发送测试邮件' : '请先启用并保存完整的邮箱配置'"
              @click="openNotificationTest('email')"
            ><Send :size="16" />测试</button>
            <button v-if="canEdit" class="secondary settings-edit-button" type="button" @click="openNotificationEdit('email')"><Edit3 :size="16" />编辑</button>
          </div>
        </div>
        <dl class="settings-list">
          <dt>状态</dt><dd><span :class="['badge', notificationValue.email.enabled ? 'healthy' : 'offline']">{{ notificationValue.email.enabled ? '已启用' : '已禁用' }}</span></dd>
          <dt>发件箱邮箱</dt><dd>{{ notificationValue.email.sender_email || '未配置' }}</dd>
          <dt>SMTP 服务</dt><dd>{{ notificationValue.email.smtp_host ? `${notificationValue.email.smtp_host}:${notificationValue.email.smtp_port}` : '未配置' }}</dd>
          <dt>连接安全</dt><dd>{{ emailSecurityLabel(notificationValue.email.security) }}</dd>
          <dt>SMTP 用户名</dt><dd>{{ notificationValue.email.username || '未配置' }}</dd>
          <dt>SMTP 密码</dt><dd>{{ notificationValue.email.password ? '已安全配置' : '未配置' }}</dd>
          <dt>单邮箱每分钟</dt><dd>{{ notificationValue.email.recipient_limit_per_minute }} 封</dd>
          <dt>单邮箱每小时</dt><dd>{{ notificationValue.email.recipient_limit_per_hour }} 封</dd>
          <dt>单邮箱每天</dt><dd>{{ notificationValue.email.recipient_limit_per_day }} 封</dd>
        </dl>
      </section>

      <section class="platform-settings-card platform-security-card">
        <div class="platform-settings-card-head">
          <span class="settings-icon"><MessageSquareText :size="18" /></span>
          <div><h3>短信网关</h3></div>
          <div v-if="canTestSms || canEdit" class="settings-card-actions notification-card-actions">
            <button
              v-if="canTestSms"
              class="secondary settings-edit-button notification-test-button"
              type="button"
              :disabled="!smsTestReady"
              :title="smsTestReady ? '发送测试短信' : '请先启用并保存完整的短信配置'"
              @click="openNotificationTest('sms')"
            ><Send :size="16" />测试</button>
            <button v-if="canEdit" class="secondary settings-edit-button" type="button" @click="openNotificationEdit('sms')"><Edit3 :size="16" />编辑</button>
          </div>
        </div>
        <dl class="settings-list">
          <dt>状态</dt><dd><span :class="['badge', notificationValue.sms.enabled ? 'healthy' : 'offline']">{{ notificationValue.sms.enabled ? '已启用' : '已禁用' }}</span></dd>
          <dt>短信服务商</dt><dd>{{ smsProviderLabel(notificationValue.sms.provider) }}</dd>
          <template v-for="field in smsOverviewFields" :key="field.key">
            <dt>{{ field.label }}</dt><dd>{{ field.value }}</dd>
          </template>
          <dt>模板 ID/编码</dt><dd>{{ notificationValue.sms.template_code || '未配置' }}</dd>
          <dt>单手机号每分钟</dt><dd>{{ notificationValue.sms.recipient_limit_per_minute }} 条</dd>
          <dt>单手机号每小时</dt><dd>{{ notificationValue.sms.recipient_limit_per_hour }} 条</dd>
          <dt>单手机号每天</dt><dd>{{ notificationValue.sms.recipient_limit_per_day }} 条</dd>
        </dl>
      </section>
    </template>

    <section v-else-if="activeTab === 'license'" class="platform-settings-card platform-security-card">
      <div class="platform-settings-card-head">
        <span class="settings-icon"><FileKey2 :size="18" /></span>
        <div><h3>Licence 授权</h3></div>
        <button v-if="canEdit" class="secondary settings-edit-button" type="button" @click="openEdit"><Edit3 :size="16" />{{ licenseValue.configured ? '更新' : '录入' }}</button>
      </div>
      <dl class="settings-list">
        <dt>授权状态</dt><dd><span :class="['badge', licenseStatusClass]">{{ licenseValue.status_label }}</span></dd>
        <dt>实例 ID</dt><dd>{{ licenseValue.instance_id || '暂不可用' }}</dd>
        <dt>Licence 编号</dt><dd>{{ licenseValue.license_id || '未配置' }}</dd>
        <dt>授权客户</dt><dd>{{ licenseValue.customer || '未配置' }}</dd>
        <dt>生效时间</dt><dd>{{ formatDateTime(licenseValue.effective_time) }}</dd>
        <dt>到期时间</dt><dd>{{ formatDateTime(licenseValue.expire_time) }}</dd>
        <dt>剩余天数</dt><dd>{{ licenseValue.status === 'valid' ? `${licenseValue.days_remaining} 天` : '-' }}</dd>
        <dt>授权用户数</dt><dd>{{ licenseValue.configured ? `${licenseValue.max_users} 人` : '未配置' }}</dd>
        <dt>并发数</dt><dd>{{ licenseValue.configured ? `${licenseValue.max_concurrency}` : '未配置' }}</dd>
        <dt>授权类型</dt><dd>{{ licenseValue.license_type || '未配置' }}</dd>
        <template v-if="licenseValue.status === 'unavailable'">
          <dt>不可用原因</dt><dd>{{ licenseValue.unavailable_reason || '授权校验未通过' }}</dd>
        </template>
      </dl>
    </section>

    <section v-else class="platform-settings-card platform-security-card watermark-settings-card">
      <div class="platform-settings-card-head">
        <span class="settings-icon"><Stamp :size="18" /></span>
        <div><h3>全局安全水印</h3><p>在工作台叠加身份水印，强化截图溯源与数据防泄漏能力。</p></div>
        <button v-if="canEdit" class="secondary settings-edit-button" type="button" @click="openEdit"><Edit3 :size="16" />编辑</button>
      </div>
      <div class="watermark-overview">
        <dl class="settings-list">
          <dt>运行状态</dt><dd><span :class="['badge', watermarkValue.enabled ? 'healthy' : 'offline']">{{ watermarkValue.enabled ? '已启用' : '已禁用' }}</span></dd>
          <dt>水印内容</dt><dd>{{ watermarkContentLabel(watermarkValue.content_type) }}</dd>
          <dt>展示布局</dt><dd>{{ watermarkLayoutLabel(watermarkValue.layout) }}</dd>
          <dt>时间标识</dt><dd>{{ watermarkValue.show_time ? '显示到分钟' : '不显示' }}</dd>
          <dt>视觉样式</dt><dd>{{ watermarkValue.font_size }}px · {{ Math.round(watermarkValue.opacity * 100) }}% 透明度 · {{ watermarkValue.rotate }}°</dd>
        </dl>
        <section class="watermark-preview-panel" aria-label="水印效果预览">
          <header><strong>效果预览</strong><span>WORKSPACE PREVIEW</span></header>
          <div class="watermark-preview-stage">
            <SystemWatermark
              :config="watermarkValue"
              :username="auth.displayName"
              :platform-name="platformDisplayName"
              :client-ip="platform.client_ip"
              preview
            />
            <span v-if="!watermarkValue.enabled" class="watermark-preview-disabled">水印当前未启用</span>
            <div class="watermark-preview-window"><i></i><i></i><i></i><span></span></div>
          </div>
        </section>
      </div>
    </section>
  </div>

  <ModalDialog
    :open="modalOpen"
    :title="modalTitle"
    dialog-class="platform-settings-dialog"
    description="修改后对平台统一生效。"
    @close="modalOpen = false"
  >
    <form class="form-grid platform-security-form" @submit.prevent="saveSetting">
      <template v-if="activeTab === 'whitelist'">
        <label class="check"><span>启用登录白名单</span><input v-model="whitelistForm.enabled" type="checkbox" /></label>
        <section class="full-width access-editor-group">
          <header><span>允许的 IP 或 CIDR</span><button class="secondary" type="button" @click="addAccessEntry('whitelist')"><Plus :size="15" />新增</button></header>
          <div v-for="row in paginatedWhitelistRows" :key="`whitelist-${row.index}`" class="access-entry-row">
            <input v-model.trim="row.entry.address" :aria-label="`白名单地址 ${row.index + 1}`" placeholder="IP 或 CIDR" />
            <input v-model.trim="row.entry.description" :aria-label="`白名单说明 ${row.index + 1}`" maxlength="200" placeholder="说明，例如：办公网出口" />
            <button class="danger" type="button" @click="removeAccessEntry('whitelist', row.index)"><Trash2 :size="15" />删除</button>
          </div>
          <p v-if="!whitelistEntries.length" class="access-entry-empty">暂未添加允许地址</p>
          <PaginationBar
            v-model:jump-page="whitelistJumpPage"
            :page-size="accessPageSize"
            :current-page="whitelistPage"
            :total-pages="whitelistTotalPages"
            :page-start="whitelistPageStart"
            :page-end="whitelistPageEnd"
            :total="whitelistEntries.length"
            @go="goWhitelistPage"
            @move="moveWhitelistPage"
            @jump="applyWhitelistJump"
          />
        </section>
        <label class="check"><span>启用登录黑名单</span><input v-model="blacklistForm.enabled" type="checkbox" /></label>
        <section class="full-width access-editor-group">
          <header><span>拒绝的 IP 或 CIDR</span><button class="secondary" type="button" @click="addAccessEntry('blacklist')"><Plus :size="15" />新增</button></header>
          <div v-for="row in paginatedBlacklistRows" :key="`blacklist-${row.index}`" class="access-entry-row">
            <input v-model.trim="row.entry.address" :aria-label="`黑名单地址 ${row.index + 1}`" placeholder="IP 或 CIDR" />
            <input v-model.trim="row.entry.description" :aria-label="`黑名单说明 ${row.index + 1}`" maxlength="200" placeholder="说明，例如：异常来源地址" />
            <button class="danger" type="button" @click="removeAccessEntry('blacklist', row.index)"><Trash2 :size="15" />删除</button>
          </div>
          <p v-if="!blacklistEntries.length" class="access-entry-empty">暂未添加拒绝地址</p>
          <PaginationBar
            v-model:jump-page="blacklistJumpPage"
            :page-size="accessPageSize"
            :current-page="blacklistPage"
            :total-pages="blacklistTotalPages"
            :page-start="blacklistPageStart"
            :page-end="blacklistPageEnd"
            :total="blacklistEntries.length"
            @go="goBlacklistPage"
            @move="moveBlacklistPage"
            @jump="applyBlacklistJump"
          />
        </section>
      </template>
      <template v-else-if="activeTab === 'password'">
        <label>密码最小长度<input v-model.number="passwordForm.min_length" type="number" min="6" max="64" required /></label>
        <label>密码修改周期（天）<input v-model.number="passwordForm.max_age_days" type="number" min="0" max="3650" required /></label>
        <p class="full-width field-hint">修改周期按天计算，0 表示不启用；只对普通用户生效，系统超级管理员 admin 始终豁免，不会因长期未修改密码被禁用。</p>
        <label class="check password-policy-check"><span>必须包含大写字母</span><input v-model="passwordForm.require_uppercase" type="checkbox" /></label>
        <label class="check password-policy-check"><span>必须包含小写字母</span><input v-model="passwordForm.require_lowercase" type="checkbox" /></label>
        <label class="check password-policy-check"><span>必须包含数字</span><input v-model="passwordForm.require_number" type="checkbox" /></label>
        <label class="check password-policy-check"><span>必须包含特殊字符</span><input v-model="passwordForm.require_special" type="checkbox" /></label>
        <label class="check password-policy-check"><span>密码不能包含用户名</span><input v-model="passwordForm.exclude_username" type="checkbox" /></label>
      </template>
      <template v-else-if="activeTab === 'login'">
        <template v-if="loginEditSection === 'authentication'">
          <label class="check"><span>启用登录验证码</span><input v-model="loginForm.captcha_enabled" type="checkbox" /></label>
          <label class="check"><span>启用图形拖拽验证</span><input v-model="loginForm.slider_captcha_enabled" type="checkbox" /></label>
          <label class="check"><span>平台默认启用 OTP</span><input v-model="loginForm.otp_enabled" type="checkbox" /></label>
          <label class="check"><span>启用短信登录</span><input v-model="loginForm.sms_login_enabled" type="checkbox" /></label>
          <p class="full-width field-hint">短信登录要求字符验证码、图形拖拽、平台 OTP 和短信网关同时启用；仅已绑定 OTP 的唯一手机号可使用。</p>
        </template>
        <template v-else>
          <div class="full-width login-lock-form-title">
            <strong>登录锁定策略</strong>
            <span>密码、OTP 与短信验证码支持 3–20 次，IP 支持 5–200 次；锁定时间支持 1–1440 分钟。</span>
          </div>
          <label>IP 失败次数
            <input v-model.number="loginForm.ip_failure_limit" type="number" min="5" max="200" required />
          </label>
          <label>IP 锁定时间（分钟）
            <input v-model.number="loginForm.ip_lock_minutes" type="number" min="1" max="1440" required />
          </label>
          <label>密码失败次数
            <input v-model.number="loginForm.login_failure_limit" type="number" min="3" max="20" required />
          </label>
          <label>密码锁定时间（分钟）
            <input v-model.number="loginForm.login_lock_minutes" type="number" min="1" max="1440" required />
          </label>
          <label>OTP 失败次数
            <input v-model.number="loginForm.otp_failure_limit" type="number" min="3" max="20" required />
          </label>
          <label>OTP 锁定时间（分钟）
            <input v-model.number="loginForm.otp_lock_minutes" type="number" min="1" max="1440" required />
          </label>
          <label>短信验证码失败次数
            <input v-model.number="loginForm.sms_failure_limit" type="number" min="3" max="20" required />
          </label>
          <label>短信验证码锁定时间（分钟）
            <input v-model.number="loginForm.sms_lock_minutes" type="number" min="1" max="1440" required />
          </label>
        </template>
      </template>
      <template v-else-if="activeTab === 'llm'">
        <section class="full-width llm-form-identity">
          <span class="settings-icon"><Bot :size="18" /></span>
          <div><strong>{{ llmForm.name }}</strong><small>{{ llmForm.code }}</small></div>
          <label class="check"><span>{{ llmForm.enabled ? '已启用' : '已停用' }}</span><input v-model="llmForm.enabled" type="checkbox" /></label>
        </section>
        <label>API Key
          <PasswordInput v-model="llmForm.api_key" :required="llmForm.enabled" :max-length="1024" autocomplete="new-password" placeholder="请输入厂商 API Key" />
        </label>
        <label>接口地址
          <input v-model.trim="llmForm.base_url" type="url" maxlength="500" required placeholder="https://api.example.com/v1" />
        </label>
        <label>模型
          <input v-model.trim="llmForm.model" maxlength="120" required placeholder="请输入模型名称" />
        </label>
        <label>优先级
          <input v-model.number="llmForm.priority" type="number" min="1" max="100" required />
        </label>
        <p class="full-width field-hint">优先级范围 1–100，数字越小越优先。</p>
        <label class="full-width">说明
          <textarea v-model.trim="llmForm.description" rows="3" maxlength="500" placeholder="请输入厂商用途说明" />
        </label>
      </template>
      <template v-else-if="activeTab === 'notification'">
        <template v-if="notificationEditChannel === 'email'">
        <div class="full-width notification-form-heading">
          <Mail :size="17" />
          <span><strong>发件箱邮箱</strong><small>SMTP 发件配置</small></span>
          <label class="check"><span>启用</span><input v-model="notificationForm.email.enabled" type="checkbox" /></label>
        </div>
        <label>SMTP 主机
          <input v-model.trim="notificationForm.email.smtp_host" :required="notificationForm.email.enabled" maxlength="255" placeholder="smtp.example.com" />
        </label>
        <label>SMTP 端口
          <input v-model.number="notificationForm.email.smtp_port" type="number" min="1" max="65535" required />
        </label>
        <label>连接安全
          <CustomSelect v-model="notificationForm.email.security">
            <option value="ssl">SSL/TLS</option>
            <option value="starttls">STARTTLS</option>
            <option value="none">不加密</option>
          </CustomSelect>
        </label>
        <label>发件箱邮箱
          <input v-model.trim="notificationForm.email.sender_email" type="email" :required="notificationForm.email.enabled" maxlength="254" placeholder="notice@example.com" />
        </label>
        <label>SMTP 用户名
          <input v-model.trim="notificationForm.email.username" :required="notificationForm.email.enabled" maxlength="255" autocomplete="off" placeholder="通常与发件箱邮箱一致" />
        </label>
        <label>SMTP 密码
          <PasswordInput v-model="notificationForm.email.password" :required="notificationForm.email.enabled" :max-length="512" autocomplete="new-password" placeholder="邮箱授权码或 SMTP 密码" />
        </label>
        <div class="full-width notification-rate-heading">
          <strong>单一收件邮箱频率策略</strong>
          <span>保存发送额度，后续通知逻辑按收件邮箱分别统计。</span>
        </div>
        <label>1 分钟发送上限（封）
          <input v-model.number="notificationForm.email.recipient_limit_per_minute" type="number" min="1" max="100000" required />
        </label>
        <label>1 小时发送上限（封）
          <input v-model.number="notificationForm.email.recipient_limit_per_hour" type="number" min="1" max="100000" required />
        </label>
        <label>1 天发送上限（封）
          <input v-model.number="notificationForm.email.recipient_limit_per_day" type="number" min="1" max="100000" required />
        </label>
        </template>
        <template v-else>
        <div class="full-width notification-form-heading notification-form-heading-sms">
          <MessageSquareText :size="17" />
          <span><strong>短信网关</strong></span>
          <label class="check"><span>启用</span><input v-model="notificationForm.sms.enabled" type="checkbox" /></label>
        </div>
        <label>短信服务商
          <CustomSelect
            v-model="notificationForm.sms.provider"
            class="sms-provider-select"
            searchable
            search-placeholder="搜索短信服务商"
            aria-label="短信服务商"
          >
            <option v-for="provider in smsProviders" :key="provider.code" :value="provider.code">{{ provider.name }}</option>
          </CustomSelect>
        </label>
        <label v-if="['aliyun', 'baidu', 'qiniu'].includes(notificationForm.sms.provider)">AccessKey ID
          <input v-model.trim="notificationForm.sms.access_key_id" :required="notificationForm.sms.enabled" maxlength="128" autocomplete="off" placeholder="请输入 AccessKey ID" />
        </label>
        <label v-if="['aliyun', 'baidu', 'qiniu'].includes(notificationForm.sms.provider)">AccessKey Secret
          <PasswordInput v-model="notificationForm.sms.access_key_secret" :required="notificationForm.sms.enabled" :max-length="256" autocomplete="new-password" placeholder="请输入 AccessKey Secret" />
        </label>
        <label v-if="notificationForm.sms.provider === 'tencent'">SecretId
          <PasswordInput v-model="notificationForm.sms.secret_id" :required="notificationForm.sms.enabled" :max-length="128" autocomplete="new-password" placeholder="请输入 SecretId" />
        </label>
        <label v-if="notificationForm.sms.provider === 'tencent'">SecretKey
          <PasswordInput v-model="notificationForm.sms.secret_key" :required="notificationForm.sms.enabled" :max-length="256" autocomplete="new-password" placeholder="请输入 SecretKey" />
        </label>
        <label v-if="notificationForm.sms.provider === 'tencent'">SmsSdkAppId
          <input v-model.trim="notificationForm.sms.sdk_app_id" :required="notificationForm.sms.enabled" maxlength="64" autocomplete="off" placeholder="请输入短信应用 ID" />
        </label>
        <label v-if="['aliyun', 'tencent'].includes(notificationForm.sms.provider)">短信签名
          <input v-model.trim="notificationForm.sms.sign_name" :required="notificationForm.sms.enabled" maxlength="100" placeholder="已审核通过的短信签名" />
        </label>
        <label v-if="notificationForm.sms.provider === 'baidu'">签名 ID
          <input v-model.trim="notificationForm.sms.signature_id" :required="notificationForm.sms.enabled" maxlength="100" placeholder="请输入审核通过的签名 ID" />
        </label>
        <label v-if="notificationForm.sms.provider === 'upyun'">Authorization Token
          <PasswordInput v-model="notificationForm.sms.authorization_token" :required="notificationForm.sms.enabled" :max-length="512" autocomplete="new-password" placeholder="请输入 Authorization Token" />
        </label>
        <label v-if="notificationForm.sms.provider === 'yunpian'">API Key
          <PasswordInput v-model="notificationForm.sms.api_key" :required="notificationForm.sms.enabled" :max-length="256" autocomplete="new-password" placeholder="请输入 API Key" />
        </label>
        <label v-if="notificationForm.sms.provider === 'netease'">AppKey
          <input v-model.trim="notificationForm.sms.app_key" :required="notificationForm.sms.enabled" maxlength="128" autocomplete="off" placeholder="请输入 AppKey" />
        </label>
        <label v-if="notificationForm.sms.provider === 'netease'">AppSecret
          <PasswordInput v-model="notificationForm.sms.app_secret" :required="notificationForm.sms.enabled" :max-length="256" autocomplete="new-password" placeholder="请输入 AppSecret" />
        </label>
        <label>模板 ID/编码
          <input v-model.trim="notificationForm.sms.template_code" :required="notificationForm.sms.enabled" maxlength="100" placeholder="请输入服务商控制台中的模板 ID 或编码" />
        </label>
        <p class="full-width field-hint">平台仅传递 code 变量，短信正文由服务商控制台中的审核模板管理。</p>
        <div class="full-width notification-rate-heading">
          <strong>单一手机号频率策略</strong>
          <span>保存发送额度，后续短信逻辑按接收手机号分别统计。</span>
        </div>
        <label>1 分钟发送上限（条）
          <input v-model.number="notificationForm.sms.recipient_limit_per_minute" type="number" min="1" max="100000" required />
        </label>
        <label>1 小时发送上限（条）
          <input v-model.number="notificationForm.sms.recipient_limit_per_hour" type="number" min="1" max="100000" required />
        </label>
        <label>1 天发送上限（条）
          <input v-model.number="notificationForm.sms.recipient_limit_per_day" type="number" min="1" max="100000" required />
        </label>
        </template>
      </template>
      <template v-else-if="activeTab === 'license'">
        <label class="full-width license-file-field">Licence 文件
          <span class="license-file-control">
            <input class="visually-hidden" type="file" accept=".lic,.license,.json,.txt,application/json,text/plain" @change="handleLicenseFile" />
            <span class="secondary license-upload-button"><Upload :size="16" />选择文件</span>
            <span>{{ licenseFileName || '未选择文件，可直接在下方输入' }}</span>
          </span>
        </label>
        <label class="full-width">请输入licence
          <textarea v-model="licenseContent" rows="10" required spellcheck="false" placeholder="请输入licence" />
        </label>
      </template>
      <template v-else>
        <div class="full-width watermark-form-heading">
          <span><Stamp :size="18" /></span>
          <div><strong>全局安全水印</strong><small>开启后覆盖登录后的整个工作台，不影响页面点击与操作。</small></div>
          <label class="check"><span>{{ watermarkForm.enabled ? '已启用' : '已禁用' }}</span><input v-model="watermarkForm.enabled" type="checkbox" /></label>
        </div>

        <section class="full-width watermark-preview-panel watermark-form-preview" aria-label="正在编辑的水印效果预览">
          <header><strong>实时预览</strong><span>所见即所得</span></header>
          <div class="watermark-preview-stage">
            <SystemWatermark
              :config="watermarkForm"
              :username="auth.displayName"
              :platform-name="platformDisplayName"
              :client-ip="platform.client_ip"
              preview
            />
            <span v-if="!watermarkForm.enabled" class="watermark-preview-disabled">启用水印后可预览效果</span>
            <div class="watermark-preview-window"><i></i><i></i><i></i><span></span></div>
          </div>
        </section>

        <label>水印内容类型
          <CustomSelect v-model="watermarkForm.content_type">
            <option value="username">登录用户</option>
            <option value="username_ip">登录用户 + 访问 IP</option>
            <option value="platform">平台名称</option>
            <option value="custom">自定义文字</option>
          </CustomSelect>
        </label>
        <label>展示布局
          <CustomSelect v-model="watermarkForm.layout">
            <option value="tiled">全屏平铺</option>
            <option value="center">页面居中</option>
          </CustomSelect>
        </label>
        <label v-if="watermarkForm.content_type === 'custom'" class="full-width">自定义水印文字
          <input v-model.trim="watermarkForm.custom_text" maxlength="40" required placeholder="例如：内部资料 · 严禁外传" />
        </label>
        <label class="check watermark-policy-check"><span>附加当前时间</span><input v-model="watermarkForm.show_time" type="checkbox" /></label>
        <label>字体粗细
          <CustomSelect v-model.number="watermarkForm.font_weight">
            <option :value="400">常规</option>
            <option :value="500">中等</option>
            <option :value="600">半粗体</option>
          </CustomSelect>
        </label>
        <label class="watermark-color-field">水印颜色
          <span><input v-model="watermarkForm.color" type="color" /><b>{{ watermarkForm.color.toUpperCase() }}</b></span>
        </label>
        <label class="watermark-range-field">字体大小 <b>{{ watermarkForm.font_size }} px</b>
          <input v-model.number="watermarkForm.font_size" type="range" min="11" max="28" step="1" />
        </label>
        <label class="watermark-range-field">透明度 <b>{{ Math.round(watermarkForm.opacity * 100) }}%</b>
          <input v-model.number="watermarkForm.opacity" type="range" min="0.05" max="0.35" step="0.01" />
        </label>
        <label class="watermark-range-field">旋转角度 <b>{{ watermarkForm.rotate }}°</b>
          <input v-model.number="watermarkForm.rotate" type="range" min="-60" max="60" step="1" />
        </label>
        <template v-if="watermarkForm.layout === 'tiled'">
          <label class="watermark-range-field">水平间距 <b>{{ watermarkForm.horizontal_gap }} px</b>
            <input v-model.number="watermarkForm.horizontal_gap" type="range" min="140" max="480" step="10" />
          </label>
          <label class="watermark-range-field">垂直间距 <b>{{ watermarkForm.vertical_gap }} px</b>
            <input v-model.number="watermarkForm.vertical_gap" type="range" min="90" max="320" step="10" />
          </label>
        </template>
      </template>
      <p v-if="error" class="form-error">{{ error }}</p>
      <footer>
        <button class="secondary" type="button" @click="modalOpen = false">取消</button>
        <button class="primary" :disabled="saving">{{ saving ? '处理中' : '保存' }}</button>
      </footer>
    </form>
  </ModalDialog>

  <ModalDialog
    :open="notificationTestOpen"
    :title="notificationTestTitle"
    :description="notificationTestDescription"
    width="560px"
    dialog-class="notification-test-dialog platform-settings-dialog"
    @close="notificationTestOpen = false"
  >
    <form class="notification-test-form" @submit.prevent="sendNotificationTest">
      <template v-if="notificationTestChannel === 'email'">
        <label>收件邮箱
          <input
            v-model.trim="notificationTestForm.recipient"
            type="email"
            maxlength="254"
            autocomplete="email"
            required
            placeholder="receiver@example.com"
          />
        </label>
        <section class="notification-mail-preview" aria-label="测试邮件预览">
          <header><span>邮件预览</span><small>HTML 格式</small></header>
          <div>
            <span class="notification-preview-eyebrow">通知渠道测试</span>
            <h3>SMTP 配置验证</h3>
            <p>这是平台名称「{{ platformDisplayName }}」的测试邮件，用于验证 SMTP 通知渠道是否可以正常发送。</p>
            <dl>
              <dt>邮件主题</dt><dd>【{{ platformDisplayName }}】通知渠道测试</dd>
              <dt>发件邮箱</dt><dd>{{ notificationValue.email.sender_email }}</dd>
            </dl>
          </div>
        </section>
      </template>
      <template v-else>
        <label>接收手机号
          <input
            v-model.trim="notificationTestForm.phone"
            type="tel"
            maxlength="20"
            autocomplete="tel"
            required
            placeholder="13800138000"
          />
        </label>
        <section class="notification-sms-summary" aria-label="短信发送配置">
          <div class="notification-summary-icon"><MessageSquareText :size="19" /></div>
          <dl>
            <dt>服务商</dt><dd>{{ smsProviderLabel(notificationValue.sms.provider) }}</dd>
            <dt>模板 ID/编码</dt><dd>{{ notificationValue.sms.template_code }}</dd>
            <dt>模板变量</dt><dd>code = 123456</dd>
          </dl>
          <p>测试发送只提交 code，短信正文以服务商审核模板为准。</p>
        </section>
      </template>
      <p v-if="notificationTestResult" class="notification-test-result"><CheckCircle2 :size="17" />{{ notificationTestResult }}</p>
      <p v-if="notificationTestError" class="form-error notification-test-error">{{ notificationTestError }}</p>
      <footer>
        <button class="secondary" type="button" @click="notificationTestOpen = false">取消</button>
        <button class="primary" :disabled="notificationTesting">
          <Send :size="16" />{{ notificationTesting ? '正在发送' : '发送测试' }}
        </button>
      </footer>
    </form>
  </ModalDialog>
</template>
