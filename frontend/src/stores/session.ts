import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { Task } from '../types'

export const useSessionStore = defineStore('session', () => {
  const userId = ref(localStorage.getItem('studyflow-user') || 'demo-user')
  const course = ref('数据结构与算法')
  const goal = ref('学习图的 BFS')
  const knowledgePoint = ref('BFS')
  const selectedTask = ref<Task | null>(null)
  watch(userId, value => localStorage.setItem('studyflow-user', value))
  return { userId, course, goal, knowledgePoint, selectedTask }
})
