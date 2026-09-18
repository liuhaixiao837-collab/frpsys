<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import type { ResourceSchema } from '../../../resourceSchemas'
import ConfiguredCrudPanel from '../ConfiguredCrudPanel.vue'
import FrpReportCenter from './FrpReportCenter.vue'
import FrpTrafficReport from './FrpTrafficReport.vue'

const props = defineProps<{ schema?: ResourceSchema; items: any[]; page?: number; pageSize?: number; total?: number }>()
const emit = defineEmits<{ refresh: []; page: [page: number] }>()

const route = useRoute()
const isFrpReportCenter = computed(() => route.path === '/security/frp/reports')
const isFrpTrafficReport = computed(() => route.path === '/security/frp/traffic-reports')
</script>

<template>
  <section class="bastion-console frp-console">
    <FrpReportCenter v-if="isFrpReportCenter" />
    <FrpTrafficReport v-else-if="isFrpTrafficReport" />
    <ConfiguredCrudPanel
      v-else-if="props.schema"
      :schema="props.schema"
      :items="items"
      :page="page"
      :page-size="pageSize"
      :total="total"
      @page="emit('page', $event)"
      @refresh="emit('refresh')"
    />
    <section v-else class="bastion-panel">
      <div class="empty">请选择 FRP 管理菜单</div>
    </section>
  </section>
</template>
