<script setup lang="ts">
/**
 * CrudPagination.vue — 数据库管理通用分页组件
 *
 * 每页 10 条数据，首页 / 上一页 / 下一页 / 尾页 / 跳转到 X 页。
 * 所有元素居中对齐 (note.txt 第 5 条)。
 */
import { computed, ref } from 'vue'

const props = withDefaults(defineProps<{
  page: number
  pageSize?: number
  total: number
}>(), {
  pageSize: 10,
})

const emit = defineEmits<{
  (e: 'go', target: number): void
}>()

/** 总页数 */
const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

/** 当前页起始条目索引 */
const pageStart = computed(() => (props.total ? (props.page - 1) * props.pageSize + 1 : 0))

/** 当前页结束条目索引 */
const pageEnd = computed(() => Math.min(props.total, props.page * props.pageSize))

/** 跳转输入框的值 */
const jumpPage = ref('')

/** 跳转到指定页，自动 clamp 到合法范围 */
function go(target: number) {
  const page = Math.min(Math.max(1, target), totalPages.value)
  emit('go', page)
}

/** 跳转输入框回车确认 */
function jump() {
  const target = Number(jumpPage.value)
  if (target >= 1) {
    go(target)
    jumpPage.value = ''
  }
}
</script>

<template>
  <footer v-if="total" class="bastion-pagination crud-pagination">
    <!-- 左侧：每页条数 + 当前显示范围 -->
    <span class="pagination-info">
      每页 {{ pageSize }} 条，显示 {{ pageStart }}-{{ pageEnd }} / 共 {{ total }} 条
    </span>
    <!-- 中间：翻页按钮组 -->
    <div class="pagination-controls">
      <button class="secondary" :disabled="page <= 1" @click="go(1)">首页</button>
      <button class="secondary" :disabled="page <= 1" @click="go(page - 1)">上一页</button>
      <b>{{ page }} / {{ totalPages }}</b>
      <button class="secondary" :disabled="page >= totalPages" @click="go(page + 1)">下一页</button>
      <button class="secondary" :disabled="page >= totalPages" @click="go(totalPages)">尾页</button>
    </div>
    <!-- 右侧：跳转输入 -->
    <label class="pagination-jump">
      跳转到
      <input v-model="jumpPage" inputmode="numeric" placeholder="X" @keyup.enter="jump" />
      页
    </label>
    <button class="secondary" @click="jump">跳转</button>
  </footer>
</template>
