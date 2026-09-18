<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { api } from '../../../api'
import { normalize } from '../../../endpoints'
import DepartmentDirectory from './DepartmentDirectory.vue'
import PermissionPolicyDirectory from './PermissionPolicyDirectory.vue'
import UserDirectory from './UserDirectory.vue'
import type { DepartmentRow, PasswordPolicy, PermissionGroup, PermissionPolicyRow, RoleRow, UserRow } from './types'

type TabName = 'users' | 'departments' | 'permissions'

const props = defineProps<{ initialTab?: TabName }>()
const emit = defineEmits<{ refresh: [] }>()

const activeTab = ref<TabName>(props.initialTab || 'users')
const users = ref<UserRow[]>([])
const departments = ref<DepartmentRow[]>([])
const roles = ref<RoleRow[]>([])
const passwordPolicy = ref<PasswordPolicy>({
  min_length: 8,
  require_uppercase: true,
  require_lowercase: true,
  require_number: true,
  require_special: true,
  exclude_username: true,
  max_age_days: 30,
})
const permissionPolicies = ref<PermissionPolicyRow[]>([])
const permissionCatalog = ref<PermissionGroup[]>([])
const loading = ref(false)
const error = ref('')

/**
 * 从后端或当前状态加载 loadAll 所需的最新业务数据。
 * 参数：无。
 * 返回：无显式返回值。
 * 副作用：可能请求后端、修改持久化数据或更新全局状态。
 */
async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [userPayload, departmentPayload, policyPayload, catalogPayload, passwordPolicyPayload] = await Promise.all([
      api('/users/?page_size=500'),
      api('/orgs/tree/'),
      api('/permission-policies/'),
      api('/permission-catalog'),
      api('/users/password-policy/'),
    ])
    users.value = normalize(userPayload)
    departments.value = departmentPayload.items || normalize(departmentPayload)
    roles.value = []
    permissionPolicies.value = normalize(policyPayload)
    permissionCatalog.value = catalogPayload.items || []
    passwordPolicy.value = passwordPolicyPayload
    emit('refresh')
  } catch (reason: any) {
    error.value = reason.message || '加载用户管理数据失败'
  } finally {
    loading.value = false
  }
}

watch(() => props.initialTab, (tab) => {
  if (tab) activeTab.value = tab
})

onMounted(loadAll)
</script>

<template>
  <div class="user-mgmt">
    <main class="user-mgmt-main">
      <p v-if="error" class="form-error">{{ error }}</p>
      <UserDirectory
        v-else-if="activeTab === 'users'"
        :users="users"
        :departments="departments"
        :roles="roles"
        :password-policy="passwordPolicy"
        :loading="loading"
        @reload="loadAll"
      />
      <DepartmentDirectory
        v-else-if="activeTab === 'departments'"
        :users="users"
        :departments="departments"
        :roles="roles"
        :loading="loading"
        @reload="loadAll"
      />
      <PermissionPolicyDirectory
        v-else-if="activeTab === 'permissions'"
        :users="users"
        :departments="departments"
        :policies="permissionPolicies"
        :catalog="permissionCatalog"
        :loading="loading"
        @reload="loadAll"
      />
    </main>
  </div>
</template>
