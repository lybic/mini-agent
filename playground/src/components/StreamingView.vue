<script setup lang="ts">
import { NCard, NEmpty } from 'naive-ui'
import { onBeforeUnmount, ref, watch, nextTick } from 'vue'
import {StreamingClient} from '@lybic/ui/streaming-client'
import axios from 'axios'
import { useSandboxStore } from '@/store/interaction'

const sandboxStore = useSandboxStore()
const streamingClient = ref<StreamingClient | null>(null)

async function getConnectionDetails(sandboxId: string): Promise<any> {
  const LYBIC_API_KEY = import.meta.env.VITE_LYBIC_API_KEY
  const LYBIC_ORG_ID = import.meta.env.VITE_LYBIC_ORG_ID

  return axios.get(`/lybic_api/orgs/${LYBIC_ORG_ID}/sandboxes/${sandboxId}`,
    {
      headers: {
        'x-api-key': LYBIC_API_KEY
      }
    }
  ).then((response) => {
    console.log('Connection details:', response.data.connectDetails)
    return response.data.connectDetails
  }).catch((error) => {
    console.error("Error fetching connection details:", error)
    return null
  })
}

async function initializeStreaming() {
  if (!sandboxStore.sandboxId) return

  console.log("Initializing streaming for sandbox ID:", sandboxStore.sandboxId)

  // 等待 DOM 更新完成
  await nextTick()

  const el = document.getElementById('lybic-ui-canvas')
  console.log('Canvas element:', el)

  if (!el) {
    console.error('Canvas element not found after nextTick')
    return
  }

  const connectionDetails = await getConnectionDetails(sandboxStore.sandboxId)
  console.log('Got connection details:', connectionDetails)

  if (!connectionDetails) {
    console.error('Failed to get connection details')
    return
  }

  try {
    console.log('Creating StreamingClient...')

    const cli = new StreamingClient(el,{
      videoFps:15,
      preferredVideoEncoding:4,
    })
    streamingClient.value = cli
    await streamingClient.value.start(connectionDetails)
    console.log('StreamingClient started successfully')

    streamingClient.value.errorEvent$.subscribe((error: any) => {
      console.error('Streaming error:', error)
    })
  } catch (error) {
    console.error('Failed to initialize streaming client:', error)
  }
}

watch(() => sandboxStore.sandboxId, (newId) => {
  if (newId && !streamingClient.value) {
    initializeStreaming()
  }
})

onBeforeUnmount(async () => {
  if (streamingClient.value) {
    await streamingClient.value.destroy()
  }
})
</script>

<template>
  <n-card
    title="Sandbox Stream"
    style="
      width: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      border-radius: 18px;
      height: 90%;
      box-shadow: 0 2px 12px rgba(33, 150, 243, 0.08);
      background: transparent;
    "
  >
    <div
      v-if="sandboxStore.sandboxId"
      style="
        width: 1280px;
        height: 720px;
        background: #000;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 16px;
        box-shadow: 0 2px 8px rgba(33, 150, 243, 0.1);
      "
    >
      <canvas id="lybic-ui-canvas" style="width: 100%; height: 100%; border-radius: 12px" tabindex="0"></canvas>
    </div>
    <n-empty v-else description="Please create a sandbox first" style="margin-top: 200px" />
  </n-card>
</template>

<style scoped>
.n-card {
  display: flex;
  flex-direction: column;
}
.n-card__content {
  flex-grow: 1;
  padding: 0;
}
</style>
