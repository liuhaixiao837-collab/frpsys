<script setup lang="ts">
import {
  AlertCircle, ArrowRight, BadgeCheck, Gauge, KeyRound, LoaderCircle,
  MessageSquareText, QrCode, RefreshCw, ShieldCheck, Smartphone, UserRound,
} from 'lucide-vue-next'
import QRCode from 'qrcode'
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api'
import PasswordInput from '../components/PasswordInput.vue'
import SliderCaptcha from '../components/SliderCaptcha.vue'
import { useAuthStore } from '../stores/auth'
import { usePlatformStore } from '../stores/platform'

type LoginStep = 'credentials' | 'otp_bind' | 'otp_setup' | 'otp_verify'
type LoginMode = 'password' | 'sms'

const auth = useAuthStore()
const platform = usePlatformStore()
const route = useRoute()
const username = ref('')
const password = ref('')
const phone = ref('')
const smsCode = ref('')
const smsChallengeToken = ref('')
const smsCountdown = ref(0)
const smsSending = ref(false)
let smsCountdownTimer: number | null = null
const captchaInput = ref('')
const captchaCode = ref('')
const captchaToken = ref('')
const sliderVerification = ref('')
const sliderCaptcha = ref<InstanceType<typeof SliderCaptcha> | null>(null)
const loading = ref(false)
const captchaLoading = ref(false)
const error = ref('')
const loginStep = ref<LoginStep>('credentials')
const loginMode = ref<LoginMode>('password')
const preauthToken = ref('')
const clientNonce = ref(createClientNonce())
const otpCredential = ref('')
const otpUri = ref('')
const qrCanvas = ref<HTMLCanvasElement | null>(null)
const forgotPasswordTarget = computed(() => ({
  path: '/forgot-password',
  query: username.value ? { username: username.value } : {},
}))

const submitLabel = computed(() => {
  if (loginStep.value === 'otp_verify') return '验证并登录'
  if (loginStep.value === 'otp_setup') return '确认绑定'
  return loginMode.value === 'sms' ? '短信验证' : '登录'
})
const loginTitle = computed(() => {
  if (loginStep.value !== 'credentials') return 'OTP 认证'
  return loginMode.value === 'sms' ? '短信登录' : '用户登录'
})
const smsSendLabel = computed(() => {
  if (smsSending.value) return '发送中'
  if (smsCountdown.value > 0) return `${smsCountdown.value}s`
  return smsChallengeToken.value ? '重新获取' : '获取验证码'
})

onMounted(async () => {
  username.value = String(route.query.username || '').trim()
  await platform.loadPublic()
  if (platform.captcha_enabled) await loadCaptcha()
})

onBeforeUnmount(() => {
  clearOtpTransient()
  clearSmsTransient()
  sliderCaptcha.value?.dispose()
})

/**
 * 生成仅当前登录页生命周期使用的浏览器会话随机值。
 * 参数：无。
 * 返回：至少 128 位随机强度的十六进制或 UUID 字符串。
 * 副作用：调用浏览器密码学安全随机源，不写入持久化存储。
 */
function createClientNonce() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = new Uint8Array(24)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')
}

/**
 * 从后端加载当前字符验证码。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：请求公开验证码接口并更新登录页临时状态。
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
 * 根据当前渐进认证步骤提交密码、OTP 验证或绑定确认。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：请求认证接口，成功时可能保存正式令牌并跳转业务首页。
 */
async function login() {
  if (loginStep.value === 'credentials' && loginMode.value === 'password') await loginWithCredentials()
  else if (loginStep.value === 'credentials') await loginWithSms()
  else if (loginStep.value === 'otp_verify') await verifyOtp()
  else if (loginStep.value === 'otp_setup') await confirmOtpBinding()
}

/**
 * 启动服务端有效期对应的短信验证码倒计时。
 * 参数：`seconds` 为服务端返回的剩余有效秒数。
 * 返回：无显式返回值。
 * 副作用：创建每秒更新一次页面状态的浏览器计时器；验证码到期后刷新下一次发送所需的字符和拖拽挑战。
 */
function startSmsCountdown(seconds: number) {
  if (smsCountdownTimer !== null) window.clearInterval(smsCountdownTimer)
  smsCountdown.value = Math.max(0, Math.min(30, Math.floor(seconds || 30)))
  smsCountdownTimer = window.setInterval(() => {
    smsCountdown.value = Math.max(0, smsCountdown.value - 1)
    if (smsCountdown.value === 0 && smsCountdownTimer !== null) {
      window.clearInterval(smsCountdownTimer)
      smsCountdownTimer = null
      captchaInput.value = ''
      captchaToken.value = ''
      sliderVerification.value = ''
      if (platform.captcha_enabled) void loadCaptcha()
      if (platform.slider_captcha_enabled) void nextTick(() => sliderCaptcha.value?.reset())
    }
  }, 1000)
}

