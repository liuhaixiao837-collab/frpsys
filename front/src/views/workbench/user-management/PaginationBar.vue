<script setup lang="ts">
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-vue-next'
import CustomSelect from '../../../components/CustomSelect.vue'

withDefaults(defineProps<{
  pageSize: number
  currentPage: number
  totalPages: number
  pageStart: number
  pageEnd: number
  total: number
  jumpPage: string
  pageSizeOptions?: number[]
  unitLabel?: string
  detail?: string
}>(), {
  pageSizeOptions: () => [],
  unitLabel: '条',
  detail: '',
})

const emit = defineEmits<{
  'update:jumpPage': [value: string]
  'update:pageSize': [value: number]
  go: [page: number]
  move: [step: number]
  jump: []
}>()
</script>

<template>
  <footer v-if="total" class="pagination-bar">
    <label v-if="pageSizeOptions.length" class="pagination-size-picker">
      每页
      <CustomSelect
        :model-value="pageSize"
        aria-label="每页显示数量"
        @update:model-value="emit('update:pageSize', Number($event))"
      >
        <option v-for="option in pageSizeOptions" :key="option" :value="option">{{ option }}</option>
      </CustomSelect>
      {{ unitLabel }}
    </label>
    <span class="pagination-info">
      <template v-if="!pageSizeOptions.length">每页 {{ pageSize }} {{ unitLabel }}，</template>
      显示 {{ pageStart }}-{{ pageEnd }} / 共 {{ total }} {{ unitLabel }}<template v-if="detail">，{{ detail }}</template>
    </span>
    <button class="secondary" type="button" :disabled="currentPage <= 1" @click="emit('go', 1)">
      <ChevronsLeft :size="15" />首页
    </button>
    <button class="secondary" type="button" :disabled="currentPage <= 1" @click="emit('move', -1)">
      <ChevronLeft :size="15" />上一页
    </button>
    <b>{{ currentPage }} / {{ totalPages }}</b>
    <button class="secondary" type="button" :disabled="currentPage >= totalPages" @click="emit('move', 1)">
      下一页<ChevronRight :size="15" />
    </button>
    <button class="secondary" type="button" :disabled="currentPage >= totalPages" @click="emit('go', totalPages)">
      尾页<ChevronsRight :size="15" />
    </button>
    <label class="page-jump">
      跳转到
      <input
        :value="jumpPage"
        inputmode="numeric"
        :aria-label="`跳转页码，范围 1 到 ${totalPages}`"
        @input="emit('update:jumpPage', ($event.target as HTMLInputElement).value)"
        @keyup.enter="emit('jump')"
      />
      页
    </label>
    <button class="secondary" type="button" @click="emit('jump')">跳转</button>
  </footer>
</template>
