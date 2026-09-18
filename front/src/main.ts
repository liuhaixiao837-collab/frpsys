import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { api } from './api'
import { hasAnyToken } from './authStorage'
import { configureNavigation, type ManifestGroup } from './navigation'
import { configurePermissions } from './permissions'
import { installColumnResizing } from './utils/columnResize'
import './styles.css'

/**
 * 加载数据库导航；失效的历史令牌清理后回退到匿名默认顺序。
 * 参数：无。
 * 返回：返回数据库导航接口载荷。
 * 副作用：可能请求后端，并在令牌失效时触发令牌清理流程。
 */
async function loadDatabaseNavigation() {
  const hadToken = hasAnyToken()
  try {
    return await api('/public/navigation')
  } catch (reason) {
    if (!hadToken || hasAnyToken()) throw reason
    return api('/public/navigation', { skipAuth: true })
  }
}

/**
 * 加载数据库导航并完成前端路由、权限状态和应用实例初始化。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
async function bootstrap() {
  const payload = await loadDatabaseNavigation()
  const groups = (payload.items || []) as ManifestGroup[]
  if (!groups.length) throw new Error('数据库中没有可用菜单')
  configureNavigation(groups)
  configurePermissions(groups)
  const { default: router } = await import('./router')
  createApp(App).use(createPinia()).use(router).mount('#app')
  installColumnResizing()
}

bootstrap().catch((reason) => {
  const root = document.querySelector<HTMLDivElement>('#app')
  if (root) root.textContent = reason?.message || '菜单加载失败'
})
