<script setup lang="ts">
import {
  ArrowDown, ArrowUp, ChevronDown, ChevronRight, CornerDownRight, RefreshCw, Save,
} from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'

import { api } from '../../api'
import { actionPermissionForPath } from '../../permissions'
import { useAuthStore } from '../../stores/auth'

type MenuOrderItem = {
  code: string
  name: string
  children: MenuOrderItem[]
}

const auth = useAuthStore()
const menuItems = ref<MenuOrderItem[]>([])
const loading = ref(false)
const saving = ref(false)
const changed = ref(false)
const error = ref('')
const expandedMenuCode = ref('')
const canUpdate = computed(() => auth.can(actionPermissionForPath('/settings/menu-order', 'update')))

/**
 * 从数据库加载当前用户的一级和二级菜单顺序。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：请求后端并替换当前页面中的菜单列表。
 */
async function loadMenus() {
  loading.value = true
  error.value = ''
  try {
    const payload = await api('/menu-order/')
    menuItems.value = Array.isArray(payload.items) ? payload.items : []
    expandedMenuCode.value = ''
    changed.value = false
  } catch (reason: any) {
    error.value = reason.message || '加载菜单顺序失败'
  } finally {
    loading.value = false
  }
}

/**
 * 切换指定主菜单的二级菜单折叠状态，并保证同时只展开一个主菜单。
 * 参数：`code` 为需要展开或折叠的主菜单代码。
 * 返回：无显式返回值。
 * 副作用：更新当前页面的菜单折叠状态。
 */
function toggleMenu(code: string) {
  expandedMenuCode.value = expandedMenuCode.value === code ? '' : code
}

/**
 * 将指定菜单向上或向下移动一个位置。
 * 参数：`index` 为当前菜单下标；`direction` 为移动方向。
 * 返回：无显式返回值。
 * 副作用：调整当前页面中的待保存菜单顺序。
 */
function moveMenu(index: number, direction: -1 | 1) {
  const targetIndex = index + direction
  if (targetIndex < 0 || targetIndex >= menuItems.value.length) return
  const next = [...menuItems.value]
  const current = next[index]
  next[index] = next[targetIndex]
  next[targetIndex] = current
  menuItems.value = next
  changed.value = true
}

/**
 * 将指定主菜单下的二级菜单向上或向下移动一个位置。
 * 参数：`parent` 为二级菜单所属主菜单；`index` 为当前下标；`direction` 为移动方向。
 * 返回：无显式返回值。
 * 副作用：调整当前页面中的待保存二级菜单顺序。
 */
function moveChild(parent: MenuOrderItem, index: number, direction: -1 | 1) {
  const targetIndex = index + direction
  if (targetIndex < 0 || targetIndex >= parent.children.length) return
  const next = [...parent.children]
  const current = next[index]
  next[index] = next[targetIndex]
  next[targetIndex] = current
  parent.children = next
  changed.value = true
}

/**
 * 把页面中的菜单树转换为后端要求的完整同级排序组。
 * 参数：无。
 * 返回：返回主菜单及每个父菜单下的完整代码顺序。
 * 副作用：不直接修改持久化数据。
 */
function buildOrders() {
  return [
    { parent_code: '__root__', codes: menuItems.value.map((item) => item.code) },
    ...menuItems.value
      .filter((item) => item.children.length)
      .map((item) => ({ parent_code: item.code, codes: item.children.map((child) => child.code) })),
  ]
}

/**
 * 保存当前用户的完整分层菜单顺序，并重新加载个人数据库导航。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：更新个人菜单偏好、写入系统日志并刷新当前页面。
 */
async function saveOrder() {
  if (!canUpdate.value || !changed.value) return
  saving.value = true
  error.value = ''
  try {
    await api('/menu-order/', {
      method: 'PUT',
      body: JSON.stringify({ orders: buildOrders() }),
    })
    window.location.reload()
  } catch (reason: any) {
    error.value = reason.message || '保存菜单顺序失败'
    saving.value = false
  }
}

onMounted(loadMenus)
</script>

<template>
  <section class="governance-page menu-order-page">
    <header class="governance-page-head">
      <div>
        <h2>菜单排序</h2>
      </div>
      <div class="toolbar-actions">
        <button
          class="secondary icon-button action-refresh"
          type="button"
          title="刷新"
          :disabled="loading || saving"
          @click="loadMenus"
        >
          <RefreshCw :size="16" :class="{ spin: loading }" />
        </button>
        <button
          v-if="canUpdate"
          class="primary"
          type="button"
          :disabled="!changed || loading || saving"
          @click="saveOrder"
        >
          <Save :size="16" />{{ saving ? '处理中' : '保存排序' }}
        </button>
      </div>
    </header>

    <div class="governance-card menu-order-card">
      <div class="governance-table menu-order-table">
        <div class="governance-table-row table-head">
          <span class="sequence-col">序号</span>
          <span>层级</span>
          <span>菜单名称</span>
          <span>操作</span>
        </div>
        <template v-for="(item, index) in menuItems" :key="item.code">
          <div class="governance-table-row menu-order-main-row">
            <span class="sequence-col">{{ index + 1 }}</span>
            <span class="menu-order-level">主菜单</span>
            <button
              class="menu-order-toggle"
              type="button"
              :title="expandedMenuCode === item.code ? `收起${item.name}` : `展开${item.name}`"
              :aria-expanded="expandedMenuCode === item.code"
              @click="toggleMenu(item.code)"
            >
              <ChevronDown v-if="expandedMenuCode === item.code" :size="17" />
              <ChevronRight v-else :size="17" />
              <strong>{{ item.name }}</strong>
            </button>
            <span class="row-actions menu-order-actions">
              <button
                v-if="canUpdate"
                class="secondary icon-button"
                type="button"
                title="上移主菜单"
                :disabled="index === 0 || saving"
                @click="moveMenu(index, -1)"
              >
                <ArrowUp :size="16" />
              </button>
              <button
                v-if="canUpdate"
                class="secondary icon-button"
                type="button"
                title="下移主菜单"
                :disabled="index === menuItems.length - 1 || saving"
                @click="moveMenu(index, 1)"
              >
                <ArrowDown :size="16" />
              </button>
              <span v-if="!canUpdate">仅查看</span>
            </span>
          </div>
          <div
            v-for="(child, childIndex) in item.children"
            v-show="expandedMenuCode === item.code"
            :key="child.code"
            class="governance-table-row menu-order-child-row"
          >
            <span class="sequence-col">{{ index + 1 }}.{{ childIndex + 1 }}</span>
            <span class="menu-order-level"><CornerDownRight :size="15" />二级菜单</span>
            <span>{{ child.name }}</span>
            <span class="row-actions menu-order-actions">
              <button
                v-if="canUpdate"
                class="secondary icon-button"
                type="button"
                title="上移二级菜单"
                :disabled="childIndex === 0 || saving"
                @click="moveChild(item, childIndex, -1)"
              >
                <ArrowUp :size="16" />
              </button>
              <button
                v-if="canUpdate"
                class="secondary icon-button"
                type="button"
                title="下移二级菜单"
                :disabled="childIndex === item.children.length - 1 || saving"
                @click="moveChild(item, childIndex, 1)"
              >
                <ArrowDown :size="16" />
              </button>
              <span v-if="!canUpdate">仅查看</span>
            </span>
          </div>
        </template>
        <p v-if="!loading && !menuItems.length" class="empty-list">暂无可排序菜单</p>
      </div>
      <p v-if="error" class="form-error menu-order-error">{{ error }}</p>
    </div>
  </section>
</template>
