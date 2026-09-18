<script setup lang="ts">
import { Cloud, Container, DatabaseBackup, Edit3, Eye, EyeOff, GitBranch, Plus, RefreshCw, ServerCog, ShieldCheck, SlidersHorizontal, Terminal, Upload } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'

import { api, apiForm } from '../../api'
import ConfirmDialog from '../../components/ConfirmDialog.vue'
import CustomSelect from '../../components/CustomSelect.vue'
import ModalDialog from '../../components/ModalDialog.vue'
import { actionPermissionForPath } from '../../permissions'
import { useAuthStore } from '../../stores/auth'
import { usePlatformStore } from '../../stores/platform'
import { localAssetUrl, requireLocalAssetUrl } from '../../utils/localAssets'
import PlatformSecuritySettings from './PlatformSecuritySettings.vue'

type SettingRow = {
  id?: number
  key: 'platform' | 'security' | string
  value?: Record<string, any>
  description?: string
}

type SettingKey = 'platform' | 'platform.filing' | 'security' | 'storage.oss' | 'recording.guacamole' | 'database.backup_tools' | 'ci.git_tools' | 'ci.maven_tools' | 'ci.npm_tools' | 'ci.java_tools' | 'ci.docker_tools' | 'ci.helm_tools' | string
type SettingsTab = 'whitelist' | 'basic' | 'password' | 'login' | 'llm' | 'notification' | 'watermark' | 'license'

const DEFAULT_DOCKER_COMMAND_PATH = 'C:\\Program Files\\Docker\\Docker\\resources\\docker.exe'
const COMMAND_SETTING_ORDER = ['database.backup_tools', 'ci.git_tools', 'ci.maven_tools', 'ci.npm_tools', 'ci.java_tools', 'ci.docker_tools', 'ci.helm_tools']
const BUILTIN_COMMAND_KEYS = new Set(['database.backup_tools', 'ci.git_tools', 'ci.maven_tools', 'ci.npm_tools', 'ci.java_tools', 'ci.docker_tools', 'ci.helm_tools'])

const props = defineProps<{ items: SettingRow[]; loading?: boolean }>()
const emit = defineEmits<{ refresh: [] }>()
const auth = useAuthStore()
const platform = usePlatformStore()
const activeTab = ref<SettingsTab>('basic')
const settingsTabs: Array<{ code: SettingsTab; name: string }> = [
  { code: 'whitelist', name: '访问限制' },
  { code: 'basic', name: '基础配置' },
  { code: 'password', name: '密码策略' },
  { code: 'login', name: '登录设置' },
  { code: 'llm', name: 'LLM配置' },
  { code: 'notification', name: '通知设置' },
  { code: 'watermark', name: '水印设置' },
  { code: 'license', name: 'Licence管理' },
]

const CREATE_COMMAND_KEY = 'ci.custom_tools'
const CONFIG_TYPE_NAMES: Record<string, string> = {
  'platform': '平台基础设置',
  'platform.filing': '备案设置',
  'security': '平台安全设置',
  'storage.oss': 'OSS 配置',
  'recording.guacamole': '录像网关 Guacamole',
}

const canCreate = computed(() => auth.can(actionPermissionForPath('/settings', 'create')))
const canUpdate = computed(() => auth.can(actionPermissionForPath('/settings', 'update')))
const canDelete = computed(() => auth.can(actionPermissionForPath('/settings', 'delete')))
const canReveal = computed(() => auth.can(actionPermissionForPath('/settings', 'reveal')))

const modalOpen = ref(false)
const modalMode = ref<'create' | 'edit'>('edit')
const editingKey = ref<SettingKey>('platform')
const saving = ref(false)
const error = ref('')
const revealing = ref(false)
const deleting = ref(false)
const deleteTarget = ref<SettingRow | null>(null)
const deleteTitle = ref('')
const deleteHint = ref('')
const ossSecretVisible = ref(false)
const guacamoleSecretVisible = ref(false)
const guacamoleSftpPasswordVisible = ref(false)
const logoFileInput = ref<HTMLInputElement | null>(null)
const logoUploading = ref(false)

const platformForm = reactive({
  name: '',
  logo_url: '',
})
const filingForm = reactive({
  icp_record: '',
  icp_url: '',
  public_security_record: '',
  public_security_url: '',
})

const securityForm = reactive({
  session_timeout_minutes: 30,
})
const ossForm = reactive({
  enabled: true,
  access_key_id: '',
  access_key_secret: '',
  bucket: '',
  endpoint: '',
  base_dir: 'baoleiji',
  use_https: true,
})
const guacamoleForm = reactive({
  enabled: true,
  scheme: 'http',
  host: '47.120.40.124',
  port: 9080,
  base_path: '/guacamole',
  json_secret_key: '290788bc59d6bef6abf380717bb609e0',
  recording_path: '/recordings',
  recording_read_mode: 'sftp',
  recording_host_path: '/root/guacamole/recordings',
  recording_sftp_host: '47.120.40.124',
  recording_sftp_port: 22,
  recording_sftp_username: '',
  recording_sftp_password: '',
  upload_to_oss: true,
  delete_local_after_upload: false,
})
const backupToolsForm = reactive({
  name: 'mysqldump',
  path: '/usr/local/mysql/mysqldump',
})
const gitToolsForm = reactive({
  name: 'git',
  path: '/mingw64/bin/git',
})
const mavenToolsForm = reactive({
  name: 'mvn',
  path: 'mvn',
})
const npmToolsForm = reactive({
  name: 'npm',
  path: 'npm',
})
const dockerToolsForm = reactive({
  name: 'docker',
  path: DEFAULT_DOCKER_COMMAND_PATH,
})
const helmToolsForm = reactive({
  name: 'helm',
  path: 'helm',
})
const javaToolsForm = reactive({
  name: 'java',
  java_home: 'JAVA_HOME',
  path: 'java',
})
const commandForm = reactive({
  name: '',
  path: '',
  description: '',
})

const settings = computed(() => ({
  platform: props.items.find((item) => item.key === 'platform'),
  filing: props.items.find((item) => item.key === 'platform.filing'),
  security: props.items.find((item) => item.key === 'security'),
  oss: props.items.find((item) => item.key === 'storage.oss'),
  guacamole: props.items.find((item) => item.key === 'recording.guacamole'),
  backupTools: props.items.find((item) => item.key === 'database.backup_tools'),
  gitTools: props.items.find((item) => item.key === 'ci.git_tools'),
  mavenTools: props.items.find((item) => item.key === 'ci.maven_tools'),
  npmTools: props.items.find((item) => item.key === 'ci.npm_tools'),
  javaTools: props.items.find((item) => item.key === 'ci.java_tools'),
  dockerTools: props.items.find((item) => item.key === 'ci.docker_tools'),
  helmTools: props.items.find((item) => item.key === 'ci.helm_tools'),
}))

