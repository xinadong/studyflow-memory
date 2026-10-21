import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import MemoryReference from '../components/MemoryReference.vue'
import { getMemory } from '../services/memories'
import type { MemoryItem } from '../types'
vi.mock('../services/memories', () => ({ getMemory: vi.fn() }))

describe('MemoryReference', () => {
  it('separates retrieved, used and candidate counts', () => {
    const wrapper = mount(MemoryReference, { props: { retrieved: ['a', 'b'], used: ['a'], candidates: ['c', 'd', 'e'] } })
    expect(wrapper.text()).toContain('2检索到')
    expect(wrapper.text()).toContain('1实际使用')
    expect(wrapper.text()).toContain('3待确认候选')
    expect(wrapper.text()).toContain('已使用 · a')
  })

  it('explains the default strategy when no memory was used', () => {
    const wrapper = mount(MemoryReference)
    expect(wrapper.text()).toContain('Agent 使用默认策略')
  })

  it('separates adopted constraints from nonbinding and unconfirmed memories and opens the original version', async () => {
    const original: MemoryItem = { id: 'original', user_id: 'demo-user', scope: 'global', course: '',
      memory_type: 'task_preference', content: '首选15分钟', preferred_minutes: 15, max_minutes: null,
      confidence: 0.8, confirmation_status: 'confirmed', active: true, use_count: 0, created_at: '2026-10-20T08:00:00Z' }
    vi.mocked(getMemory).mockResolvedValue({ ...original, confirmation_status: 'archived', replaced_by_id: 'new-version' })
    const wrapper = mount(MemoryReference, { props: { retrieved: ['original', 'cap', 'pending'], used: ['original'], candidates: ['pending'],
      evidence: [
        { memory: original, decision: 'used', reason: '本次使用了你确认的首选15分钟偏好，实际安排15分钟。' },
        { memory: { ...original, id: 'cap', preferred_minutes: null, max_minutes: 30 }, decision: 'retrieved_not_used', reason: '最多30分钟上限未触发。' },
        { memory: { ...original, id: 'pending', confirmation_status: 'pending' }, decision: 'pending', reason: '尚未确认，本轮未采用。' },
      ] } })
    expect(wrapper.get('.evidence-used').text()).toContain('确认的首选15分钟偏好')
    expect(wrapper.findAll('.evidence-used article')).toHaveLength(1)
    expect(wrapper.findAll('.evidence-details')[0].text()).toContain('上限未触发')
    expect(wrapper.findAll('.evidence-details')[1].text()).toContain('尚未确认')
    await wrapper.get('.evidence-used button').trigger('click')
    await flushPromises()
    const dialog = document.querySelector('.memory-dialog')!
    expect(dialog.textContent).toContain('本轮生成时引用的内容')
    expect(dialog.textContent).toContain('首选15分钟')
    expect(dialog.textContent).toContain('当前记录 · 已归档')
    expect(getMemory).toHaveBeenCalledWith('original')
    wrapper.unmount()
  })
})
