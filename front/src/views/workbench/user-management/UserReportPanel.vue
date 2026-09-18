<script setup lang="ts">
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'
import {
  Building2, CircleOff, Download, FileCode2, FileImage, FileText, KeyRound, RefreshCw,
  ShieldCheck, ShieldX, UserCheck, UsersRound, UserX,
} from 'lucide-vue-next'
import { computed, nextTick, onMounted, ref } from 'vue'

import { api } from '../../../api'
import EChart from '../../../components/EChart.vue'
import ModalDialog from '../../../components/ModalDialog.vue'
import { actionPermissionForPath } from '../../../permissions'
import { useAuthStore } from '../../../stores/auth'

type DistributionItem = { name: string; value: number }
type TrendItem = { date: string; value: number }
type UserReportPayload = {
  summary: {
    total_users: number
    active_users: number
    disabled_users: number
    department_count: number
    otp_bound: number
    otp_unbound: number
  }
  department_distribution: DistributionItem[]
  otp_distribution: DistributionItem[]
  status_distribution: DistributionItem[]
  registration_trend: TrendItem[]
  permission_statistics: {
    summary: {
      total_policies: number
      available_policies: number
      disabled_policies: number
      department_policies: number
      user_policies: number
      allowed_rules: number
      denied_rules: number
    }
    status_distribution: DistributionItem[]
    authorization_mode_distribution: DistributionItem[]
    subject_distribution: DistributionItem[]
    department_authorization_distribution: DistributionItem[]
    effect_distribution: DistributionItem[]
    department_distribution: DistributionItem[]
    risk_distribution: DistributionItem[]
  }
}

const report = ref<UserReportPayload | null>(null)
const loading = ref(false)
const error = ref('')
const feedback = ref('')
const reportExportModalOpen = ref(false)
const reportExportFormat = ref<'png' | 'html' | 'pdf'>('png')
const exportingReport = ref(false)
const auth = useAuthStore()
const canExport = computed(() => auth.can(actionPermissionForPath('/admin/user-report', 'export')))

const summary = computed(() => report.value?.summary || {
  total_users: 0,
  active_users: 0,
  disabled_users: 0,
  department_count: 0,
  otp_bound: 0,
  otp_unbound: 0,
})
const kpis = computed(() => [
  { label: '用户总数', value: summary.value.total_users, hint: '包含超级管理员', icon: UsersRound, tone: 'blue' },
  { label: '启用用户', value: summary.value.active_users, hint: '当前允许登录', icon: UserCheck, tone: 'green' },
  { label: '禁用用户', value: summary.value.disabled_users, hint: '当前禁止登录', icon: UserX, tone: 'red' },
  { label: '部门数量', value: summary.value.department_count, hint: '不包含公司根节点', icon: Building2, tone: 'purple' },
  { label: 'OTP 已绑定', value: summary.value.otp_bound, hint: '已完成二次认证绑定', icon: KeyRound, tone: 'cyan' },
  { label: 'OTP 未绑定', value: summary.value.otp_unbound, hint: '尚未完成 OTP 绑定', icon: KeyRound, tone: 'orange' },
])
const permissionSummary = computed(() => report.value?.permission_statistics?.summary || {
  total_policies: 0,
  available_policies: 0,
  disabled_policies: 0,
  department_policies: 0,
  user_policies: 0,
  allowed_rules: 0,
  denied_rules: 0,
})
const permissionKpis = computed(() => [
  { label: '策略总数', value: permissionSummary.value.total_policies, hint: '系统全部权限策略', icon: KeyRound, tone: 'blue' },
  { label: '启用策略', value: permissionSummary.value.available_policies, hint: '状态为已启用', icon: ShieldCheck, tone: 'green' },
  { label: '停用策略', value: permissionSummary.value.disabled_policies, hint: '状态为已停用', icon: CircleOff, tone: 'red' },
  { label: '部门策略', value: permissionSummary.value.department_policies, hint: '授权对象为部门', icon: Building2, tone: 'purple' },
  { label: '用户策略', value: permissionSummary.value.user_policies, hint: '授权对象为用户', icon: UsersRound, tone: 'cyan' },
  { label: '允许权限', value: permissionSummary.value.allowed_rules, hint: `拒绝 ${permissionSummary.value.denied_rules} 项`, icon: ShieldX, tone: 'orange' },
])

