import { defineStore } from 'pinia'
import { api } from '../api'
import { localAssetUrl } from '../utils/localAssets'
import { setPlatformTimezone } from '../utils/dateTime'

export type WatermarkSettings = {
  enabled: boolean
  content_type: 'username' | 'username_ip' | 'platform' | 'custom'
  custom_text: string
  layout: 'tiled' | 'center'
  show_time: boolean
  font_size: number
  font_weight: 400 | 500 | 600
  color: string
  opacity: number
  rotate: number
  horizontal_gap: number
  vertical_gap: number
}

type PlatformBranding = {
  name: string
  logo_url: string
  icp_record: string
  icp_url: string
  public_security_record: string
  public_security_url: string
  captcha_enabled: boolean
  slider_captcha_enabled: boolean
  otp_enabled: boolean
  sms_login_enabled: boolean
  timezone: string
  watermark?: Partial<WatermarkSettings>
  client_ip?: string
}

const defaultWatermark: WatermarkSettings = {
  enabled: false,
  content_type: 'username_ip',
  custom_text: '',
  layout: 'tiled',
  show_time: true,
  font_size: 14,
  font_weight: 500,
  color: '#64748b',
  opacity: 0.14,
  rotate: -24,
  horizontal_gap: 220,
  vertical_gap: 140,
}

export const usePlatformStore = defineStore('platform', {
  state: () => ({
    name: 'Ongrid',
    logo_url: '',
    icp_record: '',
    icp_url: '',
    public_security_record: '',
    public_security_url: '',
    captcha_enabled: true,
    slider_captcha_enabled: true,
    otp_enabled: false,
    sms_login_enabled: false,
    timezone: 'Asia/Shanghai',
    watermark: { ...defaultWatermark } as WatermarkSettings,
    client_ip: '',
    loaded: false,
    loading: false,
  }),
  actions: {
        /**
     * 从后端或当前状态加载 loadPublic 所需的最新业务数据。
     * 参数：`force` 表示该步骤所需的业务参数。
     * 返回：无显式返回值。
     * 副作用：可能请求后端、修改持久化数据或更新全局状态。
     */
async loadPublic(force = false) {
      if (this.loading || (this.loaded && !force)) return
      this.loading = true
      try {
        const result = await api('/public/platform', { skipAuth: true }) as PlatformBranding
        this.name = result.name || 'Ongrid'
        this.logo_url = localAssetUrl(result.logo_url)
        this.icp_record = result.icp_record || ''
        this.icp_url = result.icp_url || ''
        this.public_security_record = result.public_security_record || ''
        this.public_security_url = result.public_security_url || ''
        this.captcha_enabled = result.captcha_enabled !== false
        this.slider_captcha_enabled = result.slider_captcha_enabled === true
        this.otp_enabled = result.otp_enabled === true
        this.sms_login_enabled = result.sms_login_enabled === true
        this.timezone = result.timezone || 'Asia/Shanghai'
        this.watermark = { ...defaultWatermark, ...(result.watermark || {}) }
        this.client_ip = result.client_ip || ''
        setPlatformTimezone(this.timezone)
        this.loaded = true
      } catch {
        this.loaded = true
      } finally {
        this.loading = false
      }
    },
  },
})