const platformValue = computed(() => ({
  name: 'Ongrid',
  logo_url: '/assets/brand/logo.svg',
  ...(settings.value.platform?.value || {}),
}))
const platformFormLogoUrl = computed(() => localAssetUrl(platformForm.logo_url))
const filingValue = computed(() => ({
  icp_record: '',
  icp_url: '',
  public_security_record: '',
  public_security_url: '',
  ...(settings.value.filing?.value || {}),
}))

const securityValue = computed(() => ({
  session_timeout: 1800,
  ...(settings.value.security?.value || {}),
}))
const ossValue = computed(() => ({
  enabled: true,
  access_key_id: '',
  access_key_secret: '',
  bucket: '',
  endpoint: '',
  base_dir: 'baoleiji',
  use_https: true,
  ...(settings.value.oss?.value || {}),
}))
const guacamoleValue = computed(() => ({
  enabled: true,
  scheme: 'http',
  host: '47.120.40.124',
  port: 9080,
  base_path: '/guacamole',
  json_secret_key: '',
  recording_path: '/recordings',
  recording_read_mode: 'sftp',
  recording_host_path: '/root/guacamole/recordings',
  recording_sftp_host: '47.120.40.124',
  recording_sftp_port: 22,
  recording_sftp_username: '',
  recording_sftp_password: '',
  upload_to_oss: true,
  delete_local_after_upload: false,
  ...(settings.value.guacamole?.value || {}),
}))
const backupToolsValue = computed(() => ({
  name: 'mysqldump',
  path: '/usr/local/mysql/mysqldump',
  ...(settings.value.backupTools?.value || {}),
}))
const gitToolsValue = computed(() => ({
  name: 'git',
  path: '/mingw64/bin/git',
  ...(settings.value.gitTools?.value || {}),
}))
const mavenToolsValue = computed(() => ({
  name: 'mvn',
  path: 'mvn',
  ...(settings.value.mavenTools?.value || {}),
}))
const npmToolsValue = computed(() => ({
  name: 'npm',
  path: 'npm',
  ...(settings.value.npmTools?.value || {}),
}))
const javaToolsValue = computed(() => ({
  name: 'java',
  java_home: 'JAVA_HOME',
  path: 'java',
  ...(settings.value.javaTools?.value || {}),
}))
const dockerToolsValue = computed(() => ({
  name: 'docker',
  path: DEFAULT_DOCKER_COMMAND_PATH,
  ...(settings.value.dockerTools?.value || {}),
}))
const helmToolsValue = computed(() => ({
  name: 'helm',
  path: 'helm',
  ...(settings.value.helmTools?.value || {}),
}))
/**
 * 返回平台设置键对应的中文名称。
 * 参数：`key` 表示平台设置键。
 * 返回：标准配置返回对应中文名，命令类配置统一返回“命令配置”。
 * 副作用：不直接修改持久化数据。
 */
function configTypeName(key: string) {
  return CONFIG_TYPE_NAMES[key] || '命令配置'
}

const commandSettings = computed(() => {
  const byKey = new Map(props.items.filter(isCommandSetting).map((item) => [item.key, item]))
  const builtins = COMMAND_SETTING_ORDER.map((key) => byKey.get(key)).filter(Boolean) as SettingRow[]
  const custom = props.items
    .filter((item) => isCommandSetting(item) && !BUILTIN_COMMAND_KEYS.has(item.key))
    .sort((left, right) => commandTitle(left).localeCompare(commandTitle(right), 'zh-Hans-CN'))
  return [...builtins, ...custom]
})
const commandModalOpen = computed(() => isCustomCommandKey(editingKey.value))
const availableCreateKeys = computed(() => Object.keys(CONFIG_TYPE_NAMES).filter((key) => !settingForKey(key)))
const modalTitle = computed(() => {
  if (modalMode.value === 'create') return `新增${configTypeName(editingKey.value)}`
  if (isCustomCommandKey(editingKey.value)) return `编辑 ${commandForm.name || '命令'}`
  if (editingKey.value === 'ci.maven_tools') return '编辑 Maven 命令'
  if (editingKey.value === 'ci.npm_tools') return '编辑 npm 命令'
  if (editingKey.value === 'ci.java_tools') return '编辑 Java 命令'
  if (editingKey.value === 'ci.docker_tools') return '编辑 Docker 命令'
  if (editingKey.value === 'platform') return '编辑平台基础设置'
  if (editingKey.value === 'platform.filing') return '编辑备案设置'
  if (editingKey.value === 'security') return '编辑平台安全设置'
  if (editingKey.value === 'storage.oss') return '编辑 OSS 配置'
  if (editingKey.value === 'database.backup_tools') return '编辑数据库备份命令'
  if (editingKey.value === 'ci.git_tools') return '编辑 Git 命令'
  return '编辑录像网关 Guacamole'
})

/**
 * 封装 sessionMinutes 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function sessionMinutes() {
  return Math.max(1, Math.round(Number(securityValue.value.session_timeout || 0) / 60))
}

/**
 * 封装 guacamoleUrl 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`value` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function guacamoleUrl(value = guacamoleValue.value) {
  const path = String(value.base_path || '/guacamole').startsWith('/') ? value.base_path : `/${value.base_path}`
  return `${value.scheme || 'http'}://${value.host || '47.120.40.124'}:${value.port || 9080}${path}`
}

/**
 * 判断 isCommandSetting 对应的业务条件是否成立。
 * 参数：`item` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function isCommandSetting(item?: SettingRow | null) {
  const value = item?.value || {}
  const key = String(item?.key || '')
  return Boolean(value.path) && (key.endsWith('_tools') || key.endsWith('.tools') || String(item?.description || '').includes('命令'))
}

/**
 * 判断 isCustomCommandKey 对应的业务条件是否成立。
 * 参数：`key` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function isCustomCommandKey(key: string) {
  return Boolean(key) && !['platform', 'platform.filing', 'security', 'storage.oss', 'recording.guacamole'].includes(key) && !BUILTIN_COMMAND_KEYS.has(key)
}

/**
 * 封装 commandTitle 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`item` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function commandTitle(item?: SettingRow | null) {
  const name = String(item?.value?.name || item?.key?.split('.').pop()?.replace(/_tools$/, '') || '命令')
  return `${name} 命令`
}

/**
 * 封装 commandDescription 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`item` 表示该步骤所需的业务参数；`fallback` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function commandDescription(item?: SettingRow | null, fallback = '') {
  return String(item?.description || fallback || `${item?.value?.name || '命令'} 命令路径。`)
}

/**
 * 封装 commandKeyFromName 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`name` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function commandKeyFromName(name: string) {
  const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  return `ci.${slug || 'custom'}_tools`
}

/**
 * 触发平台 Logo 文件选择窗口。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能打开浏览器文件选择器。
 */
