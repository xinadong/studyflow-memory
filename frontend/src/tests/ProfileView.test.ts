import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ProfileView from '../views/ProfileView.vue'
import { listTasks } from '../services/tasks'
import { listMemories } from '../services/memories'
import type { SavedTask } from '../services/tasks'
import type { MemoryItem } from '../types'

vi.mock('../services/tasks', () => ({ listTasks: vi.fn() }))
vi.mock('../services/memories', () => ({ listMemories: vi.fn() }))
const task: SavedTask = { id: 'study-1', title: 'BFS practice', course: 'Algorithms', task_type: 'study',
  description: '', duration_minutes: 15, status: 'completed', created_at: '2026-10-20T08:00:00Z' }
const memory: MemoryItem = { id: 'memory-1', user_id: 'demo-user', memory_type: 'task_preference', course: 'Algorithms',
  content: 'Study for 15 minutes', confidence: 0.8, confirmation_status: 'confirmed', active: true,
  use_count: 2, created_at: '2026-10-20T08:00:00Z' }

describe('personal center uses saved records', () => {
  let wrapper: VueWrapper | undefined
  beforeEach(() => {
    vi.resetAllMocks()
    localStorage.clear()
    vi.mocked(listTasks).mockResolvedValue({ items: [task, { ...task, id: 'study-2', title: 'Graph practice', status: 'pending' },
      { ...task, id: 'review-1', title: 'BFS review', task_type: 'review', status: 'pending', due_at: '2026-10-25T11:30:00Z' }] })
    vi.mocked(listMemories).mockResolvedValue({ items: [memory, { ...memory, id: 'memory-2', confirmation_status: 'pending' }], total: 2 })
  })
  afterEach(() => wrapper?.unmount())
  async function open(path = '/profile') {
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/profile', component: ProfileView },
      { path: '/today', component: { template: '<div />' } },
      { path: '/study', component: { template: '<div />' } },
    ] })
    await router.push(path)
    await router.isReady()
    wrapper = mount(ProfileView, { global: { plugins: [createPinia(), router], stubs: {
      MemoryCenterView: { template: '<button class="memory-change" @click="$emit(\'changed\')">Mock memory editor</button>', emits: ['changed'] },
    } } })
    await flushPromises()
    return wrapper
  }

  it('counts actual study tasks, pending reviews and confirmed memories without fabricated statistics', async () => {
    const page = await open()
    expect(page.findAll('.summary-copy strong').map(item => item.text())).toEqual(['2项', '1项', '1条'])
    expect(page.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('33')
    expect(page.text()).not.toContain('14.2h')
    expect(page.text()).not.toContain('86%')
    expect(page.find('.edit-button').exists()).toBe(false)
  })

  it('separates review and study records and filters by status and search', async () => {
    const page = await open('/profile#tasks')
    expect(page.findAll('.record-list article')).toHaveLength(2)
    await page.findAll('.record-filters button')[2].trigger('click')
    expect(page.findAll('.record-list article')).toHaveLength(1)
    await page.get('input[type="search"]').setValue('unmatched')
    expect(page.text()).toContain('没有符合条件的记录')
    await page.get('#tab-reviews').trigger('click')
    await flushPromises()
    expect(page.findAll('.record-list article')).toHaveLength(1)
    expect(page.get('.record-list').text()).toContain('BFS review')
  })

  it('opens memory deep links and refreshes totals after a memory mutation', async () => {
    const page = await open('/profile#memories')
    expect(page.find('.memory-change').exists()).toBe(true)
    vi.mocked(listMemories).mockResolvedValueOnce({ items: [memory], total: 1 })
    await page.get('.memory-change').trigger('click')
    await flushPromises()
    expect(page.get('#tab-memories').text()).toContain('1')
  })

  it('shows load failures rather than reporting zero activity', async () => {
    vi.mocked(listTasks).mockRejectedValueOnce(new Error('Records unavailable'))
    const page = await open()
    expect(page.text()).toContain('Records unavailable')
    expect(page.find('.summary-grid').exists()).toBe(false)
  })
})
