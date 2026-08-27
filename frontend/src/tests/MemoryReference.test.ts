import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MemoryReference from '../components/MemoryReference.vue'

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
})
