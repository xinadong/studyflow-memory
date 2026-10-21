import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import MemoryCenterView from '../views/MemoryCenterView.vue'
import { listMemories, submitFeedback, updateMemory } from '../services/memories'
import { useSessionStore } from '../stores/session'
import type { MemoryItem } from '../types'

vi.mock('../services/memories', () => ({ listMemories: vi.fn(), submitFeedback: vi.fn(), updateMemory: vi.fn(), deleteMemory: vi.fn() }))
const memory: MemoryItem = { id: 'memory-1', user_id: 'demo-user', memory_type: 'task_preference', course: 'Algorithms',
  content: '15 minutes', confidence: 0.8, confirmation_status: 'pending', active: true,
  use_count: 0, created_at: '2026-10-20T08:00:00Z' }
describe('memory management scope and updates', () => {
  let wrapper: VueWrapper | undefined
  beforeEach(() => {
    vi.resetAllMocks()
    localStorage.clear()
    setActivePinia(createPinia())
    vi.mocked(listMemories).mockResolvedValue({ items: [memory], total: 1 })
  })
  afterEach(() => wrapper?.unmount())

  it('saves the explicit form scope instead of inheriting a previous learning session', async () => {
    useSessionStore().course = 'Previous course'
    useSessionStore().knowledgePoint = 'Previous point'
    vi.mocked(submitFeedback).mockResolvedValue({ feedback_id: 'feedback-1', memories: [memory] })
    wrapper = mount(MemoryCenterView, { props: { embedded: true } })
    await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false)
    await wrapper.get('.embedded-heading button').trigger('click')
    expect((wrapper.get('#feedback-course').element as HTMLInputElement).value).toBe('')
    await wrapper.get('#feedback-course').setValue('Algorithms')
    await wrapper.get('#feedback').setValue('15 minutes')
    await wrapper.get('#type').setValue('task_preference')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(submitFeedback).toHaveBeenCalledWith(expect.objectContaining({
      course: 'Algorithms', knowledge_point: undefined, content: '15 minutes',
    }))
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('notifies the overview after confirming a memory', async () => {
    vi.mocked(updateMemory).mockResolvedValue({ ...memory, confirmation_status: 'confirmed' })
    wrapper = mount(MemoryCenterView, { props: { embedded: true } })
    await flushPromises()
    const confirm = wrapper.findAll('.memory-card button').find(button => button.text() === '确认')
    expect(confirm).toBeDefined()
    await confirm!.trigger('click')
    await flushPromises()
    expect(updateMemory).toHaveBeenCalledWith(memory.id, { confirmation_status: 'confirmed' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })
})
