<script setup lang="ts">
import {
  BadgeCheck, BriefcaseBusiness, Building2, Check, ChevronDown, ChevronLeft,
  ChevronRight, CircleUserRound, Clock3, Gauge, KeyRound, LogOut, Mail, Moon,
  Palette, ShieldCheck, Sun, UserRound, X,
} from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { navigationGroups, pages } from './navigation'
import { hasAllPermissions, requiredPermissionsForPath } from './permissions'
import SystemWatermark from './components/SystemWatermark.vue'
import { useAuthStore } from './stores/auth'
import { usePlatformStore } from './stores/platform'
import { formatPlatformDateTime } from './utils/dateTime'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const platform = usePlatformStore()
const isPublic = computed(() => Boolean(route.meta.public))
const groups = computed(() => navigationGroups.map((group) => {
  const items = group[1]
    .map((item) => allowedNavItem(item))
    .filter(Boolean)
  return [group[0], items, group[2], group[3], group[4]] as any
}).filter((group) => (group[1] as any[]).length))
const uiStyleVersion = 'ongrid_ui_style_20260610_itops_right_workspace'
const savedTheme = localStorage.getItem('ongrid_theme')
type ThemeMode = 'dark' | 'light'
type ThemeOption = {
  id: string
  name: string
  description: string
  mode: ThemeMode
  swatches: [string, string, string]
}
const themeOptions: ThemeOption[] = [
  { id: 'obsidian', name: '星云夜', description: '靛蓝与湖青', mode: 'dark', swatches: ['#11131a', '#4f46e5', '#0891b2'] },
  { id: 'navy', name: '深海蓝', description: '深蓝与湖青', mode: 'dark', swatches: ['#101823', '#2563eb', '#0891b2'] },
  { id: 'pearl', name: '星云白', description: '靛蓝与亮蓝', mode: 'light', swatches: ['#f1f4fc', '#4f46e5', '#2563eb'] },
  { id: 'silver', name: '天青白', description: '天蓝与湖青', mode: 'light', swatches: ['#edf5fb', '#2563eb', '#0891b2'] },
]
const darkThemes = themeOptions.filter((item) => item.mode === 'dark')
const lightThemes = themeOptions.filter((item) => item.mode === 'light')
const legacyThemeAliases: Record<string, string> = {
  dark: 'navy',
  light: 'silver',
  midnight: 'navy',
  graphite: 'navy',
  cloud: 'silver',
  sky: 'silver',
  pine: 'obsidian',
  mint: 'silver',
  rose: 'pearl',
  aubergine: 'navy',
  lilac: 'silver',
}
const storedThemeId = savedTheme ? (legacyThemeAliases[savedTheme] || savedTheme) : null
const initialThemeId = themeOptions.some((item) => item.id === storedThemeId) ? storedThemeId! : 'navy'
const themeId = ref(initialThemeId)
const currentTheme = computed(() => themeOptions.find((item) => item.id === themeId.value) || themeOptions[0])
const themeMenuOpen = ref(false)
const themePickerRef = ref<HTMLElement | null>(null)
const accountPanelOpen = ref(false)
const accountMenuRef = ref<HTMLElement | null>(null)
const sidebarCollapsed = ref(localStorage.getItem('ongrid_sidebar_collapsed') === '1')
const accountFullName = computed(() => {
  const fullName = `${auth.user?.last_name || ''}${auth.user?.first_name || ''}`.trim()
  return fullName || auth.user?.username || '未登录'
})
const accountPermissionCount = computed(() => (auth.user?.permissions || []).filter((code) => code !== '*').length)
const accountLastLogin = computed(() => formatPlatformDateTime(auth.user?.last_login, '首次登录'))
localStorage.setItem(uiStyleVersion, '1')
/**
 * 计算并返回 getStoredGroups 对应的业务数据。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function getStoredGroups() {
  try {
    const stored = JSON.parse(localStorage.getItem('ongrid_nav_groups') || 'null')
    return Array.isArray(stored) ? stored.filter((item) => typeof item === 'string') : []
  } catch {
    return []
  }
}

const expandedGroups = ref<string[]>(getStoredGroups())
const expandedBranches = ref<string[]>([])

onMounted(() => {
  platform.loadPublic()
  document.addEventListener('click', closeThemeMenuOutside)
  document.addEventListener('keydown', closeMenusOnEscape)
})

watch(
  () => platform.name,
  (name) => {
    document.title = name || 'Ongrid'
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  document.removeEventListener('click', closeThemeMenuOutside)
  document.removeEventListener('keydown', closeMenusOnEscape)
})

watchEffect(() => {
  document.documentElement.dataset.theme = currentTheme.value.mode
  document.documentElement.dataset.palette = currentTheme.value.id
  localStorage.setItem('ongrid_theme', currentTheme.value.id)
})

const activeGroupName = computed(() => {
  const current = route.path
  return groups.value.find((group) => (group[1] as any[]).some((item) => isNavItemActive(item, current)))?.[0] as string | undefined
})

watch(
  () => route.path,
  () => {
    accountPanelOpen.value = false
    const active = activeGroupName.value || (groups.value[0]?.[0] as string | undefined)
    if (active && !expandedGroups.value.includes(active)) {
      expandedGroups.value = [...expandedGroups.value, active]
      saveExpandedGroups()
    }
  },
  { immediate: true },
)

/**
 * 切换主题选择菜单的显示状态。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function toggleThemeMenu() {
  themeMenuOpen.value = !themeMenuOpen.value
}

/**
 * 应用指定主题并关闭主题选择菜单。
 * 参数：`targetThemeId` 表示主题唯一标识。
 * 返回：无显式返回值。
 * 副作用：修改页面主题并通过监听器持久化选择。
 */
