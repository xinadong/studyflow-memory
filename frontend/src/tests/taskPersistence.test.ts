import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePlanStore } from '../stores/plan'
import { createTask, listTasks, updateTaskStatus, deleteTask } from '../services/tasks'
import type { SavedTask } from '../services/tasks'

vi.mock('../services/tasks', () => ({
  createTask: vi.fn(), listTasks: vi.fn(), updateTaskStatus: vi.fn(), deleteTask: vi.fn(),
}))

const task: SavedTask = {
  id: 'saved-study', course: 'Algorithms', title: 'BFS', description: 'Practice BFS',
  task_type: 'study', knowledge_point: 'BFS', duration_minutes: 15,
  status: 'pending', created_at: '2026-01-01T00:00:00Z',
}
const review: SavedTask = {
  ...task, id: 'saved-review', task_type: 'review',
  due_at: new Date(Date.now() + 7 * 86400000).toISOString(),
}

describe('tasks are backed by the server', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    sessionStorage.clear()
    setActivePinia(createPinia())
  })

  it('restores completed tasks and future reviews into a fresh store', async () => {
    vi.mocked(listTasks).mockResolvedValue({ items: [{ ...task, status: 'completed' }, review] })
    const plans = usePlanStore()
    await plans.loadTasks('alice')
    expect(plans.statuses[task.id]).toBe('completed')
    expect(plans.plan?.tasks.map(item => item.id)).toEqual([task.id])
    expect(plans.reviewTasks.map(item => item.id)).toEqual([review.id])
  })

  it('does not mark a task completed until the server confirms', async () => {
    vi.mocked(listTasks).mockResolvedValue({ items: [task] })
    let resolve!: (task: SavedTask) => void
    vi.mocked(updateTaskStatus).mockReturnValue(new Promise(done => { resolve = done }))
    const plans = usePlanStore()
    await plans.loadTasks('alice')
    const saving = plans.completeTask('alice', task)
    expect(plans.statuses[task.id]).toBe('pending')
    resolve({ ...task, status: 'completed' })
    await saving
    expect(updateTaskStatus).toHaveBeenCalledWith('alice', task.id, 'completed')
    expect(plans.statuses[task.id]).toBe('completed')
  })

  it('keeps the task incomplete on failure and permits retry', async () => {
    vi.mocked(listTasks).mockResolvedValue({ items: [task] })
    vi.mocked(updateTaskStatus).mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ ...task, status: 'completed' })
    const plans = usePlanStore()
    await plans.loadTasks('alice')
    await expect(plans.completeTask('alice', task)).rejects.toThrow('offline')
    expect(plans.statuses[task.id]).toBe('pending')
    await plans.completeTask('alice', task)
    expect(plans.statuses[task.id]).toBe('completed')
  })

  it('only adds a review after successful persistence', async () => {
    vi.mocked(createTask).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(review)
    const plans = usePlanStore()
    await expect(plans.addReviewTask('alice', review, 'Review later')).rejects.toThrow('offline')
    expect(plans.reviewTasks).toEqual([])
    await plans.addReviewTask('alice', review, 'Review later')
    expect(plans.reviewTasks.map(item => item.id)).toEqual([review.id])
    expect(plans.localAdjustment).toContain('BFS')
  })

  it('waits for deletion before removing the task from the UI', async () => {
    vi.mocked(listTasks).mockResolvedValue({ items: [task] })
    vi.mocked(deleteTask).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(undefined)
    const plans = usePlanStore()
    await plans.loadTasks('alice')
    await expect(plans.removeSavedTask('alice', task)).rejects.toThrow('offline')
    expect(plans.plan?.tasks).toHaveLength(1)
    await plans.removeSavedTask('alice', task)
    expect(plans.plan).toBeNull()
  })

  it('does not let an older load overwrite a newly selected user', async () => {
    let resolve!: (value: { items: SavedTask[] }) => void
    vi.mocked(listTasks).mockReturnValueOnce(new Promise(done => { resolve = done }))
      .mockResolvedValueOnce({ items: [] })
    const plans = usePlanStore()
    const oldLoad = plans.loadTasks('alice')
    await plans.loadTasks('bob')
    resolve({ items: [task] })
    await oldLoad
    expect(plans.plan).toBeNull()
    expect(plans.reviewTasks).toEqual([])
  })
})
