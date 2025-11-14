<script setup lang="ts">
import {
  NCard,
  NScrollbar,
  NInput,
  NButton,
  NList,
  NListItem,
  NSwitch,
  NSpace,
  NText,
  useMessage
} from 'naive-ui'
import { ref, computed, nextTick } from 'vue'
import { useSandboxStore } from '@/store/interaction'
import { createSandbox, runAgentInstruction, cancelTask } from '@/services/api'
const sandboxStore = useSandboxStore()

const message = useMessage()
const userInput = ref('')
const messages = ref<any[]>([])
const isRunning = ref(false)
const currentTaskId = ref<string | null>(null)
const scrollbarRef = ref<InstanceType<typeof NScrollbar> | null>(null)

const handleCreateSandbox = async () => {
  sandboxStore.setCreating(true)
  message.info('Creating sandbox...')
  
  try {
    const response = await createSandbox()
    if (response.data.success) {
      const sandboxId = response.data.sandbox_id
      sandboxStore.setSandboxId(sandboxId)
      message.success(`Sandbox created successfully! ID: ${sandboxId}`)
      messages.value.push({
        stage: 'System',
        message: `Sandbox created successfully!\nID: ${sandboxId}\nShape: ${response.data.shape}\nOS: ${response.data.os}`,
        timestamp: new Date().toISOString()
      })
      scrollToBottom()
    } else {
      message.error('Failed to create sandbox: ' + response.data.error)
    }
  } catch (error: any) {
    message.error('Error creating sandbox: ' + error.message)
  } finally {
    sandboxStore.setCreating(false)
  }
}

const handleSend = async () => {
  if (!userInput.value.trim()) return
  
  if (!sandboxStore.sandboxId) {
    message.warning('Please create a sandbox first!')
    return
  }
  
  const instruction = userInput.value.trim()
  userInput.value = ''
  
  messages.value.push({
    stage: 'User',
    message: instruction,
    timestamp: new Date().toISOString()
  })
  scrollToBottom()
  
  isRunning.value = true
  currentTaskId.value = null
  
  try {
    // Use fetch with streaming
    const requestBody: any = {
      instruction: instruction,
      sandbox_id: sandboxStore.sandboxId
    }
    
    // Add context continuation parameters if enabled
    if (sandboxStore.continueContext && sandboxStore.currentTaskId) {
      requestBody.continue_context = true
      requestBody.task_id = sandboxStore.currentTaskId
    }
    
    const response = await fetch('/api/agent/run', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody)
    })
    
    if (!response.ok) {
      const errorText = await response.text()
      throw new Error(`HTTP ${response.status}: ${errorText}`)
    }
    
    const reader = response.body?.getReader()
    const decoder = new TextDecoder()
    
    if (!reader) {
      throw new Error('No response body')
    }
    
    let hasError = false
    
    while (true) {
      const { done, value } = await reader.read()
      
      if (done) {
        break
      }
      
      const chunk = decoder.decode(value, { stream: true })
      const lines = chunk.split('\n')
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6))
            
            // Store task ID for cancellation and context continuation
            if (data.taskId) {
              if (!currentTaskId.value) {
                currentTaskId.value = data.taskId
                sandboxStore.setCurrentTaskId(data.taskId)
              }
            }
            
            if (data.error) {
              // 显示错误到界面和通知
              messages.value.push({
                stage: 'Error',
                message: `❌ Error: ${data.error}`,
                timestamp: new Date().toISOString()
              })
              scrollToBottom()
              message.error('Error: ' + data.error)
              hasError = true
              break
            } else if (data.done) {
              messages.value.push({
                stage: 'System',
                message: '✅ Task completed successfully!',
                timestamp: new Date().toISOString()
              })
              scrollToBottom()
              message.success('Task completed!')
            } else if (data.stage && data.message) {
              messages.value.push({
                stage: data.stage,
                message: data.message,
                timestamp: data.timestamp
              })
              scrollToBottom()
            }
          } catch (e) {
            console.error('Failed to parse SSE data:', e, 'Line:', line)
            messages.value.push({
              stage: 'Error',
              message: `❌ Failed to parse response: ${e}`,
              timestamp: new Date().toISOString()
            })
            scrollToBottom()
            hasError = true
          }
        }
      }
      
      // 如果遇到错误，跳出循环
      if (hasError) {
        break
      }
    }
    
  } catch (error: any) {
    // 捕获网络错误或其他异常
    const errorMsg = error.message || 'Unknown error'
    messages.value.push({
      stage: 'Error',
      message: `❌ Failed to run instruction: ${errorMsg}`,
      timestamp: new Date().toISOString()
    })
    scrollToBottom()
    message.error('Failed to run instruction: ' + errorMsg)
  } finally {
    // 无论成功还是失败，都恢复按钮状态
    isRunning.value = false
    currentTaskId.value = null
  }
}

