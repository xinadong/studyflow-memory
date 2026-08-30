import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePlanStore } from '../stores/plan'

describe('recovery adjustments update the elastic task flow', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setActivePinia(createPinia())
  })

  it('reduces the current task and defers the next task when time is insufficient', () => {
    const plans = usePlanStore()
    const current = plans.previewTasks[0]
    const next = plans.previewTasks[1]

    const summary = plans.applyRecoveryAdjustment('time', current.id, '先完成最小目标。')

    expect(current.duration_minutes).toBe(15)
    expect(plans.statuses[current.id]).toBe('active')
    expect(plans.statuses[next.id]).toBe('deferred')
    expect(summary).toContain('时间不够')
  })

  it('inserts a foundation step and defers the hard task when the learner is stuck', () => {
    const plans = usePlanStore()
    const current = plans.previewTasks[0]

    const summary = plans.applyRecoveryAdjustment('too_hard', current.id, '先看基础示例。')

    expect(plans.previewTasks[0].description).toContain('低难度起步任务')
    expect(plans.previewTasks[0].duration_minutes).toBe(10)
    expect(plans.statuses[plans.previewTasks[0].id]).toBe('active')
    expect(plans.statuses[current.id]).toBe('deferred')
    expect(summary).toContain('学不会')
  })
})