/**
 * 完成反自动化校验并请求发送一次三十秒短信验证码。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：消费字符和拖拽验证码、调用短信接口；发送成功后保留两项验证状态至短信验证码到期。
 */
async function sendSmsCode() {
  if (!/^1[3-9]\d{9}$/.test(phone.value.trim())) {
    error.value = '请输入有效的中国大陆手机号'
    return
  }
  if (!captchaInput.value.trim()) {
    error.value = '请输入验证码'
    return
  }
  if (!sliderVerification.value) {
    error.value = '请完成图形拖拽验证'
    return
  }
  smsSending.value = true
  error.value = ''
  try {
    const result = await api('/auth/sms-login/send', {
      method: 'POST',
      body: JSON.stringify({
        phone: phone.value.trim(),
        captcha_token: captchaToken.value,
        captcha_code: captchaInput.value.trim(),
        slider_verification: sliderVerification.value,
        client_nonce: clientNonce.value,
      }),
      skipAuth: true,
    })
    smsChallengeToken.value = result.challenge_token || ''
    smsCode.value = ''
    startSmsCountdown(result.expires_in || 30)
  } catch (reason: any) {
    error.value = reason.message || '短信验证码发送失败'
    if (platform.captcha_enabled) await loadCaptcha()
    if (platform.slider_captcha_enabled) await nextTick(() => sliderCaptcha.value?.reset())
  } finally {
    smsSending.value = false
  }
}

/**
 * 提交一次性短信验证码并取得后续 OTP 预认证事务。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：消费短信挑战并切换到 OTP 验证页面。
 */
async function loginWithSms() {
  if (!smsChallengeToken.value || !/^\d{6}$/.test(smsCode.value.trim())) {
    error.value = '请获取并输入六位短信验证码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const result = await api('/auth/sms-login/verify', {
      method: 'POST',
      body: JSON.stringify({
        challenge_token: smsChallengeToken.value,
        code: smsCode.value.trim(),
        client_nonce: clientNonce.value,
      }),
      skipAuth: true,
    })
    preauthToken.value = result.preauth_token || ''
    loginStep.value = result.next_step
    clearSmsCountdown()
    sliderCaptcha.value?.dispose()
  } catch (reason: any) {
    error.value = reason.message || '短信验证码验证失败'
  } finally {
    loading.value = false
  }
}

/**
 * 在密码登录和短信登录之间安全切换。
 * 参数：无。
 * 返回：验证码重新加载完成后的 Promise。
 * 副作用：销毁旧挑战、更新浏览器随机值并重新请求验证码。
 */
async function toggleLoginMode() {
  loginMode.value = loginMode.value === 'password' ? 'sms' : 'password'
  clearSmsTransient()
  password.value = ''
  error.value = ''
  captchaInput.value = ''
  captchaToken.value = ''
  sliderVerification.value = ''
  clientNonce.value = createClientNonce()
  sliderCaptcha.value?.dispose()
  if (platform.captcha_enabled) await loadCaptcha()
  if (platform.slider_captcha_enabled) await nextTick(() => sliderCaptcha.value?.reset())
}

/**
 * 提交用户名、密码和已启用的验证码，获取正式登录结果或 OTP 预认证事务。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：消费验证码和拖拽凭证；完成全部认证时保存令牌并跳转。
 */
async function loginWithCredentials() {
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
    const result = await auth.login(
      username.value,
      password.value,
      captchaToken.value,
      captchaInput.value,
      sliderVerification.value,
      clientNonce.value,
    )
    if (result.next_step === 'complete') {
      navigateAfterLogin()
      return
    }
    preauthToken.value = result.preauth_token || ''
    loginStep.value = result.next_step
    password.value = ''
    captchaInput.value = ''
    captchaToken.value = ''
    sliderVerification.value = ''
    sliderCaptcha.value?.dispose()
  } catch (reason: any) {
    error.value = reason.message || '登录失败'
    if (platform.captcha_enabled) void loadCaptcha()
    if (platform.slider_captcha_enabled) void sliderCaptcha.value?.reset()
  } finally {
    loading.value = false
  }
}

/**
 * 使用预认证事务生成本次绑定专用二维码并切换到绑定确认步骤。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：请求 OTP 设置接口，并在本地 Canvas 中临时绘制二维码。
 */
