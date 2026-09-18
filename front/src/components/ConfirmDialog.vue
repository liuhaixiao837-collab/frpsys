<script setup lang="ts">
import { AlertTriangle } from 'lucide-vue-next'

defineProps<{
  open: boolean
  title: string
  message: string
  confirmText?: string
  loading?: boolean
  dialogClass?: string
}>()

const emit = defineEmits<{ cancel: []; confirm: [] }>()

const cancelText = '\u53d6\u6d88'
const loadingText = '\u5904\u7406\u4e2d...'
const defaultConfirmText = '\u786e\u8ba4\u5220\u9664'
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="confirm-dialog-backdrop" :class="dialogClass" @click.self="emit('cancel')">
      <section class="confirm-dialog-card" role="dialog" aria-modal="true">
        <AlertTriangle :size="28" />
        <h2>{{ title }}</h2>
        <p>{{ message }}</p>
        <slot />
        <footer>
          <button class="secondary" type="button" @click="emit('cancel')">{{ cancelText }}</button>
          <button class="danger-button" type="button" :disabled="loading" @click="emit('confirm')">
            {{ loading ? loadingText : (confirmText || defaultConfirmText) }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