function choosePlatformLogo() {
  if (!canUpdate.value || logoUploading.value) return
  logoFileInput.value?.click()
}

/**
 * 判断平台 Logo 文件是否符合上传前置规则。
 * 参数：`file` 表示管理员选择的 Logo 图片。
 * 返回：文件合法时返回空字符串，否则返回中文错误提示。
 * 副作用：不直接修改持久化数据。
 */
function validatePlatformLogoFile(file: File) {
  const allowedTypes = new Set(['image/png', 'image/jpeg', 'image/webp', 'image/gif'])
  const allowedExtensions = ['.png', '.jpg', '.jpeg', '.webp', '.gif']
  const name = file.name.toLowerCase()
  if (!allowedExtensions.some((extension) => name.endsWith(extension)) || !allowedTypes.has(file.type)) {
    return 'Logo 只支持 PNG、JPG、JPEG、WEBP 或 GIF 图片'
  }
  if (file.size > 2 * 1024 * 1024) return 'Logo 文件不能超过 2 MB'
  return ''
}

/**
 * 上传平台 Logo 并把后端返回的本地路径回填到表单。
 * 参数：`event` 表示文件选择器变更事件。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、上传文件并修改当前表单路径。
 */
async function uploadPlatformLogo(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const validationError = validatePlatformLogoFile(file)
  if (validationError) {
    error.value = validationError
    return
  }
  logoUploading.value = true
  error.value = ''
  try {
    const formData = new FormData()
    formData.append('file', file)
    const result = await apiForm('/system-settings/platform/logo-upload/', formData)
    platformForm.logo_url = requireLocalAssetUrl(result.logo_url)
  } catch (reason: any) {
    error.value = reason.message || '上传平台 Logo 失败'
  } finally {
    logoUploading.value = false
  }
}

/**
 * 封装 settingForKey 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`key` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function settingForKey(key: string) {
  if (key === 'storage.oss') return settings.value.oss
  if (key === 'recording.guacamole') return settings.value.guacamole
  if (key === 'database.backup_tools') return settings.value.backupTools
  if (key === 'ci.git_tools') return settings.value.gitTools
  if (key === 'ci.maven_tools') return settings.value.mavenTools
  if (key === 'ci.npm_tools') return settings.value.npmTools
  if (key === 'ci.java_tools') return settings.value.javaTools
  if (key === 'ci.docker_tools') return settings.value.dockerTools
  if (key === 'platform') return settings.value.platform
  if (key === 'security') return settings.value.security
  return props.items.find((item) => item.key === key)
}

/**
 * 计算并返回 currentSetting 对应的业务数据。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function currentSetting() {
  return settingForKey(editingKey.value)
}

/**
 * 准备 openCreateCommand 所需数据并打开对应交互界面。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function openCreateCommand() {
  if (!canCreate.value) return
  modalMode.value = 'create'
  editingKey.value = CREATE_COMMAND_KEY
  error.value = ''
  initFormForKey(CREATE_COMMAND_KEY)
  modalOpen.value = true
}

/**
 * 按平台设置键把对应表单填充为已保存的值，缺失时回落到界面默认值。
 * 参数：`key` 表示平台设置键。
 * 返回：无显式返回值。
 * 副作用：会覆盖当前弹窗内未保存的表单输入。
 */
function initFormForKey(key: string) {
  const customSetting = settingForKey(key)
  if (isCustomCommandKey(key)) {
    Object.assign(commandForm, {
      name: customSetting?.value?.name || key.split('.').pop()?.replace(/_tools$/, '') || '',
      path: customSetting?.value?.path || '',
      description: customSetting?.description || '',
    })
    return
  }
  if (key === 'platform') {
    Object.assign(platformForm, {
      name: platformValue.value.name || '',
      logo_url: platformValue.value.logo_url || '',
    })
  } else if (key === 'platform.filing') {
    Object.assign(filingForm, {
      icp_record: filingValue.value.icp_record || '',
      icp_url: filingValue.value.icp_url || '',
      public_security_record: filingValue.value.public_security_record || '',
      public_security_url: filingValue.value.public_security_url || '',
    })
  } else if (key === 'security') {
    Object.assign(securityForm, {
      session_timeout_minutes: sessionMinutes(),
    })
  } else if (key === 'storage.oss') {
    Object.assign(ossForm, {
      enabled: Boolean(ossValue.value.enabled),
      access_key_id: ossValue.value.access_key_id || '',
      access_key_secret: ossValue.value.access_key_secret || '',
      bucket: ossValue.value.bucket || '',
      endpoint: ossValue.value.endpoint || '',
      base_dir: ossValue.value.base_dir || 'baoleiji',
      use_https: Boolean(ossValue.value.use_https),
    })
  } else if (key === 'database.backup_tools') {
    const backupTools = backupToolsValue.value as Record<string, any>
    Object.assign(backupToolsForm, {
      name: backupTools.name || 'mysqldump',
      path: backupTools.path || backupTools.mysqldump_path || '/usr/local/mysql/mysqldump',
    })
  } else if (key === 'ci.git_tools') {
    const gitTools = gitToolsValue.value as Record<string, any>
    Object.assign(gitToolsForm, {
      name: gitTools.name || 'git',
      path: gitTools.path || gitTools.git_path || '/mingw64/bin/git',
    })
  } else if (key === 'ci.maven_tools') {
    const mavenTools = mavenToolsValue.value as Record<string, any>
    Object.assign(mavenToolsForm, {
      name: mavenTools.name || 'mvn',
      path: mavenTools.path || mavenTools.mvn_path || 'mvn',
    })
  } else if (key === 'ci.npm_tools') {
    const npmTools = npmToolsValue.value as Record<string, any>
    Object.assign(npmToolsForm, {
      name: npmTools.name || 'npm',
      path: npmTools.path || npmTools.npm_path || 'npm',
    })
  } else if (key === 'ci.java_tools') {
    const javaTools = javaToolsValue.value as Record<string, any>
    Object.assign(javaToolsForm, {
      name: javaTools.name || 'java',
      java_home: javaTools.java_home || javaTools.JAVA_HOME || 'JAVA_HOME',
      path: javaTools.path || javaTools.java_path || 'java',
    })
  } else if (key === 'ci.docker_tools') {
    const dockerTools = dockerToolsValue.value as Record<string, any>
    Object.assign(dockerToolsForm, {
      name: dockerTools.name || 'docker',
      path: dockerTools.path || dockerTools.docker_path || DEFAULT_DOCKER_COMMAND_PATH,
    })
  } else if (key === 'ci.helm_tools') {
    const helmTools = helmToolsValue.value as Record<string, any>
    Object.assign(helmToolsForm, {
      name: helmTools.name || 'helm',
      path: helmTools.path || 'helm',
    })
  } else {
    Object.assign(guacamoleForm, {
      enabled: Boolean(guacamoleValue.value.enabled),
      scheme: guacamoleValue.value.scheme || 'http',
      host: guacamoleValue.value.host || '47.120.40.124',
      port: Number(guacamoleValue.value.port || 9080),
      base_path: guacamoleValue.value.base_path || '/guacamole',
      json_secret_key: guacamoleValue.value.json_secret_key || '290788bc59d6bef6abf380717bb609e0',
      recording_path: guacamoleValue.value.recording_path || '/recordings',
      recording_read_mode: guacamoleValue.value.recording_read_mode || 'sftp',
      recording_host_path: guacamoleValue.value.recording_host_path || '/root/guacamole/recordings',
      recording_sftp_host: guacamoleValue.value.recording_sftp_host || guacamoleValue.value.host || '47.120.40.124',
      recording_sftp_port: Number(guacamoleValue.value.recording_sftp_port || 22),
      recording_sftp_username: guacamoleValue.value.recording_sftp_username || '',
      recording_sftp_password: guacamoleValue.value.recording_sftp_password || '',
      upload_to_oss: true,
      delete_local_after_upload: Boolean(guacamoleValue.value.delete_local_after_upload),
    })
  }
}

