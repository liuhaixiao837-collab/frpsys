<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api'
import { normalize } from '../endpoints'
import { resourceSchemas } from '../resourceSchemas'

const MenuOrderPanel = defineAsyncComponent(() => import('./workbench/MenuOrderPanel.vue'))
const PlatformSettingsPanel = defineAsyncComponent(() => import('./workbench/PlatformSettingsPanel.vue'))
const SystemStatusPanel = defineAsyncComponent(() => import('./workbench/SystemStatusPanel.vue'))
const SystemToolsPanel = defineAsyncComponent(() => import('./workbench/SystemToolsPanel.vue'))
const UsersPanel = defineAsyncComponent(() => import('./workbench/UsersPanel.vue'))
const UserReportPanel = defineAsyncComponent(() => import('./workbench/user-management/UserReportPanel.vue'))
const SystemLogDirectory = defineAsyncComponent(() => import('./workbench/user-management/AuditDirectory.vue'))
const UserLogDirectory = defineAsyncComponent(() => import('./workbench/user-management/UserLogDirectory.vue'))
const FrpPanel = defineAsyncComponent(() => import('./workbench/security/FrpPanel.vue'))

const route = useRoute()
const settings = ref<any[]>([])
const frpItems = ref<any[]>([])
const frpPage = ref(1)
const frpTotal = ref(0)
const frpPageSize = 10
const error = ref('')
const currentSchema = computed(() => resourceSchemas[route.path])

/**
 * 生成包含当前筛选和分页参数的 FRP 列表接口地址。
 * 参数：无。
 * 返回：返回可直接请求的接口地址。
 * 副作用：不直接修改持久化数据。
 */
function frpEndpoint() {
  const endpoint = currentSchema.value?.endpoint || ''
  const [base, rawQuery = ''] = endpoint.split('?')
  const params = new URLSearchParams(rawQuery)
  for (const [key, value] of Object.entries(route.query)) {
    if (Array.isArray(value)) value.forEach((item) => item != null && params.append(key, String(item)))
    else if (value != null) params.set(key, String(value))
  }
  params.set('page', String(frpPage.value))
  params.set('page_size', String(frpPageSize))
  return `${base}?${params.toString()}`
}

/**
 * 封装 userManagementTab 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function userManagementTab() {
  if (['/admin/orgs', '/admin/departments'].includes(route.path)) return 'departments'
  if (route.path === '/admin/permissions') return 'permissions'
  return 'users'
}

/**
 * 从后端或当前状态加载 load 所需的最新业务数据。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function load() {
  error.value = ''
  try {
    if (route.path === '/settings') {
      settings.value = normalize(await api('/settings/'))
      return
    }
    if (currentSchema.value) {
      const payload = await api(frpEndpoint())
      frpItems.value = normalize(payload)
      frpTotal.value = Number(payload?.count ?? frpItems.value.length)
    }
  } catch (reason: any) {
    error.value = reason.message
  }
}

/**
 * 切换 FRP 列表页码并重新读取当前资源。
 * 参数：`page` 表示目标页码。
 * 返回：无显式返回值。
 * 副作用：请求后端并更新列表数据。
 */
function goFrpPage(page: number) {
  frpPage.value = page
  load()
}

watch(() => route.fullPath, (_path, previousPath) => {
  if (route.path !== previousPath.split('?')[0]) frpPage.value = 1
  load()
})
onMounted(load)
</script>

<template>
  <div v-if="error" class="empty">{{ error }}</div>
  <UsersPanel
    v-else-if="['/admin/users', '/admin/orgs', '/admin/departments', '/admin/permissions'].includes(route.path)"
    :initial-tab="userManagementTab()"
    @refresh="load"
  />
  <UserReportPanel v-else-if="route.path === '/admin/user-report'" />
  <UserLogDirectory v-else-if="route.path === '/logs/users'" />
  <SystemLogDirectory v-else-if="route.path === '/logs/system'" />
  <FrpPanel
    v-else-if="route.path.startsWith('/security/frp')"
    :schema="currentSchema"
    :items="frpItems"
    :page="frpPage"
    :page-size="frpPageSize"
    :total="frpTotal"
    @page="goFrpPage"
    @refresh="load"
  />
  <MenuOrderPanel v-else-if="route.path === '/settings/menu-order'" />
  <SystemStatusPanel v-else-if="route.path === '/settings/system-status'" />
  <SystemToolsPanel v-else-if="route.path === '/settings/system-tools'" />
  <PlatformSettingsPanel
    v-else-if="route.path === '/settings'"
    :items="settings"
    @refresh="load"
  />
  <div v-else class="empty">页面不存在</div>
</template>
