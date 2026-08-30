<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import { createPlan } from '../services/agent'
import { errorMessage } from '../services/api'
import { submitFeedback } from '../services/memories'
import { usePlanStore } from '../stores/plan'
import { useSessionStore } from '../stores/session'
import type { Task, TaskStatus } from '../types'

const router = useRouter()
const session = useSessionStore()
const plans = usePlanStore()
const busy = ref(false)
const error = ref('')
const showFeedback = ref(false)
const preference = ref('我希望每个学习任务控制在 15 分钟以内')
const feedbackState = ref('')
const form = reactive({ available_minutes: 25, task_type: 'study' })

const dateText = computed(() => new Intl.DateTimeFormat('zh-CN', {
  month: 'long', day: 'numeric', weekday: 'short',
}).format(new Date()))
const completed = computed(() => Object.values(plans.statuses).filter(value => value === 'completed').length)
const deferred = computed(() => Object.values(plans.statuses).filter(value => value === 'deferred').length)
const pending = computed(() => plans.plan ? Math.max(plans.plan.tasks.length - completed.value, 0) : 3)
const primaryTask = computed(() => plans.plan?.tasks[0])
const timelineTasks = computed<Task[]>(() => plans.plan?.tasks.length ? plans.plan.tasks : [
  { id: 'preview-1', title: '图的 BFS：队列与访问标记', description: '数据结构', duration_minutes: 25, task_type: 'study', knowledge_point: 'BFS' },
  { id: 'preview-2', title: 'BFS 核心流程与复杂度', description: '现在推荐', duration_minutes: 25, task_type: 'study', knowledge_point: '图论' },
  { id: 'preview-3', title: '迁移练习：最短路径建模', description: '可顺延至 21:30', duration_minutes: 20, task_type: 'study', knowledge_point: '最短路径' },
] as Task[])

