import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type { BlockType, PlanResponse, Task, TaskStatus } from '../types'

const saved = sessionStorage.getItem('studyflow-plan')
const savedStatuses = sessionStorage.getItem('studyflow-plan-statuses')
const savedAdjustment = sessionStorage.getItem('studyflow-plan-adjustment')

export const usePlanStore = defineStore('plan', () => {
  const plan = ref<PlanResponse | null>(saved ? JSON.parse(saved) : null)
  const previewTasks = ref<Task[]>([
    { id: 'preview-1', course: '数据结构与算法', title: '图的 BFS：队列与访问标记', description: '数据结构', duration_minutes: 25, task_type: 'study', knowledge_point: 'BFS' },
    { id: 'preview-2', course: '数据结构与算法', title: 'BFS 核心流程与复杂度', description: '现在推荐', duration_minutes: 25, task_type: 'study', knowledge_point: '图论' },
    { id: 'preview-3', course: '数据结构与算法', title: '迁移练习：最短路径建模', description: '可顺延至 21:30', duration_minutes: 20, task_type: 'study', knowledge_point: '最短路径' },
  ])
  const statuses = ref<Record<string, TaskStatus>>(savedStatuses ? JSON.parse(savedStatuses) : {})
  const localAdjustment = ref(savedAdjustment || '')
  const totalMinutes = computed(() => plan.value?.tasks.reduce((sum, task) => sum + task.duration_minutes, 0) ?? 0)
  watch(plan, value => value
    ? sessionStorage.setItem('studyflow-plan', JSON.stringify(value))
    : sessionStorage.removeItem('studyflow-plan'), { deep: true })
  watch(statuses, value => sessionStorage.setItem('studyflow-plan-statuses', JSON.stringify(value)), { deep: true })
  watch(localAdjustment, value => value
    ? sessionStorage.setItem('studyflow-plan-adjustment', value)
    : sessionStorage.removeItem('studyflow-plan-adjustment'))
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
  function applyRecoveryAdjustment(blockType: BlockType, taskId: string | undefined, action: string) {
    const tasks = plan.value?.tasks ?? previewTasks.value
    const currentIndex = Math.max(0, tasks.findIndex(task => task.id === taskId))
    const current = tasks[currentIndex]
    if (!current) return ''

    if (blockType === 'too_hard') {
      const helper: Task = {
        id: `recovery-step-${Date.now()}`,
        course: current.course,
        title: `${current.knowledge_point || current.title} · 基础回顾`,
        description: '根据“学不会”反馈新增的低难度起步任务',
        duration_minutes: 10,
        task_type: current.task_type,
        knowledge_point: current.knowledge_point,
        due_at: current.due_at,
      }
      tasks.splice(currentIndex, 0, helper)
      statuses.value[helper.id] = 'active'
      statuses.value[current.id] = 'deferred'
      localAdjustment.value = `检测到“学不会”：已先加入 10 分钟基础回顾，并将「${current.title}」顺延。${action}`
    } else {
      const previousMinutes = current.duration_minutes
      const nextMinutes = blockType === 'time' ? Math.max(10, Math.min(15, previousMinutes)) : Math.max(10, Math.min(15, previousMinutes))
      current.duration_minutes = nextMinutes
      current.description = blockType === 'time'
        ? '根据“时间不够”反馈压缩为本轮最小核心任务'
        : blockType === 'fatigue'
          ? '根据疲劳反馈降低本轮强度'
          : '根据分心反馈缩短为一个可完成的小步骤'
      statuses.value[current.id] = 'active'
      const nextTask = tasks.find((task, index) => index > currentIndex && (statuses.value[task.id] || 'pending') === 'pending')
      if (nextTask) statuses.value[nextTask.id] = 'deferred'
      const signal = blockType === 'time' ? '时间不够' : blockType === 'fatigue' ? '状态疲劳' : '注意力受干扰'
      localAdjustment.value = `检测到“${signal}”：已将「${current.title}」从 ${previousMinutes} 分钟调整为 ${nextMinutes} 分钟${nextTask ? `，并顺延「${nextTask.title}」` : ''}。${action}`
    }
    return localAdjustment.value
  }
  return { plan, previewTasks, statuses, localAdjustment, totalMinutes, setPlan, addImportedTasks, removeTask, applyRecoveryAdjustment }
})
