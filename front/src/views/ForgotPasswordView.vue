<script setup lang="ts">
import {
  AlertCircle, ArrowLeft, ArrowRight, BadgeCheck, Check, CheckCircle2, Gauge,
  KeyRound, LoaderCircle, LockKeyhole, RefreshCw, RotateCcw, ShieldCheck, UserRound,
} from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api'
import PasswordInput from '../components/PasswordInput.vue'
import SliderCaptcha from '../components/SliderCaptcha.vue'
import { usePlatformStore } from '../stores/platform'

type ResetStep = 'account' | 'otp' | 'password' | 'complete'

const platform = usePlatformStore()
const route = useRoute()
const router = useRouter()
const sliderCaptcha = ref<InstanceType<typeof SliderCaptcha> | null>(null)
const username = ref(String(route.query.username || '').trim())
const captchaInput = ref('')
const captchaCode = ref('')
const captchaToken = ref('')
const sliderVerification = ref('')
const clientNonce = ref(createClientNonce())
const resetToken = ref('')
const passwordToken = ref('')
const otpCredential = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const passwordPolicy = ref({
  min_length: 8,
  require_uppercase: true,
  require_lowercase: true,
  require_number: true,
  require_special: true,
  exclude_username: true,
})
const step = ref<ResetStep>('account')
const loading = ref(false)
const captchaLoading = ref(false)
const error = ref('')
const redirectSeconds = ref(3)
let redirectTimer: number | undefined

const steps = [
  { key: 'account', label: '验证账号', icon: UserRound },
  { key: 'otp', label: '验证令牌', icon: KeyRound },
  { key: 'password', label: '设置密码', icon: LockKeyhole },
  { key: 'complete', label: '完成', icon: CheckCircle2 },
] as const
const activeStepIndex = computed(() => steps.findIndex((item) => item.key === step.value))
const passwordRules = computed(() => [
  { label: `至少 ${passwordPolicy.value.min_length} 位`, visible: true, passed: newPassword.value.length >= passwordPolicy.value.min_length },
  { label: '包含大写字母', visible: passwordPolicy.value.require_uppercase, passed: /[A-Z]/.test(newPassword.value) },
  { label: '包含小写字母', visible: passwordPolicy.value.require_lowercase, passed: /[a-z]/.test(newPassword.value) },
  { label: '包含数字', visible: passwordPolicy.value.require_number, passed: /\d/.test(newPassword.value) },
  { label: '包含特殊字符', visible: passwordPolicy.value.require_special, passed: /[^\p{L}\p{N}]/u.test(newPassword.value) },
  {
    label: '不能包含用户名',
    visible: passwordPolicy.value.exclude_username,
    passed: Boolean(newPassword.value) && !newPassword.value.toLowerCase().includes(username.value.toLowerCase()),
  },
].filter((rule) => rule.visible))

onMounted(async () => {
  await platform.loadPublic()
  if (platform.captcha_enabled) await loadCaptcha()
})

onBeforeUnmount(() => {
  sliderCaptcha.value?.dispose()
  if (redirectTimer) window.clearInterval(redirectTimer)
})

/**
 * 生成只绑定当前找回页面生命周期的浏览器会话随机值。
 * 参数：无。
 * 返回：密码学安全的 UUID 或 192 位十六进制随机字符串。
 * 副作用：调用浏览器安全随机源，不写入持久化存储。
 */
function createClientNonce() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = new Uint8Array(24)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
}

/**
 * 从后端加载当前字符验证码并清空旧输入。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：请求公开验证码接口并更新页面临时状态。
 */
async function loadCaptcha() {
  if (!platform.captcha_enabled) return
  captchaLoading.value = true
  try {
    const result = await api('/auth/captcha', { skipAuth: true })
    captchaCode.value = result.code || ''
    captchaToken.value = result.token || ''
    captchaInput.value = ''
  } catch (reason: any) {
    error.value = reason.message || '验证码加载失败'
  } finally {
    captchaLoading.value = false
  }
}

/**
 * 根据当前步骤提交账号验证、OTP 或新密码。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：调用对应公开接口并推进找回流程。
 */
async function submit() {
  if (step.value === 'account') await submitAccount()
  else if (step.value === 'otp') await submitOtp()
  else if (step.value === 'password') await submitPassword()
}

/**
 * 提交账号和已启用的反自动化凭证以开始匿名找回事务。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：消费验证码或拖拽凭证并保存短期找回令牌。
 */