async function startOtpBinding() {
  loading.value = true
  error.value = ''
  try {
    const result = await api('/auth/otp/setup', {
      method: 'POST',
      body: JSON.stringify({
        preauth_token: preauthToken.value,
        client_nonce: clientNonce.value,
      }),
      skipAuth: true,
    })
    otpUri.value = result.otpauth_uri || ''
    loginStep.value = 'otp_setup'
    await nextTick()
    await renderOtpQrCode()
  } catch (reason: any) {
    error.value = reason.message || 'OTP 绑定信息加载失败'
  } finally {
    loading.value = false
  }
}

/**
 * 将临时 otpauth 内容绘制到本地 Canvas，不生成或保存图片文件。
 * 参数：无。
 * 返回：二维码绘制完成后的 Promise。
 * 副作用：只修改浏览器内存中的 Canvas 像素。
 */
async function renderOtpQrCode() {
  if (!qrCanvas.value || !otpUri.value) return
  await QRCode.toCanvas(qrCanvas.value, otpUri.value, {
    width: 196,
    margin: 1,
    color: { dark: '#0f172a', light: '#f8fafc' },
    errorCorrectionLevel: 'M',
  })
}

/**
 * 提交令牌应用显示的首个动态口令并完成 OTP 绑定。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：加密保存 OTP 种子、保存正式令牌并跳转业务首页。
 */
async function confirmOtpBinding() {
  if (!/^\d{6}$/.test(otpCredential.value.trim())) {
    error.value = '请输入六位动态口令'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.completeOtp('/auth/otp/confirm', {
      preauth_token: preauthToken.value,
      client_nonce: clientNonce.value,
      code: otpCredential.value.trim(),
    })
    navigateAfterLogin()
  } catch (reason: any) {
    error.value = reason.message || 'OTP 绑定失败'
  } finally {
    loading.value = false
  }
}

/**
 * 提交已绑定用户的六位动态口令并完成登录。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：消费 TOTP 时间步，保存正式令牌并跳转业务首页。
 */
async function verifyOtp() {
  if (!/^\d{6}$/.test(otpCredential.value.trim())) {
    error.value = '请输入六位动态口令'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.completeOtp('/auth/otp/verify', {
      preauth_token: preauthToken.value,
      client_nonce: clientNonce.value,
      credential: otpCredential.value.trim(),
    })
    navigateAfterLogin()
  } catch (reason: any) {
    error.value = reason.message || 'OTP 验证失败'
  } finally {
    loading.value = false
  }
}

/**
 * 放弃失效或未完成的 OTP 事务并返回完整登录表单。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：清除二维码和认证事务，并重新加载验证码与拖拽挑战。
 */
async function restartLogin() {
  clearOtpTransient()
  clearSmsTransient()
  loginStep.value = 'credentials'
  preauthToken.value = ''
  clientNonce.value = createClientNonce()
  password.value = ''
  error.value = ''
  if (platform.captcha_enabled) await loadCaptcha()
  if (platform.slider_captcha_enabled) await nextTick(() => sliderCaptcha.value?.reset())
}

/**
 * 停止短信验证码倒计时但保留其他输入状态。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：清理浏览器计时器并把剩余秒数归零。
 */
function clearSmsCountdown() {
  if (smsCountdownTimer !== null) window.clearInterval(smsCountdownTimer)
  smsCountdownTimer = null
  smsCountdown.value = 0
}

/**
 * 清除当前页面持有的短信挑战、验证码和计时器。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：使当前浏览器不再持有可提交的短信登录数据。
 */
function clearSmsTransient() {
  clearSmsCountdown()
  smsChallengeToken.value = ''
  smsCode.value = ''
}

/**
 * 清空二维码 Canvas 像素，避免绑定内容在组件状态中残留。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：清除当前 Canvas 的全部像素。
 */
function clearQrCanvas() {
  const canvas = qrCanvas.value
  canvas?.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height)
}

/**
 * 清除登录页全部 OTP 临时数据。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：清空 Canvas、动态口令和二维码内容。
 */
function clearOtpTransient() {
  clearQrCanvas()
  otpUri.value = ''
  otpCredential.value = ''
}

/**
 * 完成登录后的安全清理并重新加载应用，使数据库导航应用个人顺序。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：清理验证码和 OTP 临时数据，然后导航到平台用户管理入口。
 */
function navigateAfterLogin() {
  sliderCaptcha.value?.dispose()
  clearOtpTransient()
  clearSmsTransient()
  window.location.assign('/admin/users')
}
</script>

