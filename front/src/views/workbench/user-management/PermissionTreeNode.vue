<script setup lang="ts">
import { ChevronDown, ChevronRight } from 'lucide-vue-next'
import { computed } from 'vue'

import type { PermissionPage } from './types'

type RuleEffect = 'allow' | 'deny'

defineOptions({ name: 'PermissionTreeNode' })

const props = withDefaults(defineProps<{
  page: PermissionPage
  level?: number
  ruleState: Record<string, RuleEffect>
  expandedPages: Set<string>
}>(), {
  level: 0,
})

const emit = defineEmits<{
  'toggle-page': [code: string]
  'set-state': [code: string, state: RuleEffect]
  'set-page-tree': [page: PermissionPage, state: RuleEffect]
}>()

const hasChildren = computed(() => Boolean(props.page.children?.length))
const hasActions = computed(() => Boolean(props.page.actions?.length))
const hasDetails = computed(() => hasChildren.value || hasActions.value)
const isOpen = computed(() => props.expandedPages.has(props.page.code))
/**
 * 根据页面权限代码和操作代码生成完整操作权限代码。
 * 参数：`action` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
function actionCode(action: string) {
  return `${props.page.code.replace(/\.view$/, '')}.${action}`
}

/**
 * 切换 toggle 对应的界面或业务状态。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能修改当前组件状态、定时器或页面元素。
 */
function toggle() {
  if (hasDetails.value) emit('toggle-page', props.page.code)
}
</script>

<template>
  <article class="permission-tree-page" :style="{ '--permission-level': String(level) }">
    <div class="permission-tree-page-head">
      <button class="permission-tree-toggle page-toggle" :class="{ 'is-leaf': !hasDetails }" type="button" @click="toggle">
        <ChevronDown v-if="hasDetails && isOpen" :size="15" />
        <ChevronRight v-else-if="hasDetails" :size="15" />
        <span v-else class="permission-leaf-dot" />
        <span>
          <strong>{{ page.name }}</strong>
        </span>
      </button>
      <div class="permission-state-buttons">
        <button class="allow" type="button" :class="{ active: ruleState[page.code] === 'allow' }" :aria-pressed="ruleState[page.code] === 'allow'" @click="emit('set-page-tree', page, 'allow')">允许</button>
        <button class="deny" type="button" :class="{ active: ruleState[page.code] === 'deny' }" :aria-pressed="ruleState[page.code] === 'deny'" @click="emit('set-page-tree', page, 'deny')">拒绝</button>
      </div>
    </div>

    <div v-if="isOpen" class="permission-tree-page-body">
      <div v-if="hasActions" class="permission-tree-actions">
        <div v-for="action in page.actions" :key="action.code" class="permission-tree-action">
          <span>{{ action.name }}</span>
          <div class="permission-state-buttons compact">
            <button class="allow" type="button" :class="{ active: ruleState[actionCode(action.code)] === 'allow' }" :aria-pressed="ruleState[actionCode(action.code)] === 'allow'" @click="emit('set-state', actionCode(action.code), 'allow')">允许</button>
            <button class="deny" type="button" :class="{ active: ruleState[actionCode(action.code)] === 'deny' }" :aria-pressed="ruleState[actionCode(action.code)] === 'deny'" @click="emit('set-state', actionCode(action.code), 'deny')">拒绝</button>
          </div>
        </div>
      </div>

      <div v-if="hasChildren" class="permission-tree-children">
        <PermissionTreeNode
          v-for="child in page.children"
          :key="child.code"
          :page="child"
          :level="level + 1"
          :rule-state="ruleState"
          :expanded-pages="expandedPages"
          @toggle-page="emit('toggle-page', $event)"
          @set-state="(code, state) => emit('set-state', code, state)"
          @set-page-tree="(node, state) => emit('set-page-tree', node, state)"
        />
      </div>
    </div>
  </article>
</template>