async function submitAccount() {
  if (!username.value.trim()) {
    error.value = '请输入需要找回的用户名'
    return
  }
  if (platform.captcha_enabled && !captchaInput.value.trim()) {
    error.value = '请输入验证码'
    return
  }
  if (platform.slider_captcha_enabled && !sliderVerification.value) {
    error.value = '请完成图形拖拽验证'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const result = await api('/auth/password-reset/start', {
      method: 'POST',
      body: JSON.stringify({
        username: username.value.trim(),
        captcha_token: captchaToken.value,
        captcha_code: captchaInput.value,
        slider_verification: sliderVerification.value,
        client_nonce: clientNonce.value,
      }),
      skipAuth: true,
    })
    resetToken.value = result.reset_token || ''
    step.value = 'otp'
    captchaInput.value = ''
    captchaToken.value = ''
    sliderVerification.value = ''
    sliderCaptcha.value?.dispose()
  } catch (reason: any) {
    error.value = reason.message || '账号验证失败'
    if (platform.captcha_enabled) void loadCaptcha()
    if (platform.slider_captcha_enabled) void sliderCaptcha.value?.reset()
  } finally {
    loading.value = false
  }
}

/**
 * 提交六位动态令牌并换取一次性改密资格。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：消费一个 TOTP 时间步并更新服务端 OTP 锁定状态。
 */
async function submitOtp() {
  const credential = otpCredential.value.trim()
  if (!/^\d{6}$/.test(credential)) {
    error.value = '请输入 6 位动态令牌'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const result = await api('/auth/password-reset/verify-otp', {
      method: 'POST',
      body: JSON.stringify({
        reset_token: resetToken.value,
        client_nonce: clientNonce.value,
        credential,
      }),
      skipAuth: true,
    })
    passwordToken.value = result.password_token || ''
    passwordPolicy.value = { ...passwordPolicy.value, ...(result.password_policy || {}) }
    resetToken.value = ''
    otpCredential.value = ''
    step.value = 'password'
  } catch (reason: any) {
    error.value = reason.message || '动态令牌验证失败'
  } finally {
    loading.value = false
  }
}

/**
 * 提交两次新密码并完成一次性改密事务。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：成功时更新服务端密码、撤销旧会话并启动登录页倒计时。
 */
async function submitPassword() {
  if (!newPassword.value) {
    error.value = '请输入新密码'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const result = await api('/auth/password-reset/complete', {
      method: 'POST',
      body: JSON.stringify({
        password_token: passwordToken.value,
        client_nonce: clientNonce.value,
        new_password: newPassword.value,
        confirm_password: confirmPassword.value,
      }),
      skipAuth: true,
    })
    username.value = result.username || username.value
    passwordToken.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    step.value = 'complete'
    startRedirectCountdown()
  } catch (reason: any) {
    error.value = reason.message || '密码更新失败'
  } finally {
    loading.value = false
  }
}

/**
 * 清理当前事务并返回账号验证步骤。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：清空页面内的敏感临时值并重新加载反自动化验证。
 */
async function restart() {
  resetToken.value = ''
  passwordToken.value = ''
  otpCredential.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  clientNonce.value = createClientNonce()
  error.value = ''
  step.value = 'account'
  if (platform.captcha_enabled) await loadCaptcha()
  if (platform.slider_captcha_enabled) await nextTick(() => sliderCaptcha.value?.reset())
}

/**
 * 启动完成页自动返回登录页的三秒倒计时。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：创建每秒定时器并在结束时执行前端路由跳转。
 */
function startRedirectCountdown() {
  redirectSeconds.value = 3
  if (redirectTimer) window.clearInterval(redirectTimer)
  redirectTimer = window.setInterval(() => {
    redirectSeconds.value -= 1
    if (redirectSeconds.value <= 0) goToLogin()
  }, 1000)
}

/**
 * 返回登录页并仅通过查询参数预填用户名。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：清理倒计时并替换当前浏览器路由。
 */
function goToLogin() {
  if (redirectTimer) window.clearInterval(redirectTimer)
  redirectTimer = undefined
  router.replace({ path: '/login', query: username.value ? { username: username.value } : {} })
}
</script>

