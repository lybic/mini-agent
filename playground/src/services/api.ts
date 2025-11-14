import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api'
})

export const createSandbox = () => {
  return apiClient.post('/sandbox/create', {})
}

export const runAgentInstruction = (instruction: string, sandboxId?: string, continueContext?: boolean, taskId?: string) => {
  return apiClient.post('/agent/run', { 
    instruction,
    sandbox_id: sandboxId,
    continue_context: continueContext,
    task_id: taskId
  }, {
    responseType: 'stream'
  })
}

export const getAgentInfo = () => {
  return apiClient.get('/agent/info')
}

export const cancelTask = (taskId: string) => {
  return apiClient.post('/agent/cancel', {
    task_id: taskId
  })
}

export const listTasks = (status?: string, limit?: number, offset?: number) => {
  return apiClient.get('/agent/task/list', {
    params: { status, limit, offset }
  })
}

export const getTaskStatus = (taskId: string) => {
  return apiClient.get(`/agent/task/status/${taskId}`)
}
