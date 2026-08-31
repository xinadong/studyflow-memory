import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { Task } from '../types'

export const useSessionStore = defineStore('session', () => {
  const userId = ref(localStorage.getItem('studyflow-user') || 'demo-user')
  const course = ref('')
  const goal = ref('')
  const knowledgePoint = ref('')
  const selectedTask = ref<Task | null>(null)
  const focusTaskId = ref(sessionStorage.getItem('studyflow-focus-task-id') || '')
  const savedRemaining = Number(sessionStorage.getItem('studyflow-focus-remaining-seconds'))
  const focusRemainingSeconds = ref<number | null>(Number.isFinite(savedRemaining) && savedRemaining >= 0 ? savedRemaining : null)
  watch(userId, value => localStorage.setItem('studyflow-user', value))
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
  return { userId, course, goal, knowledgePoint, selectedTask, focusTaskId, focusRemainingSeconds, setFocusProgress, clearFocusProgress }
})
