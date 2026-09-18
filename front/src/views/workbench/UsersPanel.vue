<script setup lang="ts">
import UserManagementPanel from './user-management/UserManagementPanel.vue'

defineProps<{ initialTab?: 'users' | 'departments' | 'permissions' }>()
const emit = defineEmits<{ refresh: [] }>()
</script>

<template>
  <UserManagementPanel :initial-tab="initialTab || 'users'" @refresh="emit('refresh')" />
</template>
