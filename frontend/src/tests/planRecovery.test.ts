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

  it('adds ten minutes to the remaining time without replacing the hard task', () => {
    const plans = usePlanStore()
    const current = plans.previewTasks[0]

    const summary = plans.applyRecoveryAdjustment('too_hard', current.id, '先看基础示例。')

    expect(plans.previewTasks[0].id).toBe(current.id)
    expect(plans.statuses[current.id]).toBe('active')
    expect(current.duration_minutes).toBe(35)
    expect(summary).toContain('学不会')
    expect(summary).toContain('剩余约 35 分钟')
  })

  it('uses the captured remaining time as the base for a hard-task extension', () => {
    const plans = usePlanStore()
    const current = plans.previewTasks[0]

    plans.applyRecoveryAdjustment('too_hard', current.id, '给出更简单的提示。', 18)

    expect(current.duration_minutes).toBe(18)
    expect(plans.statuses[current.id]).toBe('active')
    expect(plans.previewTasks).toHaveLength(3)
  })

  it('records an unrelated distraction without changing task duration or order', () => {
    const plans = usePlanStore()
    const current = plans.previewTasks[1]
    const originalIds = plans.previewTasks.map(task => task.id)
    const originalMinutes = current.duration_minutes

    const summary = plans.applyRecoveryAdjustment('distraction', current.id, '记得取快递。')

    expect(current.duration_minutes).toBe(originalMinutes)
    expect(plans.previewTasks.map(task => task.id)).toEqual(originalIds)
    expect(plans.statuses[current.id]).toBe('active')
    expect(summary).toContain('原倒计时继续')
  })

  it('keeps a future review separate from the current task timeline', () => {
    const plans = usePlanStore()
    plans.setPlan({
      tasks: [{ id: 'today-1', title: '原有任务', description: '今天学习', duration_minutes: 25, task_type: 'study' }],
      explanation: '今日计划', metrics: {}, retrieved_memory_ids: [], used_memory_ids: [], candidate_memory_ids: [],
    })

    plans.addReviewTask({
      id: 'review-bfs', title: 'BFS · 对话后复习', description: '未来复习',
      duration_minutes: 12, task_type: 'review', knowledge_point: 'BFS',
      due_at: '2026-09-03T19:30:00.000Z',
    }, '根据对话证据安排。')

    expect(plans.plan?.tasks.map(task => task.id)).toEqual(['today-1'])
    expect(plans.reviewTasks.map(task => task.id)).toEqual(['review-bfs'])
  })
})
