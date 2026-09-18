<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

type MenuGroup = {
  title: string
  path?: string
  items: string[][]
}

const props = defineProps<{
  title: string
  description: string
  groups: MenuGroup[]
  activePath: string
  isActive?: (path: string) => boolean
}>()

const emit = defineEmits<{
  navigate: [path: string]
}>()

const openGroups = ref<Set<string>>(new Set())
const activeMatcher = computed(() => props.isActive || ((path: string) => path === props.activePath))

/**
 * 封装 activeGroupTitles 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：无。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function activeGroupTitles() {
  return props.groups
    .filter((group) => (group.path && activeMatcher.value(group.path)) || group.items.some(([, path]) => activeMatcher.value(path)))
    .map((group) => group.title)
}

/**
 * 封装 ensureActiveGroupOpen 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：不直接修改持久化数据。
 */
function ensureActiveGroupOpen() {
  const activeTitles = activeGroupTitles()
  if (!openGroups.value.size) {
    openGroups.value = new Set(activeTitles.length ? activeTitles : props.groups.slice(0, 1).map((group) => group.title))
    return
  }
  if (activeTitles.some((title) => !openGroups.value.has(title))) {
    openGroups.value = new Set([...openGroups.value, ...activeTitles])
  }
}

/**
 * 判断 isOpen 对应的业务条件是否成立。
 * 参数：`title` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function isOpen(title: string) {
  return openGroups.value.has(title)
}

/**
 * 切换 toggleGroup 对应的界面或业务状态。
 * 参数：`title` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function toggleGroup(title: string) {
  const next = new Set(openGroups.value)
  if (next.has(title)) next.delete(title)
  else next.add(title)
  openGroups.value = next
}

/**
 * 处理 handleGroupClick 对应的用户操作或系统事件。
 * 参数：`group` 表示该步骤所需的业务参数。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function handleGroupClick(group: MenuGroup) {
  if (group.path) {
    emit('navigate', group.path)
    return
  }
  toggleGroup(group.title)
}

watch(() => [props.activePath, props.groups], ensureActiveGroupOpen, { immediate: true, deep: true })
</script>

<template>
  <aside class="bastion-sidebar">
    <div class="bastion-brand">
      <strong>{{ title }}</strong>
      <span>{{ description }}</span>
    </div>
    <section
      v-for="group in groups"
      :key="group.title"
      class="bastion-nav-group"
      :class="{ collapsed: !isOpen(group.title) }"
    >
      <button
        type="button"
        class="bastion-nav-heading"
        :class="{ active: group.path && activeMatcher(group.path) }"
        :aria-expanded="group.path ? undefined : isOpen(group.title)"
        @click="handleGroupClick(group)"
      >
        <span>{{ group.title }}</span>
        <ChevronDown v-if="!group.path" :size="14" />
      </button>
      <div v-show="isOpen(group.title)" class="bastion-nav-items">
        <button
          v-for="[label, path] in group.items"
          :key="path"
          type="button"
          class="bastion-nav-item"
          :class="{ active: activeMatcher(path) }"
          @click="emit('navigate', path)"
        >
          {{ label }}
        </button>
      </div>
    </section>
  </aside>
</template>
