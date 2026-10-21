import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Task } from '../types'

export const useSessionStore = defineStore('session', () => {
  // Kept as a compatibility fallback for existing view/test callers. The
  // authenticated AppShell immediately replaces it with the server identity;
  // backend ownership never trusts this client-side value.
  const userId = ref('demo-user')
  const course = ref('')
  const goal = ref('')
  const knowledgePoint = ref('')
  const selectedTask = ref<Task | null>(null)
  const focusTaskId = ref(sessionStorage.getItem('studyflow-focus-task-id') || '')
  const savedRemaining = Number(sessionStorage.getItem('studyflow-focus-remaining-seconds'))
  const focusRemainingSeconds = ref<number | null>(Number.isFinite(savedRemaining) && savedRemaining >= 0 ? savedRemaining : null)
  function setFocusProgress(taskId: string, seconds: number) {
    focusTaskId.value = taskId
    focusRemainingSeconds.value = Math.max(0, Math.round(seconds))
    sessionStorage.setItem('studyflow-focus-task-id', taskId)
    sessionStorage.setItem('studyflow-focus-remaining-seconds', String(focusRemainingSeconds.value))
  }
  function clearFocusProgress() {
    focusTaskId.value = ''
    focusRemainingSeconds.value = null
    sessionStorage.removeItem('studyflow-focus-task-id')
    sessionStorage.removeItem('studyflow-focus-remaining-seconds')
  }
  function resetAccountState() {
    userId.value = ''
    course.value = ''
    goal.value = ''
    knowledgePoint.value = ''
    selectedTask.value = null
    clearFocusProgress()
  }
  return { userId, course, goal, knowledgePoint, selectedTask, focusTaskId, focusRemainingSeconds, setFocusProgress, clearFocusProgress, resetAccountState }
})