function selectTheme(targetThemeId: string) {
  if (!themeOptions.some((item) => item.id === targetThemeId)) return
  themeId.value = targetThemeId
  themeMenuOpen.value = false
}

/**
 * 在主题选择器之外点击时关闭菜单。
 * 参数：`event` 表示当前鼠标点击事件。
 * 返回：无显式返回值。
 * 副作用：可能关闭主题选择菜单。
 */
function closeThemeMenuOutside(event: MouseEvent) {
  if (themeMenuOpen.value && !themePickerRef.value?.contains(event.target as Node)) themeMenuOpen.value = false
  if (accountPanelOpen.value && !accountMenuRef.value?.contains(event.target as Node)) accountPanelOpen.value = false
}

/**
 * 使用键盘 Esc 关闭当前打开的主题或账户浮层。
 * 参数：`event` 表示键盘事件。
 * 返回：无显式返回值。
 * 副作用：可能关闭主题选择器和账户信息浮层。
 */
function closeMenusOnEscape(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  themeMenuOpen.value = false
  accountPanelOpen.value = false
}

/**
 * 切换当前用户账户信息浮层的显示状态。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：修改当前组件的账户浮层状态。
 */
function toggleAccountPanel() {
  accountPanelOpen.value = !accountPanelOpen.value
}

/**
 * 判断数据库根菜单是否需要作为无折叠层级的直达入口。
 * 参数：`group` 表示数据库导航转换后的根菜单。
 * 返回：总览菜单返回真，其他分组返回假。
 * 副作用：不修改状态。
 */
function isDirectGroup(group: any[]) {
  return group[2] === 'menu.overview'
}

/**
 * 返回根菜单配置的入口路由，并在缺失时使用首个可见页面。
 * 参数：`group` 表示数据库导航转换后的根菜单。
 * 返回：可供路由组件使用的入口路径。
 * 副作用：不修改状态。
 */
function directGroupPath(group: any[]) {
  return group[4] || group[1]?.[0]?.[0] || '/overview'
}

