import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import FocusTimerView from '../views/FocusTimerView.vue'
import TutorSessionView from '../views/TutorSessionView.vue'
import { usePlanStore } from '../stores/plan'
import { useSessionStore } from '../stores/session'
import { useTutorStore } from '../stores/tutor'
import { createTask, listTasks, updateTaskStatus } from '../services/tasks'
import type { SavedTask } from '../services/tasks'

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => navigation }))
vi.mock('../services/tasks', () => ({
  createTask: vi.fn(), listTasks: vi.fn(), updateTaskStatus: vi.fn(), deleteTask: vi.fn(),
}))

const task: SavedTask = {
  id: 'real-task', course: 'Algorithms', title: 'BFS', description: 'Practice',
  duration_minutes: 15, task_type: 'study', knowledge_point: 'BFS',
  status: 'pending', created_at: '2026-01-01T00:00:00Z',
}

describe('task buttons report server results', () => {
  let wrapper: VueWrapper | undefined
  beforeEach(async () => {
    vi.resetAllMocks()
    sessionStorage.clear()
    localStorage.clear()
    setActivePinia(createPinia())
    vi.mocked(listTasks).mockResolvedValue({ items: [task] })
    await usePlanStore().loadTasks('demo-user')
    useSessionStore().selectedTask = { ...task }
    useSessionStore().course = task.course!
  })
  afterEach(() => wrapper?.unmount())

  function prepareTutor() {
    const tutor = useTutorStore()
    tutor.start({ course: task.course!, knowledgePoint: 'BFS', taskType: 'study',
      level: 'recall', material: '', task })
    tutor.addMessage({ role: 'assistant', content: 'Completed practice' })
    tutor.masteryStatus = 'ready'
    return tutor
  }

  it('retains focus and shows an error when saving completion fails', async () => {
    vi.mocked(updateTaskStatus).mockRejectedValue(new Error('Save failed'))
    wrapper = mount(FocusTimerView)
    await wrapper.get('.finish-early').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Save failed')
    expect(useSessionStore().selectedTask?.id).toBe(task.id)
    expect(usePlanStore().statuses[task.id]).toBe('pending')
    expect(navigation.push).not.toHaveBeenCalled()
  })

  it('returns to the task list only after completion is saved', async () => {
    vi.mocked(updateTaskStatus).mockResolvedValue({ ...task, status: 'completed' })
    wrapper = mount(FocusTimerView)
    await wrapper.get('.finish-early').trigger('click')
    await flushPromises()
    expect(usePlanStore().statuses[task.id]).toBe('completed')
    expect(useSessionStore().selectedTask).toBeNull()
    expect(navigation.push).toHaveBeenCalledWith('/today')
  })

  it('also saves completion when finishing a tutor session', async () => {
    prepareTutor()
    vi.mocked(updateTaskStatus).mockResolvedValue({ ...task, status: 'completed' })
    wrapper = mount(TutorSessionView)
    await wrapper.get('.complete-card button').trigger('click')
    await wrapper.get('.dialog-actions .secondary').trigger('click')
    await flushPromises()
    expect(updateTaskStatus).toHaveBeenCalledWith('demo-user', task.id, 'completed')
    expect(navigation.push).toHaveBeenCalledWith('/today')
  })

  it('keeps a failed review unsaved and retries with the same ID', async () => {
    const tutor = prepareTutor()
    tutor.reviewRecommendation = { due_date: '2027-01-02', duration_minutes: 12, reason: 'Review later' }
    vi.mocked(createTask).mockRejectedValueOnce(new Error('Review failed'))
      .mockImplementationOnce(async (_, value) => ({ ...value, status: 'pending', created_at: task.created_at }))
    wrapper = mount(TutorSessionView)
    await wrapper.get('.review-card input').setValue('2027-01-02')
    await wrapper.get('.review-card button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Review failed')
    expect(wrapper.get('.review-card button').text()).toBe('确认加入计划')
    expect(usePlanStore().reviewTasks).toHaveLength(0)
    await wrapper.get('.review-card button').trigger('click')
    await flushPromises()
    expect(wrapper.get('.review-card button').text()).toBe('已加入计划')
    expect(usePlanStore().reviewTasks).toHaveLength(1)
    expect(vi.mocked(createTask).mock.calls[0][1].id).toBe(vi.mocked(createTask).mock.calls[1][1].id)
  })
})