/**
 * 准备 openEdit 所需数据并打开对应交互界面。
 * 参数：`key` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function openEdit(key: SettingKey) {
  if (!canUpdate.value) return
  modalMode.value = 'edit'
  editingKey.value = key
  error.value = ''
  revealing.value = false
  ossSecretVisible.value = false
  guacamoleSecretVisible.value = false
  guacamoleSftpPasswordVisible.value = false
  initFormForKey(key)
  modalOpen.value = true
}

/**
 * 组装 payloadForCurrent 对应的接口或界面数据结构。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function payloadForCurrent() {
  if (editingKey.value === 'platform') {
    return {
      key: 'platform',
      description: '平台基础设置',
      value: {
        name: platformForm.name,
        logo_url: requireLocalAssetUrl(platformForm.logo_url),
      },
    }
  }
  if (editingKey.value === 'platform.filing') {
    return {
      key: 'platform.filing',
      description: '登录页工信部与公安部备案信息',
      value: {
        icp_record: filingForm.icp_record,
        icp_url: filingForm.icp_url,
        public_security_record: filingForm.public_security_record,
        public_security_url: filingForm.public_security_url,
      },
    }
  }
  return {
    key: 'security',
    description: '平台安全设置',
    value: {
      session_timeout: Math.max(1, Number(securityForm.session_timeout_minutes || 1)) * 60,
    },
  }
}

/**
 * 组装 payloadForSave 对应的接口或界面数据结构。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function payloadForSave() {
  if (commandModalOpen.value) {
    const key = modalMode.value === 'create' ? commandKeyFromName(commandForm.name) : editingKey.value
    return {
      key,
      description: commandForm.description || `${commandForm.name || '命令'} 命令配置`,
      value: {
        name: commandForm.name,
        path: commandForm.path,
      },
    }
  }
  if (editingKey.value !== 'storage.oss' && editingKey.value !== 'recording.guacamole' && editingKey.value !== 'database.backup_tools' && editingKey.value !== 'ci.git_tools' && editingKey.value !== 'ci.maven_tools' && editingKey.value !== 'ci.npm_tools' && editingKey.value !== 'ci.java_tools' && editingKey.value !== 'ci.docker_tools' && editingKey.value !== 'ci.helm_tools') return payloadForCurrent()
  if (editingKey.value === 'database.backup_tools') {
    return {
      key: 'database.backup_tools',
      description: '数据库备份命令配置',
      value: {
        name: backupToolsForm.name || 'mysqldump',
        path: backupToolsForm.path || '/usr/local/mysql/mysqldump',
      },
    }
  }
  if (editingKey.value === 'ci.git_tools') {
    return {
      key: 'ci.git_tools',
      description: 'Git 命令配置',
      value: {
        name: gitToolsForm.name || 'git',
        path: gitToolsForm.path || '/mingw64/bin/git',
      },
    }
  }
  if (editingKey.value === 'ci.maven_tools') {
    return {
      key: 'ci.maven_tools',
      description: 'Maven 命令配置',
      value: {
        name: mavenToolsForm.name || 'mvn',
        path: mavenToolsForm.path || 'mvn',
      },
    }
  }
  if (editingKey.value === 'ci.npm_tools') {
    return {
      key: 'ci.npm_tools',
      description: 'npm 命令配置',
      value: {
        name: npmToolsForm.name || 'npm',
        path: npmToolsForm.path || 'npm',
      },
    }
  }
  if (editingKey.value === 'ci.java_tools') {
    return {
      key: 'ci.java_tools',
      description: 'Java 命令',
      value: {
        name: javaToolsForm.name || 'java',
        java_home: javaToolsForm.java_home || 'JAVA_HOME',
        path: javaToolsForm.path || 'java',
      },
    }
  }
  if (editingKey.value === 'ci.docker_tools') {
    return {
      key: 'ci.docker_tools',
      description: 'Docker 命令配置',
      value: {
        name: dockerToolsForm.name || 'docker',
        path: dockerToolsForm.path || DEFAULT_DOCKER_COMMAND_PATH,
      },
    }
  }
  if (editingKey.value === 'ci.helm_tools') {
    return {
      key: 'ci.helm_tools',
      description: 'Helm command config',
      value: {
        name: helmToolsForm.name || 'helm',
        path: helmToolsForm.path || 'helm',
      },
    }
  }
  if (editingKey.value === 'recording.guacamole') {
    return {
      key: 'recording.guacamole',
      description: 'Web RDP 录像网关 Guacamole 配置',
      value: {
        enabled: guacamoleForm.enabled,
        scheme: guacamoleForm.scheme || 'http',
        host: guacamoleForm.host,
        port: Number(guacamoleForm.port || 9080),
        base_path: guacamoleForm.base_path || '/guacamole',
        json_secret_key: guacamoleForm.json_secret_key,
        recording_path: guacamoleForm.recording_path || '/recordings',
        recording_read_mode: guacamoleForm.recording_read_mode || 'sftp',
        recording_host_path: guacamoleForm.recording_host_path || '/root/guacamole/recordings',
        recording_sftp_host: guacamoleForm.recording_sftp_host || guacamoleForm.host,
        recording_sftp_port: Number(guacamoleForm.recording_sftp_port || 22),
        recording_sftp_username: guacamoleForm.recording_sftp_username,
        recording_sftp_password: guacamoleForm.recording_sftp_password,
        upload_to_oss: true,
        delete_local_after_upload: guacamoleForm.delete_local_after_upload,
      },
    }
  }
  return {
    key: 'storage.oss',
    description: '堡垒机录像 OSS 存储配置',
    value: {
      enabled: ossForm.enabled,
      access_key_id: ossForm.access_key_id,
      access_key_secret: ossForm.access_key_secret,
      bucket: ossForm.bucket,
      endpoint: ossForm.endpoint,
      base_dir: ossForm.base_dir || 'baoleiji',
      use_https: ossForm.use_https,
    },
  }
}

/**
 * 准备 revealSecret 所需数据并打开对应交互界面。
 * 参数：`kind` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
async function revealSecret(kind: 'oss' | 'guacamole' | 'guacamole_sftp') {
  if (!canReveal.value) return
  if (kind === 'oss' && ossSecretVisible.value) {
    ossSecretVisible.value = false
    return
  }
  if (kind === 'guacamole' && guacamoleSecretVisible.value) {
    guacamoleSecretVisible.value = false
    return
  }
  if (kind === 'guacamole_sftp' && guacamoleSftpPasswordVisible.value) {
    guacamoleSftpPasswordVisible.value = false
    return
  }
  revealing.value = true
  error.value = ''
  try {
    const path = kind === 'oss'
      ? '/system-settings/storage/oss/reveal'
      : '/system-settings/recording/guacamole/reveal'
    const result = await api(path)
    if (kind === 'oss') {
      ossForm.access_key_secret = result.value?.access_key_secret || ossForm.access_key_secret
      ossSecretVisible.value = !ossSecretVisible.value
    } else if (kind === 'guacamole') {
      guacamoleForm.json_secret_key = result.value?.json_secret_key || guacamoleForm.json_secret_key
      guacamoleSecretVisible.value = !guacamoleSecretVisible.value
    } else {
      guacamoleForm.recording_sftp_password = result.value?.recording_sftp_password || guacamoleForm.recording_sftp_password
      guacamoleSftpPasswordVisible.value = !guacamoleSftpPasswordVisible.value
    }
  } catch (reason: any) {
    error.value = reason.message || '读取真实密钥失败'
  } finally {
    revealing.value = false
  }
}

/**
 * 校验当前输入并完成 saveSetting 对应的数据保存操作。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function saveSetting() {
  if (modalMode.value === 'create' ? !canCreate.value : !canUpdate.value) return
  saving.value = true
  error.value = ''
  try {
    const payload = payloadForSave()
    const current = currentSetting()
    if (modalMode.value === 'create' && props.items.some((item) => item.key === payload.key)) {
      throw new Error(`${configTypeName(payload.key)}已存在，请直接编辑原配置`)
    }
    if (current?.id) {
      await api(`/settings/${current.id}/`, { method: 'PATCH', body: JSON.stringify(payload) })
    } else {
      await api('/settings/', { method: 'POST', body: JSON.stringify(payload) })
    }
    modalOpen.value = false
    if (editingKey.value === 'platform' || editingKey.value === 'platform.filing') {
      await platform.loadPublic(true)
    }
    emit('refresh')
  } catch (reason: any) {
    error.value = reason.message || '保存平台设置失败'
  } finally {
    saving.value = false
  }
}

/**
 * 准备 openDelete 所需数据并打开对应交互界面。
 * 参数：`setting` 表示该步骤所需的业务参数；`title` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function openDelete(setting: SettingRow | undefined, title: string, hint = '') {
  if (!setting?.id || !canDelete.value) return
  deleteTarget.value = setting
  deleteTitle.value = title
  deleteHint.value = hint
  error.value = ''
}

/**
 * 组装删除确认弹窗的提示文案。
 * 参数：无。
 * 返回：返回包含配置名称和删除后果的中文提示。
 * 副作用：不直接修改持久化数据。
 */