/**
 * 切换 toggleSidebarCollapsed 对应的界面或业务状态。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function toggleSidebarCollapsed() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem('ongrid_sidebar_collapsed', sidebarCollapsed.value ? '1' : '0')
}

/**
 * 校验当前输入并完成 saveExpandedGroups 对应的数据保存操作。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
function saveExpandedGroups() {
  localStorage.setItem('ongrid_nav_groups', JSON.stringify(expandedGroups.value))
}

/**
 * 判断 isGroupExpanded 对应的业务条件是否成立。
 * 参数：`name` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function isGroupExpanded(name: string) {
  return expandedGroups.value.includes(name)
}

/**
 * 切换 toggleGroup 对应的界面或业务状态。
 * 参数：`name` 表示菜单名称。
 * 返回：无显式返回值。
 * 副作用：只修改菜单展开状态，不触发子页面路由跳转。
 */
function toggleGroup(name: string) {
  expandedGroups.value = isGroupExpanded(name)
    ? expandedGroups.value.filter((item) => item !== name)
    : [...expandedGroups.value, name]
  saveExpandedGroups()
}

/**
 * 判断 isBranchExpanded 对应的业务条件是否成立。
 * 参数：`code` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function isBranchExpanded(code: string) {
  return expandedBranches.value.includes(code)
}

/**
 * 切换 toggleBranch 对应的界面或业务状态。
 * 参数：`code` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function toggleBranch(code: string) {
  expandedBranches.value = isBranchExpanded(code)
    ? expandedBranches.value.filter((item) => item !== code)
    : [...expandedBranches.value, code]
}

/**
 * 判断 isItemActive 对应的业务条件是否成立。
 * 参数：`path` 表示该步骤所需的业务参数；`currentPath` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function isItemActive(path: string, currentPath = route.path) {
  if (path === '/') return currentPath === '/'
  const plain = path.replace('/:id', '')
  const matches = pages
    .map(([candidate]) => candidate.replace('/:id', ''))
    .filter((candidate) => currentPath === candidate || currentPath.startsWith(`${candidate}/`))
  const longestMatch = matches.sort((left, right) => right.length - left.length)[0] || ''
  return plain === longestMatch
}

/**
 * 判断 isNavItemActive 对应的业务条件是否成立。
 * 参数：`item` 表示该步骤所需的业务参数；`currentPath` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function isNavItemActive(item: any[], currentPath = route.path): boolean {
  const paths = (item[4] as string[] | undefined)?.length ? item[4] as string[] : [item[0]]
  return paths.some((path) => isItemActive(path, currentPath)) || (item[5] || []).some((child: any[]) => isNavItemActive(child, currentPath))
}

/**
 * 计算并返回 firstAllowedItemPath 对应的业务数据。
 * 参数：`item` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function firstAllowedItemPath(item: any[]) {
  const paths = (item[4] as string[] | undefined)?.length ? item[4] as string[] : [item[0]]
  return paths.find((path) => hasAllPermissions(auth.user?.permissions, requiredPermissionsForPath(path))) || ''
}

/**
 * 封装 allowedNavItem 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`item` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function allowedNavItem(item: any[]): any[] | null {
  const children = ((item[5] || []) as any[]).map((child) => allowedNavItem(child)).filter(Boolean) as any[]
  const allowedPath = firstAllowedItemPath(item)
  if (!allowedPath && !children.length) return null
  return [allowedPath || children[0][0], item[1], item[2], item[3], item[4], children]
}

/**
 * 封装 logout 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：撤销服务端会话、清除本地令牌并跳转登录页。
 */
async function logout() {
  await auth.logout()
  await router.push('/login')
}
</script>

