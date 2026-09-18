<script setup lang="ts">
import { Eye, EyeOff } from 'lucide-vue-next'
import { ref } from 'vue'

withDefaults(defineProps<{
  modelValue?: string
  placeholder?: string
  autocomplete?: string
  required?: boolean
  disabled?: boolean
  readonly?: boolean
  minLength?: number
  maxLength?: number
}>(), {
  modelValue: '',
  placeholder: '',
  autocomplete: 'new-password',
  required: false,
  disabled: false,
  readonly: false,
  minLength: undefined,
  maxLength: undefined,
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const visible = ref(false)
</script>

<template>
  <span class="password-input">
    <input
      :value="modelValue"
      :type="visible ? 'text' : 'password'"
      :placeholder="placeholder"
      :autocomplete="autocomplete"
      :required="required"
      :disabled="disabled"
      :readonly="readonly"
      :minlength="minLength"
      :maxlength="maxLength"
      spellcheck="false"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <button
      class="password-visibility-button"
      type="button"
      :title="visible ? '隐藏密码' : '显示密码'"
      :aria-label="visible ? '隐藏密码' : '显示密码'"
      :disabled="disabled"
      @click="visible = !visible"
    >
      <EyeOff v-if="visible" :size="16" />
      <Eye v-else :size="16" />
      <span>{{ visible ? '隐藏' : '显示' }}</span>
    </button>
  </span>
</template>