const deleteMessage = computed(() => {
  const label = deleteTitle.value || deleteTarget.value?.key || '该配置'
  return `确认删除 ${label}？${deleteHint.value || '删除后该配置会恢复为系统默认值。'}`
})

/**
 * 执行 removeSetting 对应的清理或删除操作并同步页面状态。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function removeSetting() {
  if (!deleteTarget.value?.id || !canDelete.value) return
  deleting.value = true
  try {
    await api(`/settings/${deleteTarget.value.id}/`, { method: 'DELETE' })
    deleteTarget.value = null
    emit('refresh')
  } catch (reason: any) {
    error.value = reason.message || '删除平台设置失败'
  } finally {
    deleting.value = false
  }
}

watch(editingKey, (key) => {
  if (modalMode.value !== 'create') return
  error.value = ''
  initFormForKey(key)
})

watch(() => props.items, () => {
  if (!modalOpen.value) error.value = ''
})
</script>

<template>
  <section class="platform-settings-page">
    <header class="governance-page-head">
      <div>
        <h2>平台设置</h2>
      </div>
      <div class="settings-head-actions">
        <button v-if="activeTab === 'basic' && canCreate" class="primary" type="button" @click="openCreateCommand">
          <Plus :size="16" />新增
        </button>
        <button class="secondary" type="button" :disabled="loading" @click="emit('refresh')">
          <RefreshCw :size="16" :class="{ spin: loading }" />刷新
        </button>
      </div>
    </header>

    <nav class="platform-settings-tabs" aria-label="平台设置分类">
      <button
        v-for="tab in settingsTabs"
        :key="tab.code"
        type="button"
        :class="{ active: activeTab === tab.code }"
        @click="activeTab = tab.code"
      >
        {{ tab.name }}
      </button>
    </nav>

    <div v-if="activeTab === 'basic'" class="platform-settings-grid">
      <section v-if="settings.platform" class="platform-settings-card">
        <div class="platform-settings-card-head">
          <span class="settings-icon"><SlidersHorizontal :size="18" /></span>
          <div>
            <h3>平台基础设置</h3>
            <p>平台名称和 Logo。</p>
          </div>
          <div class="settings-card-actions">
            <button v-if="canUpdate" class="secondary settings-edit-button" title="编辑" @click="openEdit('platform')"><Edit3 :size="16" />编辑</button>
            <button
              v-if="canDelete"
              class="danger-inline"
              type="button"
              @click="openDelete(settings.platform, '平台基础设置', '删除后平台名称和 Logo 会恢复为系统默认值。')"
            >删除</button>
          </div>
        </div>
        <dl class="settings-list">
          <dt>平台名称</dt><dd>{{ platformValue.name || '未设置' }}</dd>
          <dt>平台 Logo</dt>
          <dd>
            <span v-if="localAssetUrl(platformValue.logo_url)" class="logo-preview">
              <img :src="localAssetUrl(platformValue.logo_url)" alt="" />
              {{ localAssetUrl(platformValue.logo_url) }}
            </span>
            <span v-else>未设置</span>
          </dd>
        </dl>
      </section>

      <section v-if="settings.filing" class="platform-settings-card">
        <div class="platform-settings-card-head">
          <span class="settings-icon"><ShieldCheck :size="18" /></span>
          <div>
            <h3>备案设置</h3>
            <p>配置登录页展示的工信部和公安部备案信息。</p>
          </div>
          <div class="settings-card-actions">
            <button v-if="canUpdate" class="secondary settings-edit-button" title="编辑" @click="openEdit('platform.filing')"><Edit3 :size="16" />编辑</button>
            <button
              v-if="canDelete"
              class="danger-inline"
              type="button"
              @click="openDelete(settings.filing, '备案设置', '删除后登录页不再展示工信部和公安部备案信息。')"
            >删除</button>
          </div>
        </div>
        <dl class="settings-list">
          <dt>工信部备案号</dt><dd>{{ filingValue.icp_record || '未设置' }}</dd>
          <dt>工信部链接</dt><dd>{{ filingValue.icp_url || '未设置' }}</dd>
          <dt>公安部备案号</dt><dd>{{ filingValue.public_security_record || '未设置' }}</dd>
          <dt>公安部链接</dt><dd>{{ filingValue.public_security_url || '未设置' }}</dd>
        </dl>
      </section>

      <section v-if="settings.security" class="platform-settings-card">
        <div class="platform-settings-card-head">
          <span class="settings-icon"><ShieldCheck :size="18" /></span>
          <div>
            <h3>平台安全设置</h3>
            <p>用户登录会话策略。</p>
          </div>
          <div class="settings-card-actions">
            <button v-if="canUpdate" class="secondary settings-edit-button" title="编辑" @click="openEdit('security')"><Edit3 :size="16" />编辑</button>
            <button
              v-if="canDelete"
              class="danger-inline"
              type="button"
              @click="openDelete(settings.security, '平台安全设置', '删除后用户 Session 有效期会恢复为 30 分钟。')"
            >删除</button>
          </div>
        </div>
        <dl class="settings-list">
          <dt>用户 Session 有效期</dt><dd>{{ sessionMinutes() }} 分钟</dd>
        </dl>
      </section>
      <section v-if="settings.oss" class="platform-settings-card">
        <div class="platform-settings-card-head">
          <span class="settings-icon"><Cloud :size="18" /></span>
          <div>
            <h3>OSS 配置</h3>
            <p>堡垒机 SSH 录像和 RDP 录像统一存储。</p>
          </div>
          <div class="settings-card-actions">
            <button v-if="canUpdate" class="secondary settings-edit-button" title="编辑" @click="openEdit('storage.oss')"><Edit3 :size="16" />编辑</button>
            <button
              v-if="canDelete"
              class="danger-inline"
              type="button"
              @click="openDelete(settings.oss, 'OSS 配置', '删除后堡垒机录像将无法上传 OSS 统一存储。')"
            >删除</button>
          </div>
        </div>
        <dl class="settings-list">
          <dt>状态</dt><dd><span :class="['badge', ossValue.enabled ? 'healthy' : 'offline']">{{ ossValue.enabled ? '已启用' : '已禁用' }}</span></dd>
          <dt>Bucket</dt><dd>{{ ossValue.bucket || '未设置' }}</dd>
          <dt>Endpoint</dt><dd>{{ ossValue.endpoint || '未设置' }}</dd>
          <dt>存储目录</dt><dd>{{ ossValue.base_dir || 'baoleiji' }}</dd>
          <dt>访问方式</dt><dd>{{ ossValue.use_https ? 'HTTPS' : 'HTTP' }}</dd>
        </dl>
      </section>

      <section v-if="settings.guacamole" class="platform-settings-card">
        <div class="platform-settings-card-head">
          <span class="settings-icon"><ServerCog :size="18" /></span>
          <div>
            <h3>录像网关 Guacamole</h3>
            <p>Web RDP 网关、JSON Auth 和服务器录像清理策略。</p>
          </div>
          <div class="settings-card-actions">
            <button v-if="canUpdate" class="secondary settings-edit-button" title="编辑" @click="openEdit('recording.guacamole')"><Edit3 :size="16" />编辑</button>
            <button
              v-if="canDelete"
              class="danger-inline"
              type="button"
              @click="openDelete(settings.guacamole, '录像网关 Guacamole', '删除后 Web RDP 网关和录像清理策略会恢复为系统默认值。')"
            >删除</button>
          </div>
        </div>
        <dl class="settings-list">
          <dt>状态</dt><dd><span :class="['badge', guacamoleValue.enabled ? 'healthy' : 'offline']">{{ guacamoleValue.enabled ? '已启用' : '已禁用' }}</span></dd>
          <dt>网关地址</dt><dd>{{ guacamoleUrl() }}</dd>
          <dt>录像目录</dt><dd>{{ guacamoleValue.recording_path || '/recordings' }}</dd>
          <dt>读取方式</dt><dd>{{ guacamoleValue.recording_read_mode === 'sftp' ? 'SFTP 拉取' : 'Django 本机目录' }}</dd>
          <dt>OSS 上传</dt><dd>必须上传</dd>
          <dt>本地录像</dt><dd>{{ guacamoleValue.delete_local_after_upload ? '上传 OSS 后删除' : '上传 OSS 后保留' }}</dd>
        </dl>
      </section>
      <section v-for="item in commandSettings" :key="item.key" class="platform-settings-card">
        <div class="platform-settings-card-head">
          <span class="settings-icon">
            <DatabaseBackup v-if="item.key === 'database.backup_tools'" :size="18" />
            <GitBranch v-else-if="item.key === 'ci.git_tools'" :size="18" />
            <Container v-else-if="item.key === 'ci.docker_tools'" :size="18" />
            <Terminal v-else :size="18" />
          </span>
          <div>
            <h3>{{ commandTitle(item) }}</h3>
            <p>{{ commandDescription(item) }}</p>
          </div>
          <div class="settings-card-actions">
            <button v-if="canUpdate" class="secondary settings-edit-button" title="编辑" @click="openEdit(item.key)"><Edit3 :size="16" />编辑</button>
            <button v-if="canDelete" class="danger-inline" type="button" @click="openDelete(item, commandTitle(item), '删除后该命令不会再下发给 Worker。')">删除</button>
          </div>
        </div>
        <dl class="settings-list">
          <dt>名称</dt><dd>{{ item.value?.name || '-' }}</dd>
          <dt v-if="item.value?.java_home">JAVA_HOME</dt><dd v-if="item.value?.java_home">{{ item.value?.java_home }}</dd>
          <dt>路径</dt><dd>{{ item.value?.path || '-' }}</dd>
        </dl>
      </section>
    </div>
    <PlatformSecuritySettings
      v-else
      :active-tab="activeTab"
      :items="items"
      @refresh="emit('refresh')"
    />
  </section>

  <ModalDialog
    :open="modalOpen"
    :title="modalTitle"
    dialog-class="platform-settings-dialog"
    description="请按中文字段维护配置，保存后会写入平台设置。"
    @close="modalOpen = false"
  >
    <form class="form-grid" @submit.prevent="saveSetting">
      <label v-if="modalMode === 'create'">配置类型
        <CustomSelect v-model="editingKey">
          <option :value="CREATE_COMMAND_KEY">{{ configTypeName(CREATE_COMMAND_KEY) }}</option>
          <option v-for="key in availableCreateKeys" :key="key" :value="key">{{ configTypeName(key) }}</option>
        </CustomSelect>
      </label>
      <template v-if="editingKey === 'platform'">
        <label>平台名称<input v-model.trim="platformForm.name" required /></label>
        <label class="platform-logo-field">
          平台 Logo
          <button class="platform-logo-upload" type="button" :disabled="logoUploading" @click="choosePlatformLogo">
            <span v-if="platformFormLogoUrl" class="platform-logo-upload-preview">
              <img :src="platformFormLogoUrl" alt="" />
            </span>
            <span v-else class="platform-logo-upload-empty"><Upload :size="18" /></span>
            <strong>{{ logoUploading ? '上传中' : '点击上传 Logo' }}</strong>
            <small>{{ platformFormLogoUrl || '默认沿用当前 Logo，支持 PNG、JPG、WEBP、GIF，最大 2 MB' }}</small>
          </button>
          <input ref="logoFileInput" class="visually-hidden-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="uploadPlatformLogo" />
        </label>
        <label>平台 Logo 本地路径<input v-model.trim="platformForm.logo_url" placeholder="/assets/brand/logo.svg" /></label>
      </template>
      <template v-else-if="editingKey === 'platform.filing'">
        <label>工信部备案号<input v-model.trim="filingForm.icp_record" maxlength="100" placeholder="冀ICP备2026010543号-3" /></label>
        <label>工信部链接地址<input v-model.trim="filingForm.icp_url" type="url" maxlength="500" placeholder="https://beian.miit.gov.cn/" /></label>
        <label>公安部备案号<input v-model.trim="filingForm.public_security_record" maxlength="100" placeholder="冀公网安备13310102000221号" /></label>
        <label>公安部链接地址<input v-model.trim="filingForm.public_security_url" type="url" maxlength="500" placeholder="http://www.beian.gov.cn/portal/registerSystemInfo" /></label>
      </template>
      <template v-else-if="commandModalOpen">
        <label>名称<input v-model.trim="commandForm.name" required placeholder="npm" /></label>
        <label>路径<input v-model.trim="commandForm.path" required placeholder="C:\nvm4w\nodejs\npm.cmd" /></label>
        <label>说明<input v-model.trim="commandForm.description" placeholder="Vue 打包使用的 npm 命令路径。" /></label>
      </template>
      <template v-else-if="editingKey === 'security'">
        <label>用户 Session 有效期（分钟）<input v-model.number="securityForm.session_timeout_minutes" type="number" min="1" required /></label>
      </template>
      <template v-else-if="editingKey === 'storage.oss'">
        <label class="check"><span>启用 OSS</span><input v-model="ossForm.enabled" type="checkbox" /></label>
        <label>AccessKey ID<input v-model.trim="ossForm.access_key_id" required /></label>
        <label>
          AccessKey Secret
          <span class="secret-input">
            <input v-model.trim="ossForm.access_key_secret" :type="ossSecretVisible ? 'text' : 'password'" required autocomplete="off" spellcheck="false" />
            <button v-if="canReveal" class="password-visibility-button" type="button" :title="ossSecretVisible ? '隐藏密钥' : '显示密钥'" :disabled="revealing" @click="revealSecret('oss')">
              <EyeOff v-if="ossSecretVisible" :size="16" />
              <Eye v-else :size="16" />
              <span>{{ ossSecretVisible ? '隐藏' : '显示' }}</span>
            </button>
          </span>
        </label>
        <label>Bucket<input v-model.trim="ossForm.bucket" required /></label>
        <label>Endpoint<input v-model.trim="ossForm.endpoint" placeholder="oss-cn-beijing.aliyuncs.com" required /></label>
        <label>存储目录<input v-model.trim="ossForm.base_dir" placeholder="baoleiji" required /></label>
        <label class="check"><span>HTTPS 访问</span><input v-model="ossForm.use_https" type="checkbox" /></label>
      </template>
      <template v-else-if="editingKey === 'database.backup_tools'">
        <label>名称<input v-model.trim="backupToolsForm.name" required placeholder="mysqldump" /></label>
        <label>路径<input v-model.trim="backupToolsForm.path" required placeholder="/usr/local/mysql/mysqldump" /></label>
      </template>
      <template v-else-if="editingKey === 'ci.git_tools'">
        <label>名称<input v-model.trim="gitToolsForm.name" required placeholder="git" /></label>
        <label>路径<input v-model.trim="gitToolsForm.path" required placeholder="/mingw64/bin/git" /></label>
      </template>
      <template v-else-if="editingKey === 'ci.maven_tools'">
        <label>名称<input v-model.trim="mavenToolsForm.name" required placeholder="mvn" /></label>
        <label>路径<input v-model.trim="mavenToolsForm.path" required placeholder="mvn" /></label>
      </template>
      <template v-else-if="editingKey === 'ci.npm_tools'">
        <label>名称<input v-model.trim="npmToolsForm.name" required placeholder="npm" /></label>
        <label>路径<input v-model.trim="npmToolsForm.path" required placeholder="npm" /></label>
      </template>
      <template v-else-if="editingKey === 'ci.java_tools'">
        <label>名称<input v-model.trim="javaToolsForm.name" required placeholder="java" /></label>
        <label>JAVA_HOME<input v-model.trim="javaToolsForm.java_home" required placeholder="JAVA_HOME" /></label>
        <label>java路径<input v-model.trim="javaToolsForm.path" required placeholder="java" /></label>
      </template>
      <template v-else-if="editingKey === 'ci.docker_tools'">
        <label>名称<input v-model.trim="dockerToolsForm.name" required placeholder="docker" /></label>
        <label>路径<input v-model.trim="dockerToolsForm.path" required :placeholder="DEFAULT_DOCKER_COMMAND_PATH" /></label>
      </template>
      <template v-else-if="editingKey === 'ci.helm_tools'">
        <label>名称<input v-model.trim="helmToolsForm.name" required placeholder="helm" /></label>
        <label>路径<input v-model.trim="helmToolsForm.path" required placeholder="C:\\path\\to\\helm.exe" /></label>
      </template>
      <template v-else>
        <label class="check"><span>启用 Guacamole 网关</span><input v-model="guacamoleForm.enabled" type="checkbox" /></label>
        <label>访问协议
          <CustomSelect v-model="guacamoleForm.scheme">
            <option value="http">HTTP</option>
            <option value="https">HTTPS</option>
          </CustomSelect>
        </label>
        <label>网关 IP / 域名<input v-model.trim="guacamoleForm.host" placeholder="47.120.40.124" required /></label>
        <label>网关端口<input v-model.number="guacamoleForm.port" type="number" min="1" max="65535" required /></label>
        <label>访问路径<input v-model.trim="guacamoleForm.base_path" placeholder="/guacamole" required /></label>
        <label>
          JSON_SECRET_KEY
          <span class="secret-input">
            <input v-model.trim="guacamoleForm.json_secret_key" :type="guacamoleSecretVisible ? 'text' : 'password'" required autocomplete="off" spellcheck="false" />
            <button v-if="canReveal" class="password-visibility-button" type="button" :title="guacamoleSecretVisible ? '隐藏密钥' : '显示密钥'" :disabled="revealing" @click="revealSecret('guacamole')">
              <EyeOff v-if="guacamoleSecretVisible" :size="16" />
              <Eye v-else :size="16" />
              <span>{{ guacamoleSecretVisible ? '隐藏' : '显示' }}</span>
            </button>
          </span>
        </label>
        <label>服务器录像目录<input v-model.trim="guacamoleForm.recording_path" placeholder="/recordings" required /></label>
        <label>录像读取方式
          <CustomSelect v-model="guacamoleForm.recording_read_mode">
            <option value="sftp">SFTP 拉取公网服务器录像</option>
            <option value="local">Django 本机目录</option>
          </CustomSelect>
        </label>
        <label>宿主机录像目录<input v-model.trim="guacamoleForm.recording_host_path" placeholder="/root/guacamole/recordings" required /></label>
        <label v-if="guacamoleForm.recording_read_mode === 'sftp'">SFTP 主机<input v-model.trim="guacamoleForm.recording_sftp_host" placeholder="47.120.40.124" required /></label>
        <label v-if="guacamoleForm.recording_read_mode === 'sftp'">SFTP 端口<input v-model.number="guacamoleForm.recording_sftp_port" type="number" min="1" max="65535" required /></label>
        <label v-if="guacamoleForm.recording_read_mode === 'sftp'">SFTP 用户<input v-model.trim="guacamoleForm.recording_sftp_username" placeholder="root" required /></label>
        <label v-if="guacamoleForm.recording_read_mode === 'sftp'">
          SFTP 密码
          <span class="secret-input">
            <input v-model.trim="guacamoleForm.recording_sftp_password" :type="guacamoleSftpPasswordVisible ? 'text' : 'password'" required autocomplete="off" spellcheck="false" />
            <button v-if="canReveal" class="password-visibility-button" type="button" :title="guacamoleSftpPasswordVisible ? '隐藏密码' : '显示密码'" :disabled="revealing" @click="revealSecret('guacamole_sftp')">
              <EyeOff v-if="guacamoleSftpPasswordVisible" :size="16" />
              <Eye v-else :size="16" />
              <span>{{ guacamoleSftpPasswordVisible ? '隐藏' : '显示' }}</span>
            </button>
          </span>
        </label>
        <label class="check"><span>录像必须上传 OSS</span><input v-model="guacamoleForm.upload_to_oss" type="checkbox" disabled /></label>
        <label class="check"><span>上传 OSS 成功后删除服务器录像</span><input v-model="guacamoleForm.delete_local_after_upload" type="checkbox" /></label>
      </template>
      <p v-if="error" class="form-error">{{ error }}</p>
      <footer>
        <button class="secondary" type="button" @click="modalOpen = false">取消</button>
        <button class="primary" :disabled="saving">{{ saving ? '处理中' : (modalMode === 'create' ? '确定' : '保存') }}</button>
      </footer>
    </form>
  </ModalDialog>

  <ConfirmDialog
    :open="!!deleteTarget"
    title="删除平台配置"
    :message="deleteMessage"
    confirm-text="确认删除"
    :loading="deleting"
    dialog-class="platform-settings-dialog"
    @cancel="deleteTarget = null"
    @confirm="removeSetting"
  >
    <p v-if="error" class="form-error">{{ error }}</p>
  </ConfirmDialog>
</template>