<template>
  <div class="login">
    <div class="login-shell">
      <div class="login-brand">
        <span class="login-logo">
          <img v-if="platform.logo_url" :src="platform.logo_url" alt="" />
          <Gauge v-else :size="34" />
        </span>
        <div><h1>{{ platform.name }}</h1></div>
      </div>

      <form class="login-card" @submit.prevent="login">
        <div class="login-card-head">
          <h2>{{ loginTitle }}</h2>
          <button v-if="loginStep === 'credentials' && platform.sms_login_enabled" class="login-mode-switch" type="button" @click="toggleLoginMode">
            <MessageSquareText v-if="loginMode === 'password'" :size="15" />
            <ShieldCheck v-else :size="15" />
            {{ loginMode === 'password' ? '短信登录' : '密码登录' }}
          </button>
        </div>

        <template v-if="loginStep === 'credentials'">
          <label v-if="loginMode === 'password'" class="login-field">
            <span>用户名</span>
            <div><UserRound :size="18" /><input v-model.trim="username" autocomplete="username" spellcheck="false" placeholder="请输入用户名" /></div>
          </label>
          <label v-if="loginMode === 'password'" class="login-field">
            <span class="login-field-heading"><span>密码</span><RouterLink :to="forgotPasswordTarget">忘记密码？</RouterLink></span>
            <div class="login-password-control">
              <ShieldCheck :size="18" />
              <PasswordInput v-model="password" autocomplete="current-password" placeholder="请输入密码" />
            </div>
          </label>
          <label v-else class="login-field">
            <span>手机号</span>
            <div><Smartphone :size="18" /><input v-model.trim="phone" inputmode="tel" autocomplete="tel" maxlength="11" placeholder="请输入绑定手机号" /></div>
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
          <label v-if="loginMode === 'sms'" class="login-field">
            <span>短信验证码</span>
            <div class="sms-code-control">
              <MessageSquareText :size="18" />
              <input v-model.trim="smsCode" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="请输入 6 位短信验证码" />
              <button type="button" :disabled="smsSending || smsCountdown > 0 || !captchaInput || !sliderVerification" @click="sendSmsCode">{{ smsSendLabel }}</button>
            </div>
            <small v-if="smsChallengeToken" class="sms-code-hint">验证码发送后 30 秒内有效，过期后请重新获取。</small>
          </label>
        </template>

        <section v-else-if="loginStep === 'otp_bind'" class="login-otp-panel otp-bind-panel">
          <span class="login-otp-icon"><QrCode :size="24" /></span>
          <div><strong>尚未绑定动态令牌</strong><p>请使用腾讯令牌小程序或 Google Authenticator 扫码绑定。</p></div>
          <button class="primary otp-bind-button" type="button" :disabled="loading" @click="startOtpBinding"><KeyRound :size="16" />绑定令牌</button>
        </section>

        <section v-else-if="loginStep === 'otp_setup'" class="login-otp-panel otp-setup-panel">
          <div class="otp-qr-frame"><canvas ref="qrCanvas" width="196" height="196" aria-label="OTP 绑定二维码" /></div>
          <p>扫码后输入令牌应用显示的六位动态口令。</p>
          <label class="login-field">
            <span>动态令牌</span>
            <div><KeyRound :size="18" /><input v-model.trim="otpCredential" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="请输入 6 位口令" /></div>
          </label>
        </section>

        <section v-else-if="loginStep === 'otp_verify'" class="login-otp-panel otp-verify-panel">
          <span class="login-otp-icon"><KeyRound :size="24" /></span>
          <div class="otp-bound-summary"><strong>动态令牌已绑定</strong><b class="badge healthy">已绑定</b></div>
          <label class="login-field">
            <span>动态令牌</span>
            <div><KeyRound :size="18" /><input v-model.trim="otpCredential" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="请输入 6 位动态令牌" /></div>
          </label>
        </section>

        <p v-if="error" class="login-error"><AlertCircle :size="16" />{{ error }}</p>
        <button
          v-if="loginStep !== 'otp_bind'"
          class="login-button"
          :disabled="loading || (loginStep === 'credentials' && loginMode === 'password' && platform.slider_captcha_enabled && !sliderVerification) || (loginStep === 'credentials' && loginMode === 'sms' && (!smsChallengeToken || !/^\d{6}$/.test(smsCode)))"
        >
          <LoaderCircle v-if="loading" :size="16" class="spin" />
          <template v-if="loading">处理中</template>
          <template v-else>{{ submitLabel }} <ArrowRight :size="16" /></template>
        </button>
        <button v-if="loginStep !== 'credentials'" class="otp-restart-button" type="button" :disabled="loading" @click="restartLogin">返回重新登录</button>
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