<template>
  <div class="login forgot-password-page">
    <div class="login-shell forgot-password-shell">
      <div class="login-brand forgot-password-brand">
        <span class="login-logo">
          <img v-if="platform.logo_url" :src="platform.logo_url" alt="" />
          <Gauge v-else :size="34" />
        </span>
        <div><h1>{{ platform.name }}</h1><small>统一管理平台</small></div>
      </div>

      <form class="login-card forgot-password-card" @submit.prevent="submit">
        <header class="forgot-password-head">
          <div><span>账号安全中心</span><h2>找回密码</h2></div>
          <span class="forgot-security-badge"><ShieldCheck :size="15" /> 安全验证</span>
        </header>

        <ol class="forgot-stepper" aria-label="找回密码进度">
          <li v-for="(item, index) in steps" :key="item.key" :class="{ active: index === activeStepIndex, complete: index < activeStepIndex }">
            <span class="forgot-step-icon"><Check v-if="index < activeStepIndex" :size="15" /><component :is="item.icon" v-else :size="15" /></span>
            <span><b>0{{ index + 1 }}</b><strong>{{ item.label }}</strong></span>
          </li>
        </ol>

        <section class="forgot-password-content">
          <template v-if="step === 'account'">
            <div class="forgot-section-title"><strong>确认登录账号</strong><span>请输入需要找回密码的用户名</span></div>
            <label class="login-field">
              <span>用户名</span>
              <div><UserRound :size="18" /><input v-model.trim="username" autocomplete="username" spellcheck="false" placeholder="请输入用户名" /></div>
            </label>
            <label v-if="platform.captcha_enabled" class="login-field">
              <span>验证码</span>
              <div class="captcha-row">
                <span class="captcha-input"><BadgeCheck :size="18" /><input v-model.trim="captchaInput" autocomplete="off" spellcheck="false" placeholder="请输入验证码" maxlength="4" /></span>
                <button class="captcha-code" type="button" title="刷新验证码" :disabled="captchaLoading" @click="loadCaptcha">
                  <strong>{{ captchaLoading ? '----' : captchaCode }}</strong><RefreshCw :size="15" :class="{ spin: captchaLoading }" />
                </button>
              </div>
            </label>
            <SliderCaptcha v-if="platform.slider_captcha_enabled" ref="sliderCaptcha" @verified="sliderVerification = $event" />
          </template>

          <template v-else-if="step === 'otp'">
            <div class="forgot-section-title"><strong>验证动态令牌</strong><span>输入令牌应用当前显示的 6 位口令</span></div>
            <div class="forgot-account-summary"><UserRound :size="17" /><span><small>当前账号</small><strong>{{ username }}</strong></span><BadgeCheck :size="18" /></div>
            <label class="login-field">
              <span>动态令牌</span>
              <div><KeyRound :size="18" /><input v-model.trim="otpCredential" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="请输入 6 位动态令牌" /></div>
            </label>
            <p class="forgot-security-note"><ShieldCheck :size="16" />本流程仅接受已绑定的 6 位动态令牌。</p>
          </template>

          <template v-else-if="step === 'password'">
            <div class="forgot-section-title"><strong>设置新密码</strong><span>新密码将按平台安全策略实时校验</span></div>
            <label class="login-field">
              <span>新密码</span>
              <div class="login-password-control"><LockKeyhole :size="18" /><PasswordInput v-model="newPassword" autocomplete="new-password" placeholder="请输入新密码" /></div>
            </label>
            <ul class="forgot-password-rules" aria-label="密码安全要求">
              <li v-for="rule in passwordRules" :key="rule.label" :class="{ passed: rule.passed }"><CheckCircle2 :size="14" />{{ rule.label }}</li>
            </ul>
            <label class="login-field">
              <span>确认新密码</span>
              <div class="login-password-control"><ShieldCheck :size="18" /><PasswordInput v-model="confirmPassword" autocomplete="new-password" placeholder="请再次输入新密码" /></div>
            </label>
            <p class="forgot-security-note"><ShieldCheck :size="16" />密码更新后，当前账号已签发的会话将全部失效。</p>
          </template>

          <template v-else>
            <div class="forgot-complete-state">
              <span><CheckCircle2 :size="34" /></span>
              <strong>密码修改完成</strong>
              <p>请使用新密码重新登录系统</p>
              <small>{{ redirectSeconds }} 秒后自动返回登录页</small>
              <button class="login-button" type="button" @click="goToLogin">返回登录 <ArrowRight :size="16" /></button>
            </div>
          </template>

          <p v-if="error" class="login-error"><AlertCircle :size="16" />{{ error }}</p>
          <div v-if="step !== 'complete'" class="forgot-actions">
            <RouterLink v-if="step === 'account'" class="forgot-back-button" :to="{ path: '/login', query: username ? { username } : {} }"><ArrowLeft :size="16" /> 返回登录</RouterLink>
            <button v-else class="forgot-back-button" type="button" :disabled="loading" @click="restart"><RotateCcw :size="15" /> 重新开始</button>
            <button class="login-button" :disabled="loading || (step === 'account' && platform.slider_captcha_enabled && !sliderVerification)">
              <LoaderCircle v-if="loading" :size="16" class="spin" />
              <template v-if="loading">处理中</template>
              <template v-else>{{ step === 'password' ? '确认修改' : '继续' }} <ArrowRight :size="16" /></template>
            </button>
          </div>
        </section>
      </form>

      <footer class="login-footer">
        <div class="login-filing-line">
          <span>{{ platform.name }}</span>
          <template v-if="platform.icp_record">
            <span aria-hidden="true">|</span><span>ICP备案号：</span>
            <a v-if="platform.icp_url" :href="platform.icp_url" target="_blank" rel="noopener noreferrer">{{ platform.icp_record }}</a>
            <span v-else>{{ platform.icp_record }}</span>
          </template>
          <a v-if="platform.public_security_record && platform.public_security_url" class="login-public-security" :href="platform.public_security_url" target="_blank" rel="noopener noreferrer">
            <img src="/assets/brand/public-security-badge.png" alt="" />{{ platform.public_security_record }}
          </a>
          <span v-else-if="platform.public_security_record" class="login-public-security"><img src="/assets/brand/public-security-badge.png" alt="" />{{ platform.public_security_record }}</span>
        </div>
      </footer>
    </div>
  </div>
</template>
