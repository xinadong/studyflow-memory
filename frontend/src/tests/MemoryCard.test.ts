import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MemoryCard from '../components/MemoryCard.vue'
import type { MemoryItem } from '../types'

const memory: MemoryItem = { id: 'duration', user_id: 'demo-user', memory_type: 'task_preference', scope: 'global', course: '',
  content: '首选15分钟，最多30分钟', preferred_minutes: 15, max_minutes: 30, confidence: 0.8,
  confirmation_status: 'confirmed', active: true, use_count: 0, created_at: '2026-10-20T08:00:00Z' }

describe('structured preference editing', () => {
  async function edit() {
    const wrapper = mount(MemoryCard, { props: { memory } })
    await wrapper.findAll('button').find(button => button.text() === '编辑')!.trigger('click')
    return wrapper
  }
  it('lets changed text be reparsed rather than sending unchanged stale numbers', async () => {
    const wrapper = await edit()
    await wrapper.get('textarea').setValue('首选20分钟，最多30分钟')
    await wrapper.findAll('button').find(button => button.text() === '保存')!.trigger('click')
    expect(wrapper.emitted('edit')?.[0]).toEqual([{ content: '首选20分钟，最多30分钟' }])
    wrapper.unmount()
  })
  it('submits explicit numeric changes and supports clearing the maximum', async () => {
    const wrapper = await edit()
    await wrapper.get('[aria-label="最多时长（分钟）"]').setValue('')
    await wrapper.findAll('button').find(button => button.text() === '保存')!.trigger('click')
    expect(wrapper.emitted('edit')?.[0]).toEqual([{ content: memory.content, preferred_minutes: 15, max_minutes: null }])
    wrapper.unmount()
  })
  it('shows an error rather than silently saving an impossible duration', async () => {
    const wrapper = await edit()
    await wrapper.get('[aria-label="首选时长（分钟）"]').setValue(40)
    await wrapper.findAll('button').find(button => button.text() === '保存')!.trigger('click')
    expect(wrapper.text()).toContain('首选时长不能超过最多时长')
    expect(wrapper.emitted('edit')).toBeUndefined()
    wrapper.unmount()
  })
})
