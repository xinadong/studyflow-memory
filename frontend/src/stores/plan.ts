import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type { BlockType, PlanResponse, Task, TaskStatus } from '../types'

const saved = sessionStorage.getItem('studyflow-plan')
const savedStatuses = sessionStorage.getItem('studyflow-plan-statuses')
const savedAdjustment = sessionStorage.getItem('studyflow-plan-adjustment')
const savedReviews = sessionStorage.getItem('studyflow-review-tasks')

export const usePlanStore = defineStore('plan', () => {
  const plan = ref<PlanResponse | null>(saved ? JSON.parse(saved) : null)
  const previewTasks = ref<Task[]>([
    { id: 'preview-1', course: '数据结构与算法', title: '图的 BFS：队列与访问标记', description: '数据结构', duration_minutes: 25, task_type: 'study', knowledge_point: 'BFS' },
    { id: 'preview-2', course: '数据结构与算法', title: 'BFS 核心流程与复杂度', description: '现在推荐', duration_minutes: 25, task_type: 'study', knowledge_point: '图论' },
    { id: 'preview-3', course: '数据结构与算法', title: '迁移练习：最短路径建模', description: '可顺延至 21:30', duration_minutes: 20, task_type: 'study', knowledge_point: '最短路径' },
  ])
  const statuses = ref<Record<string, TaskStatus>>(savedStatuses ? JSON.parse(savedStatuses) : {})
  const reviewTasks = ref<Task[]>(savedReviews ? JSON.parse(savedReviews) : [])
  const localAdjustment = ref(savedAdjustment || '')
  const sameLocalDay = (left: Date, right: Date) => left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth() && left.getDate() === right.getDate()
  const misplacedReviews = (plan.value?.tasks ?? []).filter(task => task.task_type === 'review'
    && task.due_at && !sameLocalDay(new Date(task.due_at), new Date()))
  if (misplacedReviews.length && plan.value) {
    const merged = new Map(reviewTasks.value.map(task => [task.id, task]))
    misplacedReviews.forEach(task => merged.set(task.id, task))
    reviewTasks.value = [...merged.values()]
    plan.value.tasks = plan.value.tasks.filter(task => !misplacedReviews.some(review => review.id === task.id))
    misplacedReviews.forEach(task => { delete statuses.value[task.id] })
    if (!plan.value.tasks.length) plan.value = null
    if (plan.value) sessionStorage.setItem('studyflow-plan', JSON.stringify(plan.value))
    else sessionStorage.removeItem('studyflow-plan')
    sessionStorage.setItem('studyflow-plan-statuses', JSON.stringify(statuses.value))
  }
  const totalMinutes = computed(() => plan.value?.tasks.reduce((sum, task) => sum + task.duration_minutes, 0) ?? 0)
  watch(plan, value => value
    ? sessionStorage.setItem('studyflow-plan', JSON.stringify(value))
    : sessionStorage.removeItem('studyflow-plan'), { deep: true })
  watch(statuses, value => sessionStorage.setItem('studyflow-plan-statuses', JSON.stringify(value)), { deep: true })
  watch(reviewTasks, value => sessionStorage.setItem('studyflow-review-tasks', JSON.stringify(value)), { deep: true, immediate: true })
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
  function addReviewTask(task: Task, reason: string) {
    const existing = reviewTasks.value.find(item => item.id === task.id)
    if (existing) Object.assign(existing, task)
    else reviewTasks.value.push(task)
    localAdjustment.value = `伴学反馈已影响计划：已将「${task.knowledge_point}」复习加入 ${new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(new Date(task.due_at!))}。${reason}`
  }
  function applyRecoveryAdjustment(blockType: BlockType, taskId: string | undefined, action: string, adjustedRemainingMinutes?: number) {
    const tasks = plan.value?.tasks ?? previewTasks.value
    const currentIndex = tasks.findIndex(task => task.id === taskId)
    if (currentIndex < 0) return ''
    const current = tasks[currentIndex]
    if (!current) return ''

    if (blockType === 'too_hard') {
      const previousMinutes = current.duration_minutes
      current.duration_minutes = Math.min(120, adjustedRemainingMinutes ?? previousMinutes + 10)
      current.description = '根据“学不会”反馈，在释放杂念时的剩余时间上增加 10 分钟'
      statuses.value[current.id] = 'active'
      localAdjustment.value = `检测到“学不会/好难”：保留当前任务，并在释放杂念时的剩余时间基础上增加 10 分钟；现在剩余约 ${current.duration_minutes} 分钟。${action}`
    } else if (blockType === 'distraction') {
      statuses.value[current.id] = 'active'
      localAdjustment.value = `已记录与任务无关的杂念，未改变「${current.title}」的时长和顺序；返回后可从原倒计时继续。${action}`
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
  return { plan, previewTasks, reviewTasks, statuses, localAdjustment, totalMinutes, setPlan, addImportedTasks, addReviewTask, removeTask, applyRecoveryAdjustment }
})
