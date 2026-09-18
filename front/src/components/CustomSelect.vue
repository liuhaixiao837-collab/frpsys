<script setup lang="ts">
import { Check, ChevronDown, Search } from 'lucide-vue-next'
import { Comment, computed, Fragment, nextTick, onBeforeUnmount, onMounted, ref, useAttrs, useSlots, watch, type VNode } from 'vue'

type SelectValue = string | number | boolean | null | undefined
type SelectOption = {
  value: SelectValue
  label: string
  disabled: boolean
  treeDepth: number | null
  description: string
  optionKind: string
}

defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{
  modelValue: SelectValue
  disabled?: boolean
  required?: boolean
  placeholder?: string
  ariaLabel?: string
  searchable?: boolean
  searchPlaceholder?: string
  modelModifiers?: Record<string, boolean>
}>(), {
  disabled: false,
  required: false,
  placeholder: '请选择',
  ariaLabel: '',
  searchable: false,
  searchPlaceholder: '搜索选项',
  modelModifiers: () => ({}),
})
const emit = defineEmits<{
  'update:modelValue': [value: SelectValue]
  change: [value: SelectValue]
}>()
const attrs = useAttrs()
const slots = useSlots()
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const open = ref(false)
const searchQuery = ref('')
const highlightedIndex = ref(-1)

/**
 * 递归读取 option 虚拟节点中的可见文字。
 * 参数：`content` 为 Vue 插槽节点或文本。
 * 返回：合并并去除首尾空白后的选项文字。
 * 副作用：不修改组件状态或页面元素。
 */
function optionText(content: unknown): string {
  if (typeof content === 'string' || typeof content === 'number') return String(content)
  if (Array.isArray(content)) return content.map((item) => optionText(item)).join('')
  if (content && typeof content === 'object' && 'children' in content) {
    return optionText((content as VNode).children)
  }
  return ''
}

/**
 * 把默认插槽中的原 option 节点展开成统一下拉选项。
 * 参数：`nodes` 为默认插槽返回的虚拟节点数组。
 * 返回：保留值、文字和禁用状态的扁平选项数组。
 * 副作用：不修改插槽节点。
 */
function flattenOptions(nodes: VNode[]): SelectOption[] {
  const result: SelectOption[] = []
  for (const node of nodes) {
    if (node.type === Comment) continue
    if (node.type === Fragment && Array.isArray(node.children)) {
      result.push(...flattenOptions(node.children as VNode[]))
      continue
    }
    if (node.type !== 'option') continue
    result.push({
      value: node.props?.value,
      label: optionText(node.children).trim(),
      disabled: Boolean(node.props?.disabled),
      treeDepth: node.props?.['data-depth'] === undefined ? null : Number(node.props['data-depth']),
      description: String(node.props?.['data-description'] || ''),
      optionKind: String(node.props?.['data-option-kind'] || ''),
    })
  }
  return result
}

const options = computed(() => flattenOptions(slots.default?.() || []))
const filteredOptions = computed(() => {
  const keyword = searchQuery.value.trim().toLocaleLowerCase()
  if (!props.searchable || !keyword) return options.value
  return options.value.filter((option) => (
    `${option.label} ${option.description}`.toLocaleLowerCase().includes(keyword)
  ))
})

/**
 * 判断两个下拉值在数字和字符串来源不一致时是否仍代表同一选项。
 * 参数：`left` 和 `right` 为需要比较的模型值与选项值。
 * 返回：值严格相同或非空字符串表示相同时返回真。
 * 副作用：不修改组件状态。
 */
function sameValue(left: SelectValue, right: SelectValue) {
  if (Object.is(left, right)) return true
  if (left == null || right == null) return false
  return String(left) === String(right)
}

const selectedIndex = computed(() => options.value.findIndex((option) => sameValue(option.value, props.modelValue)))
const selectedLabel = computed(() => options.value[selectedIndex.value]?.label || props.placeholder)

/**
 * 打开或关闭下拉选项层，并定位当前选中项。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：更新展开状态和键盘高亮项。
 */
function toggleDropdown() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    searchQuery.value = ''
    highlightedIndex.value = filteredOptions.value.findIndex((option) => (
      sameValue(option.value, props.modelValue) && !option.disabled
    ))
    if (highlightedIndex.value < 0) {
      highlightedIndex.value = filteredOptions.value.findIndex((option) => !option.disabled)
    }
    if (props.searchable) void nextTick(() => searchInput.value?.focus())
  } else {
    searchQuery.value = ''
  }
}

/**
 * 选择一个可用选项并向父组件同步模型值。
 * 参数：`option` 为用户选择的选项。
 * 返回：无显式返回值。
 * 副作用：更新 v-model、触发 change 事件并关闭选项层。
 */
function selectOption(option: SelectOption) {
  if (option.disabled) return
  let value = option.value
  if (props.modelModifiers.number && typeof value === 'string' && value !== '') value = Number(value)
  emit('update:modelValue', value)
  emit('change', value)
  open.value = false
  searchQuery.value = ''
  void nextTick(() => trigger.value?.focus())
}