<template>
  <RouterView v-if="isPublic" />
  <div v-else class="app-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <SystemWatermark
      :config="platform.watermark"
      :username="auth.displayName"
      :platform-name="platform.name"
      :client-ip="platform.client_ip"
    />
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">
          <img v-if="platform.logo_url" :src="platform.logo_url" alt="" />
          <Gauge v-else :size="22" />
        </span>
        <div class="brand-text"><strong>{{ platform.name }}</strong><small>统一管理平台</small></div>
        <button class="sidebar-collapse-button" type="button" :title="sidebarCollapsed ? '展开菜单' : '折叠菜单'" @click="toggleSidebarCollapsed">
          <ChevronRight v-if="sidebarCollapsed" :size="16" />
          <ChevronLeft v-else :size="16" />
        </button>
      </div>
      <nav>
        <section v-for="group in groups" :key="group[0] as string" class="nav-group" :class="{ 'nav-group-direct': isDirectGroup(group) }">
          <RouterLink
            v-if="isDirectGroup(group)"
            :to="directGroupPath(group)"
            class="nav-group-toggle nav-group-link"
            :class="{ active: isNavItemActive((group[1] as any[])[0]) }"
            :title="group[0] as string"
          >
            <component :is="group[3] || Gauge" :size="16" />
            <span>{{ group[0] }}</span>
          </RouterLink>
          <button v-else class="nav-group-toggle" type="button" :title="group[0] as string" @click="toggleGroup(group[0] as string)">
            <component :is="group[3] || Gauge" :size="15" />
            <span>{{ group[0] }}</span>
            <ChevronDown v-if="isGroupExpanded(group[0] as string)" :size="14" />
            <ChevronRight v-else :size="14" />
          </button>
          <Transition name="nav-collapse">
            <div v-if="!isDirectGroup(group) && isGroupExpanded(group[0] as string)" class="nav-items">
              <div v-for="item in group[1] as any[]" :key="item[3]" class="nav-branch">
                <RouterLink
                  v-if="!item[5]?.length"
                  :to="item[0]"
                  class="nav-item"
                  :class="{ active: isNavItemActive(item) }"
                  :title="item[1]"
                >
                  <component :is="item[2]" :size="17" />
                  <span>{{ item[1] }}</span>
                </RouterLink>
                <div v-else class="nav-parent-row" :class="{ active: isNavItemActive(item) }">
                  <button
                    type="button"
                    class="nav-item nav-parent-item"
                    :class="{ active: isNavItemActive(item) }"
                    :title="item[1]"
                    @click="toggleBranch(item[3])"
                  >
                    <component :is="item[2]" :size="17" />
                    <span>{{ item[1] }}</span>
                  </button>
                  <button
                    class="nav-branch-toggle"
                    type="button"
                    :title="isBranchExpanded(item[3]) ? '收起' : '展开'"
                    :aria-expanded="isBranchExpanded(item[3])"
                    @click="toggleBranch(item[3])"
                  >
                    <ChevronDown v-if="isBranchExpanded(item[3])" :size="14" />
                    <ChevronRight v-else :size="14" />
                  </button>
                </div>
                <div v-if="item[5]?.length && isBranchExpanded(item[3])" class="nav-children">
                  <RouterLink
                    v-for="child in item[5]"
                    :key="child[3]"
                    :to="child[0]"
                    class="nav-item nav-child-item"
                    :class="{ active: isNavItemActive(child) }"
                    :title="child[1]"
                  >
                    <component :is="child[2]" :size="15" />
                    <span>{{ child[1] }}</span>
                  </RouterLink>
                </div>
              </div>
            </div>
          </Transition>
        </section>
      </nav>
      <div class="sidebar-footer">
        <div ref="accountMenuRef" class="account-menu">
          <Transition name="account-popover">
            <section v-if="accountPanelOpen" class="account-popover" role="dialog" aria-label="账户信息" @click.stop>
              <header class="account-popover-head">
                <span class="account-avatar"><UserRound :size="24" /></span>
                <div><strong>{{ accountFullName }}</strong><small>@{{ auth.displayName }}</small></div>
                <b :class="{ disabled: auth.user?.is_active === false }">{{ auth.user?.is_active === false ? '已停用' : '使用中' }}</b>
                <button type="button" title="关闭" aria-label="关闭账户信息" @click="accountPanelOpen = false"><X :size="16" /></button>
              </header>
              <dl class="account-details">
                <div><dt><BadgeCheck :size="15" />身份</dt><dd>{{ auth.role || '普通用户' }}</dd></div>
                <div><dt><Building2 :size="15" />所属部门</dt><dd>{{ auth.organization || '未分配' }}</dd></div>
                <div><dt><Mail :size="15" />邮箱</dt><dd :title="auth.user?.email || '未设置'">{{ auth.user?.email || '未设置' }}</dd></div>
                <div><dt><BriefcaseBusiness :size="15" />职位</dt><dd>{{ auth.user?.title || '未设置' }}</dd></div>
                <div><dt><Clock3 :size="15" />最近登录</dt><dd>{{ accountLastLogin }}</dd></div>
                <div><dt><ShieldCheck :size="15" />有效权限</dt><dd>{{ auth.user?.permissions?.includes('*') ? '全部权限' : `${accountPermissionCount} 项` }}</dd></div>
                <div><dt><KeyRound :size="15" />OTP 状态</dt><dd>{{ auth.user?.otp_status_label || (auth.user?.otp_bound ? '已绑定' : '未绑定') }}</dd></div>
              </dl>
            </section>
          </Transition>
          <div class="user-card" :class="{ active: accountPanelOpen }">
            <button class="user-card-profile" type="button" title="查看账户信息" :aria-expanded="accountPanelOpen" @click.stop="toggleAccountPanel">
              <CircleUserRound :size="27" />
              <span><strong>{{ auth.displayName }}</strong><small>{{ auth.role }} / {{ auth.organization }}</small></span>
            </button>
            <button class="user-card-logout" type="button" title="退出登录" @click.stop="logout"><LogOut :size="15" /></button>
          </div>
        </div>
      </div>
    </aside>
    <main>
      <header>
        <h1>{{ route.meta.title }}</h1>
        <div ref="themePickerRef" class="header-actions theme-picker" @keydown.esc="themeMenuOpen = false">
          <button
            class="icon-button theme-picker-trigger"
            type="button"
            title="切换界面主题"
            aria-label="切换界面主题"
            :aria-expanded="themeMenuOpen"
            @click.stop="toggleThemeMenu"
          >
            <Palette :size="18" />
          </button>
          <Transition name="theme-menu">
            <div v-if="themeMenuOpen" class="theme-picker-popover" role="dialog" aria-label="界面主题" @click.stop>
              <header class="theme-picker-head">
                <div><strong>界面主题</strong><small>选择后立即应用到所有页面</small></div>
                <span>{{ currentTheme.name }}</span>
              </header>
              <section class="theme-picker-group">
                <h2><Moon :size="14" /> 深色主题</h2>
                <div class="theme-option-grid">
                  <button
                    v-for="item in darkThemes"
                    :key="item.id"
                    type="button"
                    class="theme-option"
                    :class="{ active: themeId === item.id }"
                    :aria-pressed="themeId === item.id"
                    @click="selectTheme(item.id)"
                  >
                    <span class="theme-option-swatches" aria-hidden="true">
                      <i v-for="color in item.swatches" :key="color" :style="{ backgroundColor: color }"></i>
                    </span>
                    <span class="theme-option-copy"><strong>{{ item.name }}</strong><small>{{ item.description }}</small></span>
                    <Check v-if="themeId === item.id" :size="15" />
                  </button>
                </div>
              </section>
              <section class="theme-picker-group">
                <h2><Sun :size="14" /> 浅色主题</h2>
                <div class="theme-option-grid">
                  <button
                    v-for="item in lightThemes"
                    :key="item.id"
                    type="button"
                    class="theme-option"
                    :class="{ active: themeId === item.id }"
                    :aria-pressed="themeId === item.id"
                    @click="selectTheme(item.id)"
                  >
                    <span class="theme-option-swatches" aria-hidden="true">
                      <i v-for="color in item.swatches" :key="color" :style="{ backgroundColor: color }"></i>
                    </span>
                    <span class="theme-option-copy"><strong>{{ item.name }}</strong><small>{{ item.description }}</small></span>
                    <Check v-if="themeId === item.id" :size="15" />
                  </button>
                </div>
              </section>
            </div>
          </Transition>
        </div>
      </header>
      <div class="page"><RouterView /></div>
    </main>
  </div>
</template>
