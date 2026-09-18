import { computed, ref, unref, watch, type ComputedRef, type MaybeRef } from 'vue'

/**
 * 封装 usePager 对应的前端业务处理步骤，供当前模块统一调用。
 * 参数：`items` 表示该步骤所需的业务参数；`pageSize` 表示该步骤所需的业务参数。
 * 返回：返回该步骤计算、查询或校验后的结果。
 * 副作用：不直接修改持久化数据。
 */
export function usePager<T>(items: ComputedRef<T[]>, pageSize: MaybeRef<number> = 10) {
  const currentPage = ref(1)
  const jumpPage = ref('1')
  const resolvedPageSize = computed(() => Math.max(1, Number(unref(pageSize)) || 10))
  const totalPages = computed(() => Math.max(1, Math.ceil(items.value.length / resolvedPageSize.value)))
  const paginatedItems = computed(() => {
    const start = (currentPage.value - 1) * resolvedPageSize.value
    return items.value.slice(start, start + resolvedPageSize.value)
  })
  const pageStart = computed(() => (items.value.length ? (currentPage.value - 1) * resolvedPageSize.value + 1 : 0))
  const pageEnd = computed(() => Math.min(currentPage.value * resolvedPageSize.value, items.value.length))

    /**
   * 封装 goPage 对应的前端业务处理步骤，供当前模块统一调用。
   * 参数：`page` 表示该步骤所需的业务参数。
   * 返回：无显式返回值。
   * 副作用：不直接修改持久化数据。
   */
function goPage(page: number) {
    currentPage.value = Math.min(totalPages.value, Math.max(1, page))
  }

    /**
   * 封装 movePage 对应的前端业务处理步骤，供当前模块统一调用。
   * 参数：`step` 表示该步骤所需的业务参数。
   * 返回：无显式返回值。
   * 副作用：不直接修改持久化数据。
   */
function movePage(step: number) {
    goPage(currentPage.value + step)
  }

    /**
   * 封装 applyJump 对应的前端业务处理步骤，供当前模块统一调用。
   * 参数：无。
   * 返回：无显式返回值。
   * 副作用：不直接修改持久化数据。
   */
function applyJump() {
    const page = Number.parseInt(jumpPage.value, 10)
    if (!Number.isFinite(page)) {
      jumpPage.value = String(currentPage.value)
      return
    }
    goPage(page)
  }

    /**
   * 将 resetPage 管理的界面或业务状态恢复到初始值。
   * 参数：无。
   * 返回：无显式返回值。
   * 副作用：可能修改当前组件状态、定时器或页面元素。
   */
function resetPage() {
    currentPage.value = 1
  }

  watch(totalPages, (value) => {
    if (currentPage.value > value) currentPage.value = value
  })

  watch(resolvedPageSize, resetPage)

  watch(currentPage, (value) => {
    jumpPage.value = String(value)
  }, { immediate: true })

  return {
    pageSize: resolvedPageSize,
    currentPage,
    jumpPage,
    totalPages,
    paginatedItems,
    pageStart,
    pageEnd,
    goPage,
    movePage,
    applyJump,
    resetPage,
  }
}
