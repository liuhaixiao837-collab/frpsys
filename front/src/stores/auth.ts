import { defineStore } from 'pinia'
import { api } from '../api'
import { clearTokens, getAccessToken, hasAnyToken, setTokens } from '../authStorage'

type CurrentUser = {
  id: number
  username: string
  email: string
  first_name?: string
  last_name?: string
  is_active?: boolean
  title?: string
  last_login?: string | null
  date_joined?: string | null
  otp_bound?: boolean
  otp_status_label?: string
  role: string
  role_name?: string
  organization: string
  department?: string
  permissions?: string[]
}

type LoginResult = {
  next_step: 'complete' | 'otp_bind' | 'otp_verify'
  access?: string
  refresh?: string
  user?: CurrentUser
  preauth_token?: string
  expires_in?: number
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as CurrentUser | null,
    loading: false,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.user || getAccessToken() || hasAnyToken()),
    displayName: (state) => state.user?.username || '未登录',
    role: (state) => state.user?.role_name || state.user?.role || '',
    organization: (state) => state.user?.department || state.user?.organization || '',
    can: (state) => (code: string) => {
      if (!code) return true
      if (state.user?.username === 'admin') return true
      const permissions = state.user?.permissions || []
      return permissions.includes('*') || permissions.includes(code)
    },
    canAny: (state) => (codes: string[]) => codes.some((code) => {
      if (state.user?.username === 'admin') return true
      const permissions = state.user?.permissions || []
      return permissions.includes('*') || permissions.includes(code)
    }),
  },
  actions: {
        /**
     * 封装 login 对应的前端业务处理步骤，供当前模块统一调用。
     * 参数：`username`、`password` 为登录凭据；`captchaToken`、`captchaCode` 为字符验证码；`sliderVerification` 为拖拽凭证；`clientNonce` 为浏览器会话随机值。
     * 返回：正式登录结果或下一步 OTP 预认证事务。
     * 副作用：请求后端；无需 OTP 时会保存正式令牌。
     */
async login(username: string, password: string, captchaToken = '', captchaCode = '', sliderVerification = '', clientNonce = '') {
      this.loading = true
      try {
        const result = await api('/auth/login', {
          method: 'POST',
          body: JSON.stringify({
            username,
            password,
            captcha_token: captchaToken,
            captcha_code: captchaCode,
            slider_verification: sliderVerification,
            client_nonce: clientNonce,
          }),
          skipAuth: true,
        })
        if (result.next_step === 'complete') this.acceptLogin(result)
        return result as LoginResult
      } finally {
        this.loading = false
      }
    },
    /**
     * 保存完成全部认证步骤后的正式登录结果。
     * 参数：`result` 为包含正式访问令牌、刷新令牌和用户信息的响应。
     * 返回：无显式返回值。
     * 副作用：把正式令牌写入浏览器存储并更新当前用户状态。
     */
    acceptLogin(result: LoginResult) {
      if (!result.access || !result.user) throw new Error('登录结果缺少正式令牌')
      setTokens(result.access, result.refresh)
      this.user = result.user
    },
    /**
     * 提交 OTP 绑定确认或登录验证请求。
     * 参数：`path` 为 OTP 接口路径；`payload` 为预认证事务和用户输入；`persist` 控制是否立即保存正式令牌。
     * 返回：后端 OTP 处理结果。
     * 副作用：请求后端；`persist` 为真且认证完成时写入浏览器令牌存储。
     */
    async completeOtp(path: string, payload: Record<string, unknown>, persist = true) {
      this.loading = true
      try {
        const result = await api(path, {
          method: 'POST',
          body: JSON.stringify(payload),
          skipAuth: true,
        }) as LoginResult
        if (persist && result.next_step === 'complete') this.acceptLogin(result)
        return result
      } finally {
        this.loading = false
      }
    },
        /**
     * 从后端或当前状态加载 loadMe 所需的最新业务数据。
     * 参数：无。
     * 返回：返回该步骤计算、查询或校验后的结果。
     * 副作用：可能请求后端、修改持久化数据或更新全局状态。
     */
async loadMe() {
      if (!hasAnyToken()) return false
      this.loading = true
      try {
        this.user = await api('/me')
        return true
      } catch {
        clearTokens()
        this.user = null
        return false
      } finally {
        this.loading = false
      }
    },
    /**
     * 撤销服务端平台会话并清除本地令牌。
     * 参数：无。
     * 返回：无显式返回值。
     * 副作用：请求退出接口，并始终清除浏览器令牌和当前用户状态。
     */
    async logout() {
      try {
        await api('/auth/logout', { method: 'POST' })
      } finally {
        clearTokens()
        this.user = null
      }
    },
  },
})
