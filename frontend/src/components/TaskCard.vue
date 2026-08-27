<script setup lang="ts">
import type { Task, TaskStatus } from '../types'
defineProps<{ task: Task; status: TaskStatus }>()
defineEmits<{ start: [task: Task]; status: [status: TaskStatus] }>()
const labels: Record<TaskStatus, string> = { pending: '待开始', active: '进行中', completed: '理解完成', deferred: '已顺延' }
</script>
<template>
  <article class="task-card">
    <div class="task-top"><div><span class="course">{{ task.knowledge_point || task.task_type }}</span><h3>{{ task.title }}</h3></div><span class="chip" :class="{ success: status === 'completed', warning: status === 'deferred' }">{{ labels[status] }}</span></div>
    <p>{{ task.description }}</p>
    <div class="task-meta"><strong>{{ task.duration_minutes }} 分钟</strong><select :value="status" aria-label="任务状态" @change="$emit('status', ($event.target as HTMLSelectElement).value as TaskStatus)"><option value="pending">待开始</option><option value="active">进行中</option><option value="completed">理解完成</option><option value="deferred">已顺延</option></select><button class="btn btn-secondary" @click="$emit('start', task)">开始学习 →</button></div>
  </article>
</template>
<style scoped>
.task-card { padding: 20px; border-radius: 20px; background: white; border: 1px solid var(--border); box-shadow: 0 8px 20px rgba(52,71,173,.07); }
.task-top,.task-meta{display:flex;align-items:center;justify-content:space-between;gap:12px}.course{font-size:11px;color:var(--brand);font-weight:800}h3{margin:5px 0 0;font-size:16px}p{margin:12px 0;color:var(--muted);font-size:13px;line-height:1.6}.task-meta strong{font-size:13px}.task-meta select{border:0;background:#f6f8ff;border-radius:10px;padding:8px;color:var(--muted)}
@media(max-width:620px){.task-meta{align-items:stretch;display:grid;grid-template-columns:1fr 1fr}.task-meta .btn{grid-column:1/-1}.task-top{align-items:flex-start}}
</style>
