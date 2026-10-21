import { apiRequest } from './api'
import type { Task, TaskStatus } from '../types'

export interface SavedTask extends Task { status: TaskStatus; created_at: string }

const ownerQuery = (userId: string) => new URLSearchParams({ user_id: userId })
export const listTasks = (userId: string) => apiRequest<{ items: SavedTask[] }>(`/tasks?${ownerQuery(userId)}`)
export const createTask = (userId: string, task: Task) => apiRequest<SavedTask>('/tasks', {
  method: 'POST', body: JSON.stringify({ ...task, user_id: userId }),
})
export const updateTaskStatus = (userId: string, id: string, status: TaskStatus) => apiRequest<SavedTask>(`/tasks/${encodeURIComponent(id)}?${ownerQuery(userId)}`, {
  method: 'PATCH', body: JSON.stringify({ status }),
})
export const deleteTask = (userId: string, id: string) => apiRequest<void>(`/tasks/${encodeURIComponent(id)}?${ownerQuery(userId)}`, { method: 'DELETE' })
