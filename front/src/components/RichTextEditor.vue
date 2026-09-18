<script setup lang="ts">
import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  Code2,
  Image,
  Italic,
  Link,
  List,
  ListOrdered,
  Quote,
  RemoveFormatting,
  Strikethrough,
  Underline,
} from 'lucide-vue-next'
import { nextTick, ref, watch } from 'vue'

const props = defineProps<{
  modelValue?: string
  disabled?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const editorRef = ref<HTMLElement | null>(null)
const focused = ref(false)

/**
 * 处理 syncFromValue 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function syncFromValue() {
  const editor = editorRef.value
  if (!editor || focused.value) return
  const value = props.modelValue || ''
  if (editor.innerHTML !== value) editor.innerHTML = value
}

watch(() => props.modelValue, syncFromValue)

nextTick(syncFromValue)

/**
 * 处理 emitCurrent 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function emitCurrent() {
  emit('update:modelValue', editorRef.value?.innerHTML || '')
}

/**
 * 处理 run 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function run(command: string, value?: string) {
  if (props.disabled) return
  editorRef.value?.focus()
  document.execCommand(command, false, value)
  emitCurrent()
}

/**
 * 处理 setBlock 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function setBlock(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  run('formatBlock', value)
}

/**
 * 处理 createLink 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function createLink() {
  const url = window.prompt('请输入链接地址')
  if (url) run('createLink', url)
}

/**
 * 处理 insertImage 对应的 FRP 前端业务步骤。
 * 参数：按函数签名传入当前界面所需数据。
 * 返回：返回该步骤生成、查询或校验后的结果。
 * 副作用：可能更新当前组件状态或请求后端。
 */
function insertImage() {
  const url = window.prompt('请输入图片地址')
  if (url) run('insertImage', url)
}
</script>

<template>
  <div class="rich-text-editor">
    <div class="rich-text-toolbar">
      <select :disabled="disabled" title="段落格式" @change="setBlock">
        <option value="p">正文</option>
        <option value="h2">标题</option>
        <option value="h3">小标题</option>
        <option value="blockquote">引用块</option>
      </select>
      <button type="button" title="加粗" :disabled="disabled" @click="run('bold')"><Bold :size="16" /></button>
      <button type="button" title="斜体" :disabled="disabled" @click="run('italic')"><Italic :size="16" /></button>
      <button type="button" title="下划线" :disabled="disabled" @click="run('underline')"><Underline :size="16" /></button>
      <button type="button" title="删除线" :disabled="disabled" @click="run('strikeThrough')"><Strikethrough :size="16" /></button>
      <span class="rich-text-divider"></span>
      <button type="button" title="有序列表" :disabled="disabled" @click="run('insertOrderedList')"><ListOrdered :size="16" /></button>
      <button type="button" title="无序列表" :disabled="disabled" @click="run('insertUnorderedList')"><List :size="16" /></button>
      <button type="button" title="左对齐" :disabled="disabled" @click="run('justifyLeft')"><AlignLeft :size="16" /></button>
      <button type="button" title="居中" :disabled="disabled" @click="run('justifyCenter')"><AlignCenter :size="16" /></button>
      <button type="button" title="右对齐" :disabled="disabled" @click="run('justifyRight')"><AlignRight :size="16" /></button>
      <span class="rich-text-divider"></span>
      <button type="button" title="引用" :disabled="disabled" @click="run('formatBlock', 'blockquote')"><Quote :size="16" /></button>
      <button type="button" title="代码" :disabled="disabled" @click="run('formatBlock', 'pre')"><Code2 :size="16" /></button>
      <button type="button" title="链接" :disabled="disabled" @click="createLink"><Link :size="16" /></button>
      <button type="button" title="图片" :disabled="disabled" @click="insertImage"><Image :size="16" /></button>
      <button type="button" title="清除格式" :disabled="disabled" @click="run('removeFormat')"><RemoveFormatting :size="16" /></button>
    </div>
    <div
      ref="editorRef"
      class="rich-text-surface"
      :contenteditable="!disabled"
      spellcheck="false"
      @focus="focused = true"
      @blur="focused = false; emitCurrent()"
      @input="emitCurrent"
    ></div>
  </div>
</template>