/** 返回用户报表统一的 ECharts 配色和坐标样式。 */
function chartBase() {
  return {
    color: ['#2563eb', '#14b8a6', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'],
    tooltip: { trigger: 'axis' },
    grid: { left: 28, right: 24, top: 24, bottom: 26, containLabel: true },
    textStyle: { color: '#64748b' },
  }
}

/** 构建用户数量饼图，空数据仍保持稳定布局。 */
function pieOption(items: DistributionItem[], unit = '人') {
  return {
    color: ['#2563eb', '#f59e0b', '#14b8a6', '#ef4444'],
    tooltip: { trigger: 'item', formatter: `{b}<br/>{c} ${unit}（{d}%）` },
    legend: { type: 'scroll', bottom: 0, textStyle: { color: '#64748b' } },
    series: [{
      type: 'pie',
      radius: ['42%', '68%'],
      center: ['50%', '44%'],
      avoidLabelOverlap: true,
      label: { formatter: `{b}\n{c} ${unit}`, color: '#64748b' },
      data: items.filter((item) => item.value > 0),
    }],
  }
}

const departmentOption = computed(() => pieOption(report.value?.department_distribution || []))
const otpOption = computed(() => pieOption(report.value?.otp_distribution || []))
const statusOption = computed(() => pieOption(report.value?.status_distribution || []))
const permissionAuthorizationModeOption = computed(() => pieOption(report.value?.permission_statistics?.authorization_mode_distribution || [], '项'))
const permissionDepartmentAuthorizationOption = computed(() => pieOption(report.value?.permission_statistics?.department_authorization_distribution || [], '个'))
const permissionEffectOption = computed(() => pieOption(report.value?.permission_statistics?.effect_distribution || [], '项'))
const permissionDepartmentOption = computed(() => pieOption(report.value?.permission_statistics?.department_distribution || [], '项'))
const permissionRiskOption = computed(() => pieOption(report.value?.permission_statistics?.risk_distribution || [], '项'))
const registrationOption = computed(() => {
  const items = report.value?.registration_trend || []
  return {
    ...chartBase(),
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', boundaryGap: false, data: items.map((item) => item.date), axisTick: { show: false } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: 'rgba(148, 163, 184, .18)' } } },
    series: [{
      type: 'line',
      name: '新增用户',
      data: items.map((item) => item.value),
      smooth: true,
      symbolSize: 7,
      lineStyle: { width: 3 },
      areaStyle: { color: 'rgba(37, 99, 235, .14)' },
    }],
  }
})

/** 从后端加载当前权限和部门范围内的用户统计。 */
async function loadReport() {
  loading.value = true
  error.value = ''
  feedback.value = ''
  try {
    report.value = await api('/user-report/')
  } catch (reason: any) {
    error.value = reason.message || '加载用户报表失败'
  } finally {
    loading.value = false
  }
}

/** 返回当前用户报表的页面元素，作为三种导出格式的统一数据源。 */
function reportSourceElement() {
  const source = document.querySelector<HTMLElement>('.user-report-page')
  if (!source) throw new Error('未找到用户报表内容')
  return source
}

/** 返回当前主题的页面背景色，避免导出的透明区域显示异常。 */
function reportBackgroundColor() {
  const bodyBackground = getComputedStyle(document.body).backgroundColor
  if (bodyBackground && bodyBackground !== 'rgba(0, 0, 0, 0)' && bodyBackground !== 'transparent') return bodyBackground
  return getComputedStyle(document.documentElement).getPropertyValue('--surface-deep').trim() || '#020617'
}

/** 将当前用户报表渲染为画布，并临时隐藏按钮、提示和加载状态。 */
async function renderReportSnapshotCanvas() {
  const source = reportSourceElement()
  const hiddenNodes = Array.from(source.querySelectorAll<HTMLElement>(
    '.bastion-report-actions, .user-report-error, .user-report-feedback, .bastion-report-loading',
  ))
  const oldVisibility = hiddenNodes.map((node) => node.style.visibility)
  hiddenNodes.forEach((node) => { node.style.visibility = 'hidden' })
  await nextTick()
  try {
    return await html2canvas(source, {
      backgroundColor: reportBackgroundColor(),
      scale: Math.min(2, window.devicePixelRatio || 1),
      useCORS: true,
      logging: false,
      width: Math.ceil(source.getBoundingClientRect().width),
      height: Math.ceil(source.scrollHeight),
      windowWidth: document.documentElement.clientWidth,
      windowHeight: Math.max(document.documentElement.clientHeight, source.scrollHeight),
    })
  } finally {
    hiddenNodes.forEach((node, index) => { node.style.visibility = oldVisibility[index] })
  }
}

/** 生成带时间戳的用户报表下载文件名。 */
function reportExportFilename(extension: 'png' | 'html' | 'pdf') {
  const stamp = new Date().toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).replace(/\D/g, '')
  return `user-report-${stamp}.${extension}`
}

