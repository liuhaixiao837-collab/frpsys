<script setup lang="ts">
import {
  Activity, CheckCircle2, Globe2, LoaderCircle, Network, Play, RadioTower,
  Route, Server, TerminalSquare, XCircle,
} from 'lucide-vue-next'
import { computed, reactive, ref } from 'vue'

import { api, apiStream } from '../../api'
import CustomSelect from '../../components/CustomSelect.vue'
import { actionPermissionForPath } from '../../permissions'
import { useAuthStore } from '../../stores/auth'

type ToolName = 'ping' | 'telnet' | 'curl' | 'traceroute' | 'mtr'
type ToolResult = {
  tool: ToolName
  target: string
  resolved_address: string
  port?: number
  status_code?: number
  success: boolean
  duration_ms: number
  detail: string
  output?: string
}

const auth = useAuthStore()
const activeTool = ref<ToolName>('ping')
const running = ref(false)
const error = ref('')
const result = ref<ToolResult | null>(null)
const form = reactive({ target: '', port: 22, count: 4, max_hops: 20, timeout_seconds: 3, method: 'GET' })

const canPing = computed(() => auth.can(actionPermissionForPath('/settings/system-tools', 'ping')))
const canTelnet = computed(() => auth.can(actionPermissionForPath('/settings/system-tools', 'telnet')))
const canCurl = computed(() => auth.can(actionPermissionForPath('/settings/system-tools', 'curl')))
const canTraceroute = computed(() => auth.can(actionPermissionForPath('/settings/system-tools', 'traceroute')))
const canMtr = computed(() => auth.can(actionPermissionForPath('/settings/system-tools', 'mtr')))
const canExecute = computed(() => ({
  ping: canPing.value,
  telnet: canTelnet.value,
  curl: canCurl.value,
  traceroute: canTraceroute.value,
  mtr: canMtr.value,
}[activeTool.value]))
const isLiveResult = computed(() => running.value && result.value?.tool === 'traceroute')

/**
 * 切换当前诊断工具，并清理上一次错误和结果。
 * 参数：`tool` 为用户选择的平台诊断工具。
 * 返回：无显式返回值。
 * 副作用：更新当前工具、错误和结果状态；执行期间不会切换。
 */
function selectTool(tool: ToolName) {
  if (running.value) return
  activeTool.value = tool
  error.value = ''
  result.value = null
}

/**
 * 提交当前网络诊断参数，并展示普通响应或实时路由追踪结果。
 * 参数：无，读取当前表单和工具状态。
 * 返回：诊断完成后解析的 Promise。
 * 副作用：请求后端诊断接口，并更新运行、错误和结果状态。
 */
