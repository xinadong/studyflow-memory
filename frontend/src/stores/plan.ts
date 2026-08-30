import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type { PlanResponse, Task, TaskStatus } from '../types'

const saved = sessionStorage.getItem('studyflow-plan')

export const usePlanStore = defineStore('plan', () => {
  const plan = ref<PlanResponse | null>(saved ? JSON.parse(saved) : null)
  const previewTasks = ref<Task[]>([
    { id: 'preview-1', course: '数据结构与算法', title: '图的 BFS：队列与访问标记', description: '数据结构', duration_minutes: 25, task_type: 'study', knowledge_point: 'BFS' },
    { id: 'preview-2', course: '数据结构与算法', title: 'BFS 核心流程与复杂度', description: '现在推荐', duration_minutes: 25, task_type: 'study', knowledge_point: '图论' },
    { id: 'preview-3', course: '数据结构与算法', title: '迁移练习：最短路径建模', description: '可顺延至 21:30', duration_minutes: 20, task_type: 'study', knowledge_point: '最短路径' },
  ])
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
  function addImportedTasks(tasks: Task[]) {
    if (!tasks.length) return
    if (!plan.value) {
      plan.value = {
        tasks: [...previewTasks.value],
        explanation: '已导入的任务会加入今日弹性任务流，可继续生成计划或直接开始。',
        metrics: {},
        retrieved_memory_ids: [],
        used_memory_ids: [],
        candidate_memory_ids: [],
      }
      statuses.value = {
        [previewTasks.value[0]?.id]: 'completed',
        [previewTasks.value[1]?.id]: 'pending',
        [previewTasks.value[2]?.id]: 'deferred',
      }
    }
    plan.value.tasks.push(...tasks)
    tasks.forEach(task => { statuses.value[task.id] = 'pending' })
  }
  function removeTask(taskId: string) {
    if (!plan.value) {
      previewTasks.value = previewTasks.value.filter(task => task.id !== taskId)
      return
    }
    plan.value.tasks = plan.value.tasks.filter(task => task.id !== taskId)
    delete statuses.value[taskId]
    if (!plan.value.tasks.length) plan.value = null
  }
  return { plan, previewTasks, statuses, localAdjustment, totalMinutes, setPlan, addImportedTasks, removeTask }
})