function taskStatus(task: Task, index: number): TaskStatus {
  if (plans.plan) return plans.statuses[task.id] || 'pending'
  return index === 0 ? 'completed' : index === 2 ? 'deferred' : 'pending'
}
function statusText(status: TaskStatus) {
  return ({ completed: '理解完成', active: '进行中', deferred: '可顺延', pending: '待开始' } as Record<TaskStatus, string>)[status]
}
async function generatePlan() {
  busy.value = true
  error.value = ''
  try {
    plans.setPlan(await createPlan({
      user_id: session.userId,
      course: session.course,
      goal: session.goal,
      available_minutes: form.available_minutes,
      task_type: form.task_type,
      knowledge_point: session.knowledgePoint || undefined,
    }))
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
function startTask(task: Task) {
  if (!plans.plan) return
  session.selectedTask = task
  plans.statuses[task.id] = 'active'
  router.push('/study')
}
function recover(type: 'time' | 'too_hard') {
  sessionStorage.setItem('studyflow-block', type)
  if (primaryTask.value) session.selectedTask = primaryTask.value
  router.push('/recovery')
}
async function savePreference() {
  feedbackState.value = 'saving'
  error.value = ''
  try {
    await submitFeedback({
      user_id: session.userId,
      course: session.course,
      content: preference.value,
      feedback_type: 'task_preference',
      explicit: true,
      task_type: 'study',
      knowledge_point: session.knowledgePoint || undefined,
    })
    feedbackState.value = 'saved'
  } catch (e) {
    feedbackState.value = ''
    error.value = errorMessage(e)
  }
}
</script>

<template>
  <section class="today-page">
    <header class="today-header">
      <div>
        <h1>早上好，{{ session.userId }}</h1>
        <p class="date-line">{{ dateText }} · 连续学习 13 天 · 今天，让进度流动起来</p>
      </div>
      <div class="sync-state"><b>{{ session.userId.slice(0, 1).toUpperCase() }}</b><i />计划已同步</div>
    </header>

    <section class="status-strip" aria-label="今日学习状态">
      <div><p><small>今日节奏</small><strong class="brand-value">充沛</strong></p></div>
      <div><p><small>待完成</small><strong>{{ pending }} 项</strong></p></div>
      <div><p><small>可顺延</small><strong class="cyan-value">{{ plans.plan ? deferred : 1 }} 项</strong></p></div>
      <div><p><small>最近截止</small><strong class="rose-value">21:30</strong></p></div>
    </section>

    <div class="plan-row">
      <article class="hero-task">
        <div class="hero-copy">
          <span class="hero-chip">现在最值得做</span>
          <h2>{{ primaryTask?.title || '掌握图的 BFS 与核心遍历流程' }}</h2>
          <p>{{ primaryTask?.description || '数据结构与算法 · 目标：能够独立解释队列与访问顺序' }}</p>
          <div class="hero-divider" />
          <div class="hero-meta"><strong>{{ primaryTask?.duration_minutes || form.available_minutes }}</strong><span>分钟</span><div><b>截止 21:30</b><small>完成后仍保留 35 分钟缓冲</small></div></div>
          <p class="hero-reason"><b>Flow Agent 推荐</b>{{ plans.plan?.explanation || '生成计划后，这里将展示 Agent 的真实推荐依据。' }}</p>
          <div class="hero-actions">
            <button class="start-button" :disabled="!primaryTask" @click="primaryTask && startTask(primaryTask)">▶ 开始学习</button>
            <button class="ghost-button" @click="recover('time')">时间不够</button>
          </div>
        </div>
      </article>

      <form class="settings-card" @submit.prevent="generatePlan">
        <div class="settings-title"><div><h2>快速调整</h2><p>保持主流程可见，只调整必要输入</p></div></div>
        <label>课程<input v-model.trim="session.course" required /></label>
        <label>知识点<input v-model.trim="session.knowledgePoint" placeholder="例如 BFS" /></label>
        <label>可用时间<input v-model.number="form.available_minutes" type="number" min="5" max="120" step="5" /></label>
        <button class="generate-button" :disabled="busy">{{ busy ? '正在生成…' : plans.plan ? '重新生成计划' : '生成今日计划' }}</button>
      </form>
    </div>

    <LoadingState v-if="busy" text="正在检索记忆并拆分学习任务…" />
    <ErrorNotice v-if="error" :message="error" @retry="generatePlan" />

    <div class="bottom-row">
      <section class="timeline-panel">
        <div class="panel-heading">
          <h2>今日任务时间线</h2>
          <div class="heading-actions"><button type="button">✦ 导入任务</button><span>{{ completed }} / {{ plans.plan?.tasks.length || 3 }} 已完成</span></div>
        </div>
        <p v-if="!plans.plan" class="preview-label">界面预览 · 生成计划后替换为真实 Agent 结果</p>
        <div class="timeline-list">
          <article v-for="(task, index) in timelineTasks" :key="task.id" class="glass-task" :class="taskStatus(task, index)">
            <i class="timeline-dot" />
            <div class="task-copy">
              <h3>{{ task.title }}</h3>
              <p>{{ index === 0 ? '09:00–09:25 · 数据结构' : index === 1 ? `现在推荐 · ${task.duration_minutes} 分钟` : '可顺延至 21:30' }}</p>
            </div>
            <span class="task-chip">{{ statusText(taskStatus(task, index)) }}</span>
            <button v-if="plans.plan && taskStatus(task, index) !== 'completed'" class="task-open" @click="startTask(task)" aria-label="开始该任务">→</button>
          </article>
        </div>
      </section>

      <section class="help-panel">
        <div class="panel-heading help-heading"><div><h2>需要一点帮助？</h2><p>随时调整，不打断节奏</p></div></div>
        <button class="glass-help cyan" @click="recover('too_hard')"><b>?</b><span>我卡住了</span><i>→</i></button>
        <button class="glass-help violet" @click="recover('time')"><b>↘</b><span>缩小任务</span><i>→</i></button>
        <button class="glass-help rose" @click="showFeedback = !showFeedback"><b>☁</b><span>记录调整偏好</span><i>→</i></button>
        <div class="health-note"><b>✦ 计划仍然健康</b><span>已为你保留 35 分钟缓冲</span></div>
      </section>
    </div>

    <form v-if="showFeedback" class="feedback-panel" @submit.prevent="savePreference">
      <div><p>反馈记忆 · 任务流内部机制</p><h3>告诉 Agent 你希望怎样调整任务</h3></div>
      <input v-model.trim="preference" required aria-label="任务调整偏好" />
      <button :disabled="feedbackState === 'saving'">{{ feedbackState === 'saving' ? '正在记录…' : feedbackState === 'saved' ? '已记录为反馈记忆' : '记录并用于后续计划' }}</button>
    </form>
  </section>
</template>

<style scoped>
.today-page{width:820px;color:#172052}.today-header{height:78px;display:flex;align-items:flex-start;justify-content:space-between}.date-line{margin:6px 0 0;color:#596387;font-size:14px}.today-header h1{margin:0;font-size:34px;letter-spacing:-.7px}.sync-state{display:flex;align-items:center;gap:8px;margin-top:7px;padding:8px 12px;border:0;border-radius:16px;background:#fff;box-shadow:0 6px 14px rgba(52,71,173,.08);color:#20a77a;font-size:12px}.sync-state b{display:grid;place-items:center;width:34px;height:30px;border-radius:12px;background:#eef2ff;color:#4f63f6}.sync-state i{width:6px;height:6px;border-radius:50%;background:#20a77a}
.status-strip{height:84px;margin-bottom:20px;padding:18px 20px;display:grid;grid-template-columns:repeat(4,1fr);align-items:center;border:0;border-radius:22px;background:#fff;box-shadow:0 8px 18px rgba(52,71,173,.08)}.status-strip>div{height:48px;padding:0 20px;display:flex;align-items:center;border-right:1px solid #dce2f4}.status-strip>div:first-child{padding-left:0}.status-strip>div:last-child{border:0}.status-strip p{display:grid;gap:4px;margin:0}.status-strip small{color:#7b88aa;font-size:11px}.status-strip strong{font-size:19px}.brand-value{color:#4f63f6}.cyan-value{color:#28c7df}.rose-value{color:#ff7f96}
.plan-row{display:grid;grid-template-columns:542px 260px;gap:18px;margin-bottom:14px}.hero-task{position:relative;height:330px;overflow:hidden;padding:24px;border-radius:28px;background:linear-gradient(116deg,#96dff5 0%,#eed0f2 40%,#9ebaeb 81%);box-shadow:0 14px 20px rgba(140,168,227,.24)}.hero-task:before{content:"";position:absolute;inset:0;background:linear-gradient(110deg,rgba(255,255,255,.16),transparent 55%)}.hero-copy{position:relative;z-index:2;width:100%}.hero-chip{display:inline-flex;padding:7px 14px;border-radius:15px;background:rgba(255,255,255,.78);color:#4f63f6;font-size:11px;font-weight:700}.hero-task h2{margin:14px 0 7px;font-size:25px;color:#25335f}.hero-task p{margin:0;color:#55648d;font-size:12px}.hero-divider{height:1px;margin:14px 0 10px;background:rgba(255,255,255,.82)}.hero-meta{display:flex;align-items:center;gap:30px;margin:0 0 10px}.hero-meta>strong{font-size:42px;line-height:1;color:#25335f}.hero-meta>span{font-size:12px;color:#55648d}.hero-meta>div{display:grid;gap:4px}.hero-meta b{font-size:13px}.hero-meta small{color:#55648d;font-size:10px}.hero-reason{display:grid;gap:4px;padding:9px 14px;border-radius:16px;background:rgba(255,255,255,.45);font-size:11px!important}.hero-actions{display:flex;gap:33px;margin-top:9px}.hero-actions button{height:39px;border:0;border-radius:15px;font-weight:800;cursor:pointer}.start-button{width:201px;background:rgba(255,255,255,.92);color:#4f63f6}.start-button:disabled{opacity:.55;cursor:not-allowed}.ghost-button{width:110px;background:rgba(255,255,255,.38);color:#25335f}
.settings-card{height:330px;padding:20px 18px;display:grid;align-content:start;gap:12px;border:0;border-radius:24px;background:#fff;box-shadow:0 8px 18px rgba(52,71,173,.08)}.settings-title h2{margin:0;font-size:16px}.settings-title p{margin:4px 0 0;color:#7b88aa;font-size:11px}.settings-card label{display:grid;gap:5px;color:#596387;font-size:10px;font-weight:600}.settings-card input{width:100%;height:36px;border:1px solid #e1e6f6;border-radius:12px;padding:0 12px;background:#f7f9ff;color:#172052;font:inherit}.generate-button{height:40px;border:0;border-radius:14px;background:linear-gradient(90deg,#28c7df,#7657f6);color:white;font-size:12px;font-weight:800;cursor:pointer}
.bottom-row{display:grid;grid-template-columns:540px 262px;gap:18px}.timeline-panel,.help-panel{padding:22px;border:1px solid rgba(255,255,255,.82);border-radius:25px;background:rgba(255,255,255,.38);box-shadow:0 12px 32px rgba(66,82,148,.07)}.panel-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.panel-heading h2{margin:0;font-size:18px}.panel-heading>span{padding:7px 12px;border-radius:16px;background:#eef1ff;color:#64719b;font-size:10px}.preview-label{margin:-7px 0 10px;color:#99a2bd;font-size:9px}.timeline-list{position:relative;display:grid;gap:12px;padding-left:21px}.timeline-list:before{content:"";position:absolute;left:5px;top:24px;bottom:24px;border-left:2px dashed #ccd6ea}.glass-task{position:relative;min-height:76px;padding:15px 46px 14px 17px;display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid rgba(255,255,255,.94);border-radius:20px;background:linear-gradient(118deg,rgba(255,255,255,.79),rgba(242,247,255,.52));box-shadow:inset 0 1px 0 rgba(255,255,255,.96),0 9px 22px rgba(76,91,151,.08);backdrop-filter:blur(18px) saturate(125%)}.glass-task:after{content:"";position:absolute;inset:1px;border-radius:19px;background:linear-gradient(120deg,rgba(255,255,255,.38),transparent 42%);pointer-events:none}.timeline-dot{position:absolute;z-index:2;left:-24px;top:30px;width:12px;height:12px;border:3px solid #f6f8ff;border-radius:50%;background:#4f7bf5;box-shadow:0 0 0 1px rgba(214,222,240,.8)}.task-copy{position:relative;z-index:1;min-width:0}.task-copy h3{margin:0 0 8px;font-size:13px}.task-copy p{margin:0;color:#8491b3;font-size:9px}.task-chip{position:relative;z-index:1;flex:0 0 auto;padding:7px 11px;border-radius:15px;background:#eaf1ff;color:#4e73e7;font-size:9px;font-weight:800}.task-open{position:absolute;z-index:3;right:13px;bottom:9px;border:0;background:transparent;color:#6b78a0;cursor:pointer}.glass-task.completed .timeline-dot{background:#25b98e}.glass-task.completed .task-copy h3,.glass-task.completed .task-copy p{color:#a8b2ca}.glass-task.completed .task-chip{background:#e7f8f3;color:#36a887}.glass-task.deferred .timeline-dot{background:#ff8a34}.glass-task.deferred .task-chip{background:#fff0e4;color:#f28037}
.help-panel{padding:22px 18px}.help-heading{margin-bottom:13px}.help-heading p{margin:4px 0 0;color:#96a0bc;font-size:9px}.glass-help{width:100%;height:56px;margin-bottom:10px;padding:0 15px;display:grid;grid-template-columns:25px 1fr auto;align-items:center;gap:9px;border:1px solid rgba(255,255,255,.8);border-radius:18px;text-align:left;font-weight:800;box-shadow:inset 0 1px 0 rgba(255,255,255,.84),0 8px 18px rgba(73,94,158,.07);backdrop-filter:blur(17px);cursor:pointer}.glass-help b{font-size:20px}.glass-help i{font-style:normal;opacity:.55}.glass-help.cyan{color:#20b9d4;background:linear-gradient(105deg,rgba(217,249,252,.83),rgba(235,252,255,.54))}.glass-help.violet{color:#7657f6;background:linear-gradient(105deg,rgba(236,230,255,.87),rgba(246,242,255,.58))}.glass-help.rose{color:#fa7295;background:linear-gradient(105deg,rgba(255,234,241,.88),rgba(255,245,248,.55))}.health-note{display:grid;gap:4px;margin-top:5px;padding:12px 14px;border-radius:16px;background:linear-gradient(110deg,#edf7ff,#efedff);font-size:10px}.health-note span{color:#7380a4;font-size:9px}
.feedback-panel{margin-top:18px;padding:18px 20px;display:grid;grid-template-columns:1fr 1.4fr auto;align-items:center;gap:14px;border-radius:20px;background:rgba(255,255,255,.72);box-shadow:0 12px 28px rgba(65,82,150,.09)}.feedback-panel p{margin:0;color:#5265e8;font-size:9px;font-weight:900}.feedback-panel h3{margin:4px 0 0;font-size:13px}.feedback-panel input{height:38px;border:1px solid #dde3f3;border-radius:11px;padding:0 11px}.feedback-panel button{height:38px;border:0;border-radius:11px;padding:0 15px;background:#596bf0;color:#fff;font-weight:800}
.timeline-panel,.help-panel{height:330px;padding:20px 18px;border:1px solid #e7ebfa;border-radius:24px;background:#fff;box-shadow:0 8px 18px rgba(52,71,173,.07)}.panel-heading{margin-bottom:12px}.panel-heading h2{font-size:17px}.heading-actions{display:flex;align-items:center;gap:10px}.heading-actions button{height:32px;padding:0 12px;border:1px solid rgba(255,255,255,.72);border-radius:16px;background:linear-gradient(90deg,#54dde9,#5d9af4 52%,#8a7bf3);box-shadow:0 7px 16px rgba(88,127,231,.28);color:#fff;font-size:10px;font-weight:800}.heading-actions span{padding:7px 11px;border-radius:13px;background:#eef2ff;color:#596387;font-size:10px}.timeline-list{gap:10px}.glass-task{min-height:62px;padding:13px 44px 13px 14px;border-radius:17px}.glass-task.completed{background:linear-gradient(153deg,rgba(255,255,255,.7),rgba(151,236,218,.22),rgba(255,255,255,.35));box-shadow:inset 1px 2px 7px rgba(32,167,122,.1),0 9px 20px -4px rgba(32,167,122,.18)}.glass-task.pending{background:linear-gradient(153deg,rgba(255,255,255,.7),rgba(166,201,255,.22),rgba(255,255,255,.35));box-shadow:inset 1px 2px 7px rgba(79,99,246,.1),0 9px 20px -4px rgba(79,99,246,.18)}.glass-task.deferred{background:linear-gradient(153deg,rgba(255,255,255,.7),rgba(255,215,184,.22),rgba(255,255,255,.35));box-shadow:inset 1px 2px 7px rgba(255,138,52,.1),0 9px 20px -4px rgba(255,138,52,.18)}.timeline-dot{top:24px}.task-copy h3{margin-bottom:4px;font-size:12px}.task-copy p{font-size:10px}.help-panel{padding:20px 18px}.glass-help{height:48px;margin-bottom:8px;padding:0 14px;border-radius:17px;background:rgba(255,255,255,.18)!important}.glass-help.cyan{box-shadow:inset 1px 2px 7px rgba(40,199,223,.1),0 9px 20px -4px rgba(40,199,223,.18)}.glass-help.violet{box-shadow:inset 1px 2px 7px rgba(118,87,246,.1),0 9px 20px -4px rgba(118,87,246,.18)}.glass-help.rose{box-shadow:inset 1px 2px 7px rgba(255,127,150,.1),0 9px 20px -4px rgba(255,127,150,.18)}.health-note{margin-top:0;padding:10px 14px;border:1px solid rgba(255,255,255,.92);background:rgba(255,255,255,.18);box-shadow:inset 1px 2px 7px rgba(118,87,246,.1),0 9px 20px -4px rgba(118,87,246,.18)}
@media(max-width:1100px){.today-page{width:100%}.plan-row,.bottom-row{grid-template-columns:minmax(0,1fr)}.settings-card{height:auto}.hero-task{min-height:278px}.timeline-panel,.help-panel{width:100%}}
@media(max-width:760px){.today-header{height:auto;margin-bottom:18px}.today-header h1{font-size:23px}.sync-state{display:none}.status-strip{height:auto;grid-template-columns:repeat(2,1fr);gap:14px;padding:14px}.status-strip>div{border:0;padding:0}.hero-task{padding:22px;min-height:330px}.hero-copy{width:100%}.hero-orbit{right:25px;top:145px;width:105px;height:105px}.hero-reason{left:22px;right:auto;width:200px}.bottom-row{grid-template-columns:1fr}.timeline-panel{padding:18px 14px}.glass-task{padding-right:36px}.feedback-panel{grid-template-columns:1fr}.panel-heading h2{font-size:16px}}
</style>
