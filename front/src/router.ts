import { createRouter, createWebHistory } from 'vue-router'

import { navigationGroups, pages } from './navigation'
import { hasAllPermissions, requiredPermissionsForPath } from './permissions'
import { useAuthStore } from './stores/auth'


/**
 * 计算并返回 firstAllowedPath 对应的业务数据。
 * 参数：`permissions` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function firstAllowedPath(permissions?: string[]) {
  for (const group of navigationGroups) {
    for (const item of group[1] as any[]) {
      const paths = Array.isArray(item[4]) && item[4].length ? item[4] : [item[0]]
      const allowedPath = paths.find((path: string) => (
        hasAllPermissions(permissions, requiredPermissionsForPath(path))
      ))
      if (allowedPath) return allowedPath
    }
  }
  return ''
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/login' },
    {
      path: '/login',
      component: () => import('./views/LoginView.vue'),
      meta: { public: true, title: '登录' },
    },
    {
      path: '/forgot-password',
      component: () => import('./views/ForgotPasswordView.vue'),
      meta: { public: true, title: '找回密码' },
    },
    ...pages.map(([path, title]) => ({
      path,
      component: () => import('./views/WorkbenchView.vue'),
      meta: { title },
    })),
    {
      path: '/:pathMatch(.*)*',
      component: () => import('./views/NotFoundView.vue'),
      meta: { public: true, title: '页面不存在' },
    },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  const auth = useAuthStore()
  if (!auth.user && !await auth.loadMe()) return '/login'
  const required = requiredPermissionsForPath(to.path)
  if (!required.length || hasAllPermissions(auth.user?.permissions, required)) return true
  return firstAllowedPath(auth.user?.permissions) || false
})

export default router
