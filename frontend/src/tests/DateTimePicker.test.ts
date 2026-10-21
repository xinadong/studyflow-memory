import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import DateTimePicker from '../components/DateTimePicker.vue'

describe('custom deadline picker', () => {
  let wrapper: VueWrapper | undefined
  afterEach(() => { wrapper?.unmount(); document.body.innerHTML = '' })
  async function click(label: string) {
    const button = document.querySelector<HTMLButtonElement>(`[aria-label="${label}"]`)
    expect(button).not.toBeNull()
    button!.click()
    await flushPromises()
  }

  it('opens from the field and commits only after the minute selection, including the same minute', async () => {
    wrapper = mount(DateTimePicker, { props: { modelValue: '2028-02-28T14:30' }, attachTo: document.body })
    await wrapper.get('.date-trigger').trigger('click')
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    await click('2028年2月29日')
    await click('9时')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    await click('30分')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['2028-02-29T09:30'])
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(document.activeElement).toBe(wrapper.get('.date-trigger').element)
  })

  it('navigates across years and pads single digit hours and minutes', async () => {
    wrapper = mount(DateTimePicker, { props: { modelValue: '2027-12-31T08:00' }, attachTo: document.body })
    await wrapper.get('.date-trigger').trigger('click')
    await click('下个月')
    expect(document.querySelector('.month-navigation')?.textContent).toContain('2028 年 1 月')
    await click('2028年1月2日')
    await click('7时')
    await click('5分')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['2028-01-02T07:05'])
  })

  it('dismisses on Escape or outside click without changing the saved deadline', async () => {
    wrapper = mount(DateTimePicker, { props: { modelValue: '' }, attachTo: document.body })
    await wrapper.get('.date-trigger').trigger('click')
    document.querySelector('.date-panel')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    await wrapper.get('.date-trigger').trigger('click')
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('can clear a saved deadline and respects the disabled state', async () => {
    wrapper = mount(DateTimePicker, { props: { modelValue: '2028-01-02T07:05' }, attachTo: document.body })
    await wrapper.get('.date-trigger').trigger('click')
    document.querySelector<HTMLButtonElement>('.clear-date')!.click()
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([''])
    await wrapper.setProps({ disabled: true })
    await wrapper.get('.date-trigger').trigger('click')
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })
})
