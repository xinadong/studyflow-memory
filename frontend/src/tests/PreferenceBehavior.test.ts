import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TodayView from '../views/TodayView.vue'
import TutorSessionView from '../views/TutorSessionView.vue'
import DateTimePicker from '../components/DateTimePicker.vue'
import { createPlan, checkUnderstanding } from '../services/agent'
import { submitFeedback } from '../services/memories'
import { useTutorStore } from '../stores/tutor'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('../services/agent', () => ({ createPlan: vi.fn(), checkUnderstanding: vi.fn() }))
vi.mock('../services/memories', () => ({ submitFeedback: vi.fn() }))

describe('temporary and long-term preference consent', () => {
  let wrapper: VueWrapper | undefined
  beforeEach(() => {
    vi.resetAllMocks()
    sessionStorage.clear(); localStorage.clear()
    setActivePinia(createPinia())
    vi.mocked(createPlan).mockResolvedValue({ tasks: [], explanation: 'Plan ready', metrics: {},
      retrieved_memory_ids: [], used_memory_ids: [], candidate_memory_ids: [] })
    vi.mocked(checkUnderstanding).mockResolvedValue({ level: 'recall', question: 'Try an example', feedback: 'Hint',
      missing_dimensions: [], guidance_type: 'hint', mastery_status: 'ongoing', visual_steps: [],
      retrieved_memory_ids: [], used_memory_ids: [], candidate_memory_ids: [], metrics: {} })
    vi.mocked(submitFeedback).mockResolvedValue({ feedback_id: 'saved', memories: [] })
  })
  afterEach(() => wrapper?.unmount())

  async function preparePlan() {
    wrapper = mount(TodayView)
    const inputs = wrapper.findAll('.settings-card input')
    await inputs[0].setValue('Algorithms')
    await inputs[1].setValue('BFS')
    await inputs[2].setValue(60)
    wrapper.findComponent(DateTimePicker).vm.$emit('update:modelValue', '2027-01-02T19:30')
    await wrapper.get('.glass-help.rose').trigger('click')
    await wrapper.get('.feedback-panel input').setValue('每次学习15分钟')
    return wrapper
  }
  function prepareHint() {
    const tutor = useTutorStore()
    tutor.start({ course: 'Algorithms', knowledgePoint: 'BFS', taskType: 'study', level: 'recall', material: '', task: null })
    tutor.addMessage({ role: 'assistant', content: 'Choose a hint', hintChoices: true })
    wrapper = mount(TutorSessionView)
    return wrapper
  }

  it('defaults to one plan only and consumes the temporary preference after success', async () => {
    const page = await preparePlan()
    await page.get('.feedback-panel').trigger('submit')
    expect(submitFeedback).not.toHaveBeenCalled()
    await page.get('.settings-card').trigger('submit')
    await flushPromises()
    expect(createPlan).toHaveBeenNthCalledWith(1, expect.objectContaining({ temporary_preference: '每次学习15分钟' }))
    await page.get('.settings-card').trigger('submit')
    await flushPromises()
    expect(createPlan).toHaveBeenNthCalledWith(2, expect.objectContaining({ temporary_preference: undefined }))
  })

  it('requires an explicit long-term choice and sends a global scope without course leakage', async () => {
    const page = await preparePlan()
    await page.findAll('.preference-lifetime button')[1].trigger('click')
    await page.get('.preference-scope select').setValue('global')
    await page.get('.feedback-panel').trigger('submit')
    await flushPromises()
    expect(submitFeedback).toHaveBeenCalledOnce()
    expect(submitFeedback).toHaveBeenCalledWith(expect.objectContaining({ scope: 'global', course: '', knowledge_point: undefined, explicit: true }))
  })

  it('never saves an ordinary hint choice as a long-term preference', async () => {
    const page = prepareHint()
    await page.findAll('.hint-choices button')[0].trigger('click')
    await flushPromises()
    expect(checkUnderstanding).toHaveBeenCalledWith(expect.objectContaining({ hint_preference: 'example' }))
    expect(submitFeedback).not.toHaveBeenCalled()
  })

  it('retries a failed long-term save without generating or losing the hint again', async () => {
    vi.mocked(submitFeedback).mockRejectedValueOnce(new Error('Save unavailable')).mockResolvedValueOnce({ feedback_id: 'saved', memories: [] })
    const page = prepareHint()
    await page.findAll('.preference-lifetime button')[1].trigger('click')
    await page.get('.preference-scope select').setValue('knowledge_point')
    await page.findAll('.hint-choices button')[0].trigger('click')
    await flushPromises()
    expect(page.text()).toContain('本次提示已生成，但长期偏好保存失败')
    expect(page.text()).toContain('Try an example')
    await page.get('.hint-memory-failure .link-button').trigger('click')
    await flushPromises()
    expect(checkUnderstanding).toHaveBeenCalledOnce()
    expect(submitFeedback).toHaveBeenCalledTimes(2)
    expect(submitFeedback).toHaveBeenLastCalledWith(expect.objectContaining({ scope: 'knowledge_point', course: 'Algorithms', knowledge_point: 'BFS' }))
    expect(page.text()).toContain('已保存为长期解释偏好')
  })
})
