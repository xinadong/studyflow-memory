import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePlanStore } from '../stores/plan'
import { useSessionStore } from '../stores/session'
import { useTutorStore } from '../stores/tutor'
import { syncAccountScopedState } from '../stores/accountState'

describe('account-scoped browser state', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('clears another account\'s learning state before the next account loads', () => {
    const session = useSessionStore()
    const plan = usePlanStore()
    const tutor = useTutorStore()

    sessionStorage.setItem('studyflow-active-account-id', 'alice')
    session.course = 'Algorithms'
    session.setFocusProgress('alice-task', 600)
    plan.setPlan({
      tasks: [{ id: 'alice-task', title: 'BFS', course: 'Algorithms', description: '', duration_minutes: 15, task_type: 'study', knowledge_point: 'BFS' }],
      explanation: 'Alice plan', metrics: {}, retrieved_memory_ids: [], used_memory_ids: [], candidate_memory_ids: [],
    })
    tutor.start({ course: 'Algorithms', knowledgePoint: 'BFS', taskType: 'study', level: 'recall', material: 'Alice notes', task: null })
    tutor.addMessage({ role: 'assistant', content: 'Alice answer' })
    sessionStorage.setItem('studyflow-block', 'distraction')

    syncAccountScopedState('bob')

    expect(session.course).toBe('')
    expect(session.selectedTask).toBeNull()
    expect(session.focusTaskId).toBe('')
    expect(session.focusRemainingSeconds).toBeNull()
    expect(plan.plan).toBeNull()
    expect(plan.reviewTasks).toEqual([])
    expect(tutor.config).toBeNull()
    expect(tutor.messages).toEqual([])
    expect(sessionStorage.getItem('studyflow-focus-task-id')).toBeNull()
    expect(sessionStorage.getItem('studyflow-plan')).toBeNull()
    expect(sessionStorage.getItem('studyflow-tutor-messages')).toBeNull()
    expect(sessionStorage.getItem('studyflow-block')).toBeNull()
    expect(sessionStorage.getItem('studyflow-active-account-id')).toBe('bob')
  })

  it('clears account-scoped state when the session is logged out', () => {
    const session = useSessionStore()
    const tutor = useTutorStore()

    sessionStorage.setItem('studyflow-active-account-id', 'alice')
    session.course = 'Algorithms'
    tutor.start({ course: 'Algorithms', knowledgePoint: 'BFS', taskType: 'study', level: 'recall', material: 'Alice notes', task: null })

    syncAccountScopedState(null)

    expect(session.course).toBe('')
    expect(tutor.config).toBeNull()
    expect(tutor.messages).toEqual([])
    expect(sessionStorage.getItem('studyflow-active-account-id')).toBeNull()
    expect(sessionStorage.getItem('studyflow-tutor-config')).toBeNull()
  })
})