/**
 * 按指定方向移动键盘高亮项并跳过禁用选项。
 * 参数：`direction` 为向上或向下移动方向。
 * 返回：无显式返回值。
 * 副作用：更新当前高亮选项下标。
 */
function moveHighlight(direction: -1 | 1) {
  if (!filteredOptions.value.length) return
  let index = highlightedIndex.value
  for (let count = 0; count < filteredOptions.value.length; count += 1) {
    index = (index + direction + filteredOptions.value.length) % filteredOptions.value.length
    if (!filteredOptions.value[index].disabled) {
      highlightedIndex.value = index
      return
    }
  }
}

/**
 * 处理下拉触发按钮上的方向键、Enter、空格和 Escape。
 * 参数：`event` 为键盘事件。
 * 返回：无显式返回值。
 * 副作用：可能展开、关闭或选择下拉项。
 */
function handleKeydown(event: KeyboardEvent) {
  if (props.disabled) return
  if (event.key === 'Escape') {
    open.value = false
    searchQuery.value = ''
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!open.value) toggleDropdown()
    else moveHighlight(event.key === 'ArrowDown' ? 1 : -1)
    return
  }
  if ((event.key === 'Enter' || event.key === ' ') && open.value) {
    event.preventDefault()
    const option = filteredOptions.value[highlightedIndex.value]
    if (option) selectOption(option)
  }
}

/**
 * 处理搜索输入框中的方向键、回车和退出操作。
 * 参数：`event` 为搜索框键盘事件。
 * 返回：无显式返回值。
 * 副作用：可能移动高亮项、选择选项或关闭下拉框。
 */
function handleSearchKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    open.value = false
    searchQuery.value = ''
    void nextTick(() => trigger.value?.focus())
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    moveHighlight(event.key === 'ArrowDown' ? 1 : -1)
    return
  }
  if (event.key === 'Enter') {
    event.preventDefault()
    const option = filteredOptions.value[highlightedIndex.value]
    if (option) selectOption(option)
  }
}

/**
 * 点击组件外部时关闭当前下拉选项层。
 * 参数：`event` 为文档指针事件。
 * 返回：无显式返回值。
 * 副作用：可能关闭选项层。
 */
function closeOutside(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) {
    open.value = false
    searchQuery.value = ''
  }
}

watch(searchQuery, () => {
  if (!open.value) return
  highlightedIndex.value = filteredOptions.value.findIndex((option) => !option.disabled)
})

onMounted(() => document.addEventListener('pointerdown', closeOutside))
onBeforeUnmount(() => document.removeEventListener('pointerdown', closeOutside))
</script>

<template>
  <div ref="root" class="custom-select" :class="{ open, disabled }" v-bind="attrs">
    <button
      ref="trigger"
      class="custom-select-trigger"
      type="button"
      role="combobox"
      :aria-label="ariaLabel || undefined"
      :aria-expanded="open"
      aria-haspopup="listbox"
      :aria-required="required || undefined"
      :disabled="disabled"
      @click="toggleDropdown"
      @keydown="handleKeydown"
    >
      <slot name="prefix" />
      <span :class="{ placeholder: selectedIndex < 0 }">{{ selectedLabel }}</span>
      <ChevronDown :size="15" />
    </button>
    <div v-if="open" class="custom-select-menu" role="listbox" :aria-label="ariaLabel || undefined">
      <label v-if="searchable" class="custom-select-search" @pointerdown.stop>
        <Search :size="14" />
        <input
          ref="searchInput"
          v-model="searchQuery"
          :placeholder="searchPlaceholder"
          autocomplete="off"
          @keydown="handleSearchKeydown"
        />
      </label>
      <p v-if="searchable && !filteredOptions.length" class="custom-select-empty">未找到匹配选项</p>
      <button
        v-for="(option, index) in filteredOptions"
        :key="`${String(option.value)}-${index}`"
      type="button"
      role="option"
      :class="{
        highlighted: highlightedIndex === index,
        'custom-select-tree-item': option.optionKind === 'tree',
        'custom-select-tree-child': option.optionKind === 'tree' && (option.treeDepth || 0) > 0,
      }"
      :style="option.treeDepth === null ? undefined : { '--custom-select-tree-depth': option.treeDepth }"
      :aria-level="option.optionKind === 'tree' ? (option.treeDepth || 0) + 1 : undefined"
      :aria-selected="sameValue(option.value, modelValue)"
        :disabled="option.disabled"
        @pointerenter="highlightedIndex = index"
        @click="selectOption(option)"
      >
        <span v-if="option.optionKind === 'tree'" class="custom-select-tree-option">
          <span class="custom-select-tree-guide" aria-hidden="true" />
          <span class="custom-select-tree-copy">
            <strong>{{ option.label }}</strong>
            <small v-if="option.description">{{ option.description }}</small>
          </span>
        </span>
        <span v-else>{{ option.label }}</span>
        <Check v-if="sameValue(option.value, modelValue)" :size="15" />
      </button>
    </div>
  </div>
</template>