/** 通过临时下载链接保存浏览器内生成的文件，不打开新窗口。 */
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/** 将报表截图封装为可离线查看的 HTML 文档。 */
function reportExportDocument(imageSource: string, width: number) {
  const backgroundColor = reportBackgroundColor()
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>用户报表</title>
  <style>
    body { margin: 0; padding: 24px 28px 40px; background: ${backgroundColor}; }
    main { width: ${Math.ceil(width)}px; max-width: 100%; margin: 0 auto; }
    img { display: block; width: 100%; height: auto; }
  </style>
</head>
<body><main><img src="${imageSource}" alt="用户报表" /></main></body>
</html>`
}

/** 导出当前用户报表为 PNG 图片。 */
async function exportUserReportPng() {
  const canvas = await renderReportSnapshotCanvas()
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((result) => {
      if (result) resolve(result)
      else reject(new Error('图片生成失败'))
    }, 'image/png')
  })
  downloadBlob(blob, reportExportFilename('png'))
  feedback.value = '用户报表 PNG 图片已下载'
}

/** 导出嵌入报表快照的 HTML 文件，确保离线打开仍保持当前样式。 */
async function exportUserReportHtml() {
  const source = reportSourceElement()
  const canvas = await renderReportSnapshotCanvas()
  const documentContent = reportExportDocument(canvas.toDataURL('image/png'), source.getBoundingClientRect().width)
  downloadBlob(new Blob([documentContent], { type: 'text/html;charset=utf-8' }), reportExportFilename('html'))
  feedback.value = '用户报表 HTML 文件已下载'
}

/** 将长报表画布按横向 A4 可用高度分页，并直接下载 PDF 文件。 */
async function exportUserReportPdf() {
  const canvas = await renderReportSnapshotCanvas()
  const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' })
  const margin = 8
  const printableWidth = pdf.internal.pageSize.getWidth() - margin * 2
  const printableHeight = pdf.internal.pageSize.getHeight() - margin * 2
  const sliceHeight = Math.max(1, Math.floor(printableHeight * canvas.width / printableWidth))

  for (let offset = 0, pageIndex = 0; offset < canvas.height; offset += sliceHeight, pageIndex += 1) {
    const currentSliceHeight = Math.min(sliceHeight, canvas.height - offset)
    const pageCanvas = document.createElement('canvas')
    pageCanvas.width = canvas.width
    pageCanvas.height = currentSliceHeight
    const context = pageCanvas.getContext('2d')
    if (!context) throw new Error('PDF 页面生成失败')
    context.drawImage(canvas, 0, offset, canvas.width, currentSliceHeight, 0, 0, canvas.width, currentSliceHeight)
    if (pageIndex > 0) pdf.addPage('a4', 'landscape')
    pdf.addImage(
      pageCanvas.toDataURL('image/png'),
      'PNG',
      margin,
      margin,
      printableWidth,
      currentSliceHeight * printableWidth / canvas.width,
      undefined,
      'FAST',
    )
  }

  pdf.save(reportExportFilename('pdf'))
  feedback.value = '用户报表 PDF 文件已下载'
}

/** 根据弹窗选择的格式生成文件，并在完成后关闭导出弹窗。 */
async function submitReportExport() {
  if (!report.value) {
    error.value = '暂无可导出的报表数据'
    return
  }
  exportingReport.value = true
  error.value = ''
  feedback.value = ''
  try {
    if (reportExportFormat.value === 'html') await exportUserReportHtml()
    else if (reportExportFormat.value === 'pdf') await exportUserReportPdf()
    else await exportUserReportPng()
    reportExportModalOpen.value = false
  } catch (reason: any) {
    error.value = reason.message || '导出用户报表失败'
  } finally {
    exportingReport.value = false
  }
}

onMounted(loadReport)
</script>

<template>
  <section class="bastion-report-center user-report-page">
    <header class="bastion-report-head">
      <div>
        <h2>用户报表</h2>
      </div>
      <div class="bastion-report-actions">
        <button v-if="canExport" class="secondary" type="button" :disabled="loading || !report" @click="reportExportModalOpen = true">
          <Download :size="16" />导出报表
        </button>
        <button class="secondary action-refresh" type="button" title="刷新报表" :disabled="loading" @click="loadReport">
          <RefreshCw :size="16" :class="{ spin: loading }" />刷新报表
        </button>
      </div>
    </header>

    <p v-if="error" class="form-error user-report-error">{{ error }}</p>
    <p v-if="feedback" class="bastion-feedback user-report-feedback">{{ feedback }}</p>
    <div v-if="loading && !report" class="bastion-report-loading">正在汇总用户数据...</div>
    <template v-else>
      <section class="bastion-report-kpis user-report-kpis">
        <article v-for="item in kpis" :key="item.label" :class="['bastion-report-kpi', `tone-${item.tone}`]">
          <span class="user-report-kpi-label"><component :is="item.icon" :size="17" />{{ item.label }}</span>
          <b>{{ item.value }}</b>
          <em>{{ item.hint }}</em>
        </article>
      </section>

      <section class="bastion-report-kpis user-report-kpis">
        <article v-for="item in permissionKpis" :key="item.label" :class="['bastion-report-kpi', `tone-${item.tone}`]">
          <span class="user-report-kpi-label"><component :is="item.icon" :size="17" />{{ item.label }}</span>
          <b>{{ item.value }}</b>
          <em>{{ item.hint }}</em>
        </article>
      </section>

      <section class="bastion-report-grid">
        <article class="bastion-report-panel">
          <header><strong>部门用户分布</strong><span>按直属部门统计</span></header>
          <EChart :option="departmentOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>OTP 绑定情况</strong><span>用户二次认证覆盖</span></header>
          <EChart :option="otpOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>用户账号状态</strong><span>启用与禁用用户</span></header>
          <EChart :option="statusOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>授权模式</strong><span>有效策略的直接与继承授权</span></header>
          <EChart :option="permissionAuthorizationModeOption" />
        </article>
      </section>

      <section class="bastion-report-grid">
        <article class="bastion-report-panel">
          <header><strong>部门授权</strong><span>直接配置有效策略的部门</span></header>
          <EChart :option="permissionDepartmentAuthorizationOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>权限效果</strong><span>完整权限矩阵允许与拒绝</span></header>
          <EChart :option="permissionEffectOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>部门策略分布</strong><span>按授权对象所属部门统计</span></header>
          <EChart :option="permissionDepartmentOption" />
        </article>
        <article class="bastion-report-panel">
          <header><strong>高风险操作授权</strong><span>仅统计已启用策略允许项</span></header>
          <EChart :option="permissionRiskOption" />
        </article>
        <article class="bastion-report-panel wide">
          <header><strong>近 7 天新增用户</strong><span>按用户创建日期统计</span></header>
          <EChart :option="registrationOption" />
        </article>
      </section>
    </template>
  </section>

  <ModalDialog :open="reportExportModalOpen" title="导出用户报表" width="560px" @close="reportExportModalOpen = false">
    <form class="bastion-form report-export-form" @submit.prevent="submitReportExport">
      <label class="wide">
        <span>导出格式</span>
        <div class="bastion-radio-group report-export-options user-report-export-options">
          <label class="bastion-radio-option">
            <input v-model="reportExportFormat" type="radio" value="png" />
            <span><FileImage :size="16" />图片 PNG</span>
          </label>
          <label class="bastion-radio-option">
            <input v-model="reportExportFormat" type="radio" value="html" />
            <span><FileCode2 :size="16" />HTML 文件</span>
          </label>
          <label class="bastion-radio-option">
            <input v-model="reportExportFormat" type="radio" value="pdf" />
            <span><FileText :size="16" />PDF 文件</span>
          </label>
        </div>
      </label>
      <p class="field-hint">文件由浏览器直接生成并下载，不会打开打印窗口。</p>
      <footer>
        <button class="secondary" type="button" :disabled="exportingReport" @click="reportExportModalOpen = false">取消</button>
        <button class="primary bastion-save-button" type="submit" :disabled="exportingReport">
          {{ exportingReport ? '生成中...' : '下载' }}
        </button>
      </footer>
    </form>
  </ModalDialog>
</template>