const handleCancel = async () => {
  if (!currentTaskId.value) {
    message.warning('No running task to cancel')
    return
  }
  
  try {
    const response = await cancelTask(currentTaskId.value)
    if (response.data.success) {
      messages.value.push({
        stage: 'System',
        message: `🚫 Task cancelled: ${response.data.message}`,
        timestamp: new Date().toISOString()
      })
      scrollToBottom()
      message.success('Task cancelled successfully')
      isRunning.value = false
      currentTaskId.value = null
    } else {
      message.error('Failed to cancel task: ' + response.data.message)
    }
  } catch (error: any) {
    message.error('Error cancelling task: ' + error.message)
  }
}

const getCardColor = (stage: string) => {
  const colorMap: { [key: string]: string } = {
    'User': '#FFE0B2',
    'System': '#E0F7FA',
    'Error': '#FFCDD2',
    'manager_dag_translator': '#FFECF5',
    'manager_planner': '#F0F0F0',
    'Grounding': '#E6E0FF',
    'worker_planner': '#FFF5E6',
    'worker_reflection': '#FFEBFF'
  }
  return colorMap[stage] || '#FFFFFF'
}

const scrollToBottom = async () => {
  await nextTick()
  if (scrollbarRef.value) {
    scrollbarRef.value.scrollTo({ top: scrollbarRef.value.scrollbarInstRef?.contentRef?.scrollHeight, behavior: 'smooth' })
  }
}
</script>

<template>
  <n-card style="height: 90%; display: flex; flex-direction: column">
    <!-- Create Sandbox Button -->
    <div v-if="!sandboxStore.sandboxId" style="padding: 20px; text-align: center">
      <n-button
        type="primary"
        size="large"
        :loading="sandboxStore.isCreating"
        @click="handleCreateSandbox"
        style="background: #00b1e9; border: none"
      >
        {{ sandboxStore.isCreating ? 'Creating Sandbox...' : 'Create Sandbox' }}
      </n-button>
    </div>

    <!-- Messages Area -->
    <n-scrollbar ref="scrollbarRef" v-if="sandboxStore.sandboxId" style="flex-grow: 1; padding-right: 20px; overflow-y: auto; max-height: 70vh">
      <n-list>
        <n-list-item v-for="(msg, index) in messages" :key="index">
          <n-card :style="{ 'background-color': getCardColor(msg.stage) }">
            <p>
              <strong>{{ msg.stage }}</strong>
            </p>
            <p style="white-space: pre-wrap">{{ msg.message }}</p>
            <p v-if="msg.timestamp" style="font-size: 12px; color: #999; margin-top: 8px">
              {{ new Date(msg.timestamp).toLocaleTimeString() }}
            </p>
          </n-card>
        </n-list-item>
      </n-list>
    </n-scrollbar>

    <!-- Context Continuation Toggle -->
    <div v-if="sandboxStore.sandboxId" style="padding-top: 10px; width: 100%; display: flex; align-items: center; gap: 12px">
      <n-space align="center">
        <n-switch 
          v-model:value="sandboxStore.continueContext" 
          :disabled="isRunning || !sandboxStore.currentTaskId"
        />
        <n-text>
          Continue previous context
          <span v-if="sandboxStore.currentTaskId" style="color: #999; font-size: 12px">
            (Task: {{ sandboxStore.currentTaskId.substring(0, 8) }}...)
          </span>
        </n-text>
      </n-space>
    </div>

    <!-- Input Area -->
    <div v-if="sandboxStore.sandboxId" style="padding-top: 10px; width: 100%; display: flex; align-items: center; gap: 8px">
      <n-input
        v-model:value="userInput"
        type="textarea"
        placeholder="Send a message..."
        :disabled="isRunning"
        style="width: 100%; resize: none"
        @keydown.enter.prevent="handleSend"
      />
      <n-button
        v-if="!isRunning"
        type="primary"
        :disabled="!userInput.trim()"
        style="background: #00b1e9; color: #fff; border: none"
        @click="handleSend"
      >
        Send
      </n-button>
      <n-button
        v-else
        type="error"
        style="background: #ff4d4f; color: #fff; border: none"
        @click="handleCancel"
      >
        Cancel
      </n-button>
    </div>
  </n-card>
</template>

<style scoped></style>
