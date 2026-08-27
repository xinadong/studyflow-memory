import { apiRequest } from './api'
import type { ConfirmationStatus, FeedbackRequest, FeedbackResponse, MemoryItem, MemoryList, MemoryType } from '../types'

export interface MemoryFilters {
  user_id?: string
  course?: string
  memory_type?: MemoryType | ''
  confirmation_status?: ConfirmationStatus | ''
  active?: boolean
}

export async function listMemories(filters: MemoryFilters): Promise<MemoryList> {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value !== undefined) params.set(key, String(value))
  })
  return apiRequest<MemoryList>(`/memories?${params}`)
}

export const submitFeedback = (payload: FeedbackRequest) => apiRequest<FeedbackResponse>('/feedback', {
  method: 'POST', body: JSON.stringify(payload),
})

export const updateMemory = (id: string, payload: Partial<MemoryItem>) => apiRequest<MemoryItem>(`/memories/${id}`, {
  method: 'PATCH', body: JSON.stringify(payload),
})

export const deleteMemory = (id: string) => apiRequest<void>(`/memories/${id}`, { method: 'DELETE' })
