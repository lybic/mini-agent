<script setup lang="ts">
import { NButton, NSpace, NTag } from 'naive-ui'
import { ref, onMounted } from 'vue'
import { getAgentInfo } from '@/services/api.ts'

const agentInfo = ref<any>(null)

onMounted(async () => {
  try {
    const response = await getAgentInfo()
    agentInfo.value = response.data
  } catch (error) {
    console.error('Failed to get agent info:', error)
  }
})
</script>

<template>
  <div style="display: flex; justify-content: space-between; align-items: center; width: 100%">
    <div style="display: flex; align-items: center; gap: 16px">
      <img src="../assets/logo.png" alt="lybic" style="height: 40px; width: auto" />
      <h2 style="margin: 0; color: #333">GUI Agent Playground</h2>
      <n-tag v-if="agentInfo" type="info" size="small">
        v{{ agentInfo.version }}
      </n-tag>
    </div>
  </div>
</template>
