import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useSandboxStore = defineStore('sandbox', () => {
  const sandboxId = ref<string | null>(null)
  const isCreating = ref(false)
  const currentTaskId = ref<string | null>(null)
  const continueContext = ref(false)
  
  function setSandboxId(id: string) {
    sandboxId.value = id
  }
  
  function setCreating(creating: boolean) {
    isCreating.value = creating
  }
  
  function setCurrentTaskId(taskId: string | null) {
    currentTaskId.value = taskId
  }
  
  function setContinueContext(value: boolean) {
    continueContext.value = value
  }
  
  return {
    sandboxId,
    isCreating,
    currentTaskId,
    continueContext,
    setSandboxId,
    setCreating,
    setCurrentTaskId,
    setContinueContext
  }
})

export const useInteractionStore = defineStore('interaction', {
  state: () => ({
    interactionId: null as number | null,
    messages: [] as any[],
    status: 'idle' as 'idle' | 'running' | 'paused' | 'completed' | 'stopped' | 'failed',
  }),
  actions: {
    
  },
})