async function executeTool() {
  error.value = ''
  result.value = null
  if (!form.target.trim()) {
    error.value = activeTool.value === 'curl'
      ? '请输入需要请求的 HTTP 或 HTTPS 地址'
      : '请输入需要检测的 IP 地址或主机名'
    return
  }
  if (!canExecute.value) {
    error.value = `没有执行 ${toolLabel(activeTool.value)} 的权限`
    return
  }
  running.value = true
  try {
    const payload: Record<string, any> = {
      target: form.target.trim(),
      timeout_seconds: Number(form.timeout_seconds),
    }
    if (activeTool.value === 'ping') payload.count = Number(form.count)
    else if (activeTool.value === 'telnet') payload.port = Number(form.port)
    else if (activeTool.value === 'curl') payload.method = form.method
    else {
      payload.max_hops = Number(form.max_hops)
      if (activeTool.value === 'mtr') payload.count = Number(form.count)
    }
    if (activeTool.value === 'traceroute') {
      const response = await apiStream('/system-tools/traceroute/', {
        payload,
        /**
         * 接收路由追踪事件，并把增量输出追加到当前诊断结果。
         * 参数：`event` 为 SSE 事件名；`data` 为后端事件载荷。
         * 返回：无显式返回值。
         * 副作用：更新当前诊断结果，并把输出限制在 16000 个字符以内。
         */
        onEvent(event: string, data: any) {
          if (event === 'start') result.value = data as ToolResult
          else if (event === 'output' && result.value) {
            result.value.output = `${result.value.output || ''}${data.text || ''}`.slice(-16000)
          } else if (event === 'done') result.value = data as ToolResult
        },
      }) as ToolResult
      if (response) result.value = response
      return
    }
    result.value = await api(`/system-tools/${activeTool.value}/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }) as ToolResult
  } catch (reason: any) {
    error.value = reason.message || '网络诊断执行失败'
  } finally {
    running.value = false
  }
}

/**
 * 返回诊断工具对应的中文名称。
 * 参数：`tool` 为平台诊断工具代码。
 * 返回：面向用户的中文工具名称。
 * 副作用：不修改页面或持久化状态。
 */
function toolLabel(tool: ToolName) {
  if (tool === 'ping') return 'Ping 检测'
  if (tool === 'telnet') return 'Telnet 检测'
  if (tool === 'curl') return 'Curl HTTP 检测'
  if (tool === 'traceroute') return 'Traceroute 路由追踪'
  return 'MTR 链路质量'
}

/**
 * 返回当前诊断结果的用户友好状态文案。
 * 参数：`item` 为后端返回的结构化诊断结果。
 * 返回：成功、失败或运行中的中文标题。
 * 副作用：不修改页面或持久化状态。
 */
function resultTitle(item: ToolResult) {
  if (running.value && item.tool === 'traceroute') return '正在追踪路由'
  if (item.tool === 'telnet') return item.success ? '目标端口已开放' : '目标端口未开放'
  if (item.tool === 'curl') return item.success ? 'HTTP 请求成功' : 'HTTP 请求失败'
  if (item.tool === 'traceroute') return item.success ? '路由追踪完成' : '路由追踪未完整完成'
  if (item.tool === 'mtr') return item.success ? '链路质量探测完成' : '已返回当前链路结果'
  return item.success ? '目标主机可达' : '目标主机未响应'
}

/**
 * 返回当前工具顶部的用途和安全边界说明。
 * 参数：无，读取当前工具状态。
 * 返回：当前工具的中文说明。
 * 副作用：不修改页面或持久化状态。
 */
function toolDescription() {
  if (activeTool.value === 'ping') return '发送受控 ICMP 探测请求，检查目标主机是否可达。'
  if (activeTool.value === 'telnet') return '建立一次 TCP 握手，明确判断目标服务端口是否开放。'
  if (activeTool.value === 'curl') return '请求 HTTP 服务并在内存中显示有限响应预览，不在服务器保存文件。'
  if (activeTool.value === 'traceroute') return '实时追踪数据包到目标主机所经过的网络节点。'
  return '统计各跳节点的丢包率与最小、平均、最大响应延迟。'
}

/**
 * 返回指定诊断工具使用的本地图标组件。
 * 参数：`tool` 为平台诊断工具代码。
 * 返回：已由本地依赖打包的 Lucide 图标组件。
 * 副作用：不请求外部静态资源，也不修改页面状态。
 */
function toolIcon(tool: ToolName) {
  if (tool === 'ping') return Activity
  if (tool === 'telnet') return TerminalSquare
  if (tool === 'curl') return Globe2
  if (tool === 'traceroute') return Route
  return RadioTower
}
</script>

<template>
  <section class="system-tools-page">
    <section class="system-tools-workspace">
      <aside class="system-tools-selector">
        <button type="button" :disabled="running" :class="{ active: activeTool === 'ping' }" @click="selectTool('ping')">
          <span class="tool-selector-icon ping"><Activity :size="21" /></span>
          <span><strong>Ping</strong><small>验证目标主机网络可达性</small></span>
          <em :class="canPing ? 'allowed' : 'denied'">{{ canPing ? '可执行' : '未授权' }}</em>
        </button>
        <button type="button" :disabled="running" :class="{ active: activeTool === 'telnet' }" @click="selectTool('telnet')">
          <span class="tool-selector-icon telnet"><TerminalSquare :size="21" /></span>
          <span><strong>Telnet</strong><small>检测指定 TCP 服务端口</small></span>
          <em :class="canTelnet ? 'allowed' : 'denied'">{{ canTelnet ? '可执行' : '未授权' }}</em>
        </button>
        <button type="button" :disabled="running" :class="{ active: activeTool === 'curl' }" @click="selectTool('curl')">
          <span class="tool-selector-icon curl"><Globe2 :size="21" /></span>
          <span><strong>Curl</strong><small>检查 HTTP 服务响应内容</small></span>
          <em :class="canCurl ? 'allowed' : 'denied'">{{ canCurl ? '可执行' : '未授权' }}</em>
        </button>
        <button type="button" :disabled="running" :class="{ active: activeTool === 'traceroute' }" @click="selectTool('traceroute')">
          <span class="tool-selector-icon traceroute"><Route :size="21" /></span>
          <span><strong>Traceroute</strong><small>追踪目标主机网络路径</small></span>
          <em :class="canTraceroute ? 'allowed' : 'denied'">{{ canTraceroute ? '可执行' : '未授权' }}</em>
        </button>
        <button type="button" :disabled="running" :class="{ active: activeTool === 'mtr' }" @click="selectTool('mtr')">
          <span class="tool-selector-icon mtr"><RadioTower :size="21" /></span>
          <span><strong>MTR</strong><small>统计逐跳丢包与响应延迟</small></span>
          <em :class="canMtr ? 'allowed' : 'denied'">{{ canMtr ? '可执行' : '未授权' }}</em>
        </button>
      </aside>

      <main class="system-tool-console">
        <header>
          <span class="tool-console-icon"><component :is="toolIcon(activeTool)" :size="22" /></span>
          <div>
            <h3>{{ toolLabel(activeTool) }}</h3>
            <p>{{ toolDescription() }}</p>
          </div>
        </header>

        <form class="system-tool-form" :class="{ 'mtr-form': activeTool === 'mtr' }" @submit.prevent="executeTool">
          <label class="target-field">
            <span>目标地址</span>
            <div class="system-tool-field-control">
              <component :is="activeTool === 'curl' ? Globe2 : Server" :size="17" />
              <input
                v-model="form.target"
                :maxlength="activeTool === 'curl' ? 2048 : 253"
                :placeholder="activeTool === 'curl' ? '例如：https://server.example.com/health' : '例如：192.168.1.10 或 server.example.com'"
              />
            </div>
            <small>{{ activeTool === 'curl' ? '仅支持 HTTP/HTTPS，不跟随重定向且响应不落盘' : '支持 IPv4、IPv6 和合法 DNS 主机名' }}</small>
          </label>
          <label v-if="activeTool === 'telnet'">
            <span>目标端口</span>
            <input v-model.number="form.port" type="number" min="1" max="65535" />
            <small>允许范围 1-65535</small>
          </label>
          <label v-else-if="activeTool === 'ping' || activeTool === 'mtr'">
            <span>探测次数</span>
            <input v-model.number="form.count" type="number" min="1" :max="activeTool === 'mtr' ? 10 : 5" />
            <small>单次最多 {{ activeTool === 'mtr' ? 10 : 5 }} 次</small>
          </label>
          <label v-else-if="activeTool === 'curl'">
            <span>请求方法</span>
            <CustomSelect v-model="form.method" aria-label="请求方法">
              <option value="GET">GET</option>
              <option value="HEAD">HEAD</option>
            </CustomSelect>
            <small>支持 GET、HEAD</small>
          </label>
          <label v-else>
            <span>最大跳数</span>
            <input v-model.number="form.max_hops" type="number" min="1" max="30" />
            <small>允许范围 1-30 跳</small>
          </label>
          <label v-if="activeTool === 'mtr'">
            <span>最大跳数</span>
            <input v-model.number="form.max_hops" type="number" min="1" max="30" />
            <small>允许范围 1-30 跳</small>
          </label>
          <label>
            <span>超时时间</span>
            <div class="system-tool-time-control">
              <input v-model.number="form.timeout_seconds" type="number" min="1" :max="activeTool === 'curl' ? 30 : (activeTool === 'telnet' ? 10 : 5)" />
              <b>秒</b>
            </div>
            <small>{{ activeTool === 'curl' ? '允许范围 1-30 秒' : (activeTool === 'telnet' ? '允许范围 1-10 秒' : '允许范围 1-5 秒') }}</small>
          </label>
          <button class="primary system-tool-run" type="submit" :disabled="running || !canExecute">
            <Play :size="16" />{{ running ? '诊断中...' : '开始诊断' }}
          </button>
        </form>

        <p v-if="error" class="form-error system-tool-error">{{ error }}</p>

        <section
          v-if="result"
          class="system-tool-result"
          :class="{ success: result.success && !isLiveResult, failed: !result.success && !isLiveResult, running: isLiveResult }"
        >
          <header>
            <span>
              <LoaderCircle v-if="isLiveResult" class="spin" :size="24" />
              <CheckCircle2 v-else-if="result.success" :size="24" />
              <XCircle v-else :size="24" />
            </span>
            <div><strong>{{ resultTitle(result) }}</strong><small>{{ result.detail }}</small></div>
            <em>{{ result.duration_ms }} ms</em>
          </header>
          <dl>
            <div><dt>检测项目</dt><dd>{{ toolLabel(result.tool) }}</dd></div>
            <div><dt>目标地址</dt><dd :title="result.target">{{ result.target }}</dd></div>
            <div><dt>解析地址</dt><dd :title="result.resolved_address">{{ result.resolved_address || '不适用' }}</dd></div>
            <div v-if="result.port"><dt>目标端口</dt><dd>{{ result.port }}</dd></div>
            <div v-else-if="result.status_code"><dt>HTTP 状态</dt><dd>{{ result.status_code }}</dd></div>
          </dl>
          <pre v-if="result.output">{{ result.output }}</pre>
        </section>

        <section v-else class="system-tool-empty">
          <Network :size="38" />
          <strong>等待执行网络诊断</strong>
          <span>填写目标信息后开始诊断，结果会在此处实时呈现。</span>
        </section>
      </main>
    </section>
  </section>
</template>

