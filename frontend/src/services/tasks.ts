import { apiRequest } from './api'
import type { Task, TaskStatus } from '../types'

export interface SavedTask extends Task { status: TaskStatus; created_at: string }

export const listTasks = (_userId: string) => apiRequest<{ items: SavedTask[] }>('/tasks')
export const createTask = (_userId: string, task: Task) => apiRequest<SavedTask>('/tasks', {
  method: 'POST', body: JSON.stringify(task),
})
export const updateTaskStatus = (_userId: string, id: string, status: TaskStatus) => apiRequest<SavedTask>(`/tasks/${encodeURIComponent(id)}`, {
  method: 'PATCH', body: JSON.stringify({ status }),
})
export const deleteTask = (_userId: string, id: string) => apiRequest<void>(`/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' })
