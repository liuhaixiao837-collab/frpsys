<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { useSlots } from 'vue'

defineProps<{
  open: boolean
  title: string
  description?: string
  width?: string
  dialogClass?: string
}>()

const emit = defineEmits<{ close: [] }>()
const slots = useSlots()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" :class="dialogClass" @click.self="emit('close')">
      <section class="modal-card" :style="{ width: width ? `min(100%, ${width})` : undefined, maxWidth: width || '760px' }" role="dialog" aria-modal="true">
        <header class="modal-head">
          <div>
            <h2>{{ title }}</h2>
            <p v-if="description">{{ description }}</p>
          </div>
          <button class="icon-button" type="button" title="关闭" @click="emit('close')">
            <X :size="17" />
          </button>
        </header>
        <div class="modal-body">
          <slot />
        </div>
        <footer v-if="slots.footer" class="modal-footer">
          <slot name="footer" />
        </footer>
      </section>
    </div>
  </Teleport>
</template>
