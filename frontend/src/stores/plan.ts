import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type { PlanResponse, TaskStatus } from '../types'

const saved = sessionStorage.getItem('studyflow-plan')

export const usePlanStore = defineStore('plan', () => {
  const plan = ref<PlanResponse | null>(saved ? JSON.parse(saved) : null)
  const statuses = ref<Record<string, TaskStatus>>({})
  const localAdjustment = ref('')
  const totalMinutes = computed(() => plan.value?.tasks.reduce((sum, task) => sum + task.duration_minutes, 0) ?? 0)
  watch(plan, value => value
    ? sessionStorage.setItem('studyflow-plan', JSON.stringify(value))
    : sessionStorage.removeItem('studyflow-plan'), { deep: true })
  function setPlan(value: PlanResponse) {
    plan.value = value
    statuses.value = Object.fromEntries(value.tasks.map(task => [task.id, 'pending']))
  }
  return { plan, statuses, localAdjustment, totalMinutes, setPlan }
})
