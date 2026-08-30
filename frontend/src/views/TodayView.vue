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
const showImport = ref(false)
const deleteMode = ref(false)
const importDrafts = ref([{ course: '', knowledgePoint: '', dueAt: '' }])
const importError = ref('')
const importSuccess = ref('')
function defaultDeadline() {
  const date = new Date()
  date.setHours(21, 30, 0, 0)
  if (date.getTime() <= Date.now()) date.setDate(date.getDate() + 1)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}
const form = reactive({ available_minutes: 25, task_type: 'study', deadline: defaultDeadline() })

const dateText = computed(() => new Intl.DateTimeFormat('zh-CN', {
  month: 'long', day: 'numeric', weekday: 'short',
}).format(new Date()))
const completed = computed(() => Object.values(plans.statuses).filter(value => value === 'completed').length)
const deferred = computed(() => Object.values(plans.statuses).filter(value => value === 'deferred').length)
const pending = computed(() => Math.max((plans.plan?.tasks.length ?? plans.previewTasks.length) - completed.value, 0))
const timelineTasks = computed<Task[]>(() => plans.plan?.tasks.length ? plans.plan.tasks : plans.previewTasks)
const primaryTask = computed(() => timelineTasks.value[0])
const planGoal = computed(() => [session.course.trim(), session.knowledgePoint.trim()].filter(Boolean).join(' · '))
const planDeadlineText = computed(() => new Intl.DateTimeFormat('zh-CN', {
  month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
}).format(new Date(form.deadline)))

function taskStatus(task: Task, index: number): TaskStatus {
  return plans.statuses[task.id] || (plans.plan ? 'pending' : index === 0 ? 'completed' : index === 2 ? 'deferred' : 'pending')
}
function statusText(status: TaskStatus) {
  return ({ completed: '理解完成', active: '进行中', deferred: '可顺延', pending: '待开始' } as Record<TaskStatus, string>)[status]
}
async function generatePlan() {
  busy.value = true
  error.value = ''
  try {
    const existingImports = (plans.plan?.tasks ?? []).filter(task => task.due_at)
    const generated = await createPlan({
      user_id: session.userId,
      course: session.course,
      goal: planGoal.value,
      available_minutes: form.available_minutes,
      task_type: form.task_type,
      knowledge_point: session.knowledgePoint || undefined,
      imported_tasks: [
        ...existingImports
        .filter(task => task.due_at)
        .map(task => ({ title: task.title, due_at: task.due_at! })),
        { title: planGoal.value, due_at: new Date(form.deadline).toISOString() },
      ],
    })
    const generatedTitles = new Set(generated.tasks.map(task => task.title))
    plans.setPlan({
      ...generated,
      tasks: [...generated.tasks, ...existingImports.filter(task => !generatedTitles.has(task.title))],
    })
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
function startTask(task: Task) {
  session.selectedTask = task
  if (task.course) session.course = task.course
  if (task.knowledge_point) session.knowledgePoint = task.knowledge_point
  plans.statuses[task.id] = 'active'
  router.push('/focus')
}
function deleteTask(task: Task) {
  if (!plans.plan) {
    plans.removeTask(task.id)
    if (!plans.previewTasks.length) deleteMode.value = false
    return
  }
  if (session.selectedTask?.id === task.id) session.selectedTask = null
  plans.removeTask(task.id)
  if (!plans.plan) deleteMode.value = false
}
function openTaskDialog() {
  importError.value = ''
  importDrafts.value = [{ course: session.course, knowledgePoint: session.knowledgePoint, dueAt: '' }]
  showImport.value = true
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
function addTask() {
  importError.value = ''
  if (importDrafts.value.some(task => !task.course.trim() || !task.knowledgePoint.trim() || !task.dueAt)) {
    importError.value = '请填写课程、知识点和截止时间。'
    return
  }
  const tasks = importDrafts.value.map((draft, index) => ({
    id: `imported-${Date.now()}-${index}`,
    course: draft.course.trim(),
    title: `${draft.course.trim()} · ${draft.knowledgePoint.trim()}`,
    description: '根据截止时间添加的待安排任务',
    duration_minutes: form.available_minutes,
    task_type: form.task_type,
    knowledge_point: draft.knowledgePoint.trim(),
    due_at: new Date(draft.dueAt).toISOString(),
  }))
  plans.addImportedTasks(tasks)
  importSuccess.value = `已添加 ${tasks.length} 个任务`
  showImport.value = false
  importDrafts.value = [{ course: '', knowledgePoint: '', dueAt: '' }]
  window.setTimeout(() => { importSuccess.value = '' }, 3000)
}
function removeImportDraft(index: number) {
  if (importDrafts.value.length === 1) importDrafts.value[0] = { course: '', knowledgePoint: '', dueAt: '' }
  else importDrafts.value.splice(index, 1)
}
function dueText(task: Task) {
  return task.due_at
    ? new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(task.due_at))
    : ''
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

    <section v-if="plans.localAdjustment" class="recovery-adjustment" aria-live="polite">
      <div><span>反馈记忆 · 已影响本次计划</span><strong>弹性任务流刚刚完成调整</strong><p>{{ plans.localAdjustment }}</p></div>
      <button type="button" @click="plans.localAdjustment = ''">我知道了</button>
    </section>

    <div class="plan-row">
      <article class="hero-task">
        <div class="hero-copy">
          <span class="hero-chip">现在最值得做</span>
          <h2>{{ primaryTask?.title || '掌握图的 BFS 与核心遍历流程' }}</h2>
          <p>{{ primaryTask?.description || '数据结构与算法 · 目标：能够独立解释队列与访问顺序' }}</p>
          <div class="hero-divider" />
          <div class="hero-meta"><strong>{{ primaryTask?.duration_minutes || form.available_minutes }}</strong><span>分钟</span><div><b>截止 {{ primaryTask?.due_at ? dueText(primaryTask) : planDeadlineText }}</b><small>Agent 将结合截止时间安排优先级</small></div></div>
          <p class="hero-reason"><b>Flow Agent 推荐</b>{{ plans.plan?.explanation || '生成计划后，这里将展示 Agent 的真实推荐依据。' }}</p>
          <div class="hero-actions">
            <button class="start-button" :disabled="!primaryTask" @click="primaryTask && startTask(primaryTask)">▶ 开始学习</button>
          </div>
        </div>
      </article>

      <form class="settings-card" @submit.prevent="generatePlan">
        <div class="settings-title"><div><h2>快速调整</h2><p>设置学习范围与时间，交给 Agent 安排</p></div></div>
        <label>课程<input v-model.trim="session.course" required placeholder="例如：数据结构与算法" /></label>
        <label>知识点<input v-model.trim="session.knowledgePoint" required placeholder="例如：BFS" /></label>
        <label>可用时间<input v-model.number="form.available_minutes" type="number" min="5" max="120" step="5" /></label>
        <label>截止时间<input v-model="form.deadline" type="datetime-local" required /></label>
        <button class="generate-button" :disabled="busy">{{ busy ? '正在生成…' : plans.plan ? '重新生成计划' : '生成今日计划' }}</button>
      </form>
    </div>

    <LoadingState v-if="busy" text="正在检索记忆并拆分学习任务…" />
    <ErrorNotice v-if="error" :message="error" @retry="generatePlan" />

    <div class="bottom-row">
      <section class="timeline-panel">
        <div class="panel-heading">
          <h2>今日任务时间线</h2>
          <div class="heading-actions">
            <div class="task-tools">
              <button type="button" class="add-tool" @click="openTaskDialog">＋ 添加</button>
              <button type="button" class="delete-tool" :class="{ active: deleteMode }" @click="deleteMode = !deleteMode">{{ deleteMode ? '完成' : '− 删除' }}</button>
            </div>
            <span>{{ completed }} / {{ timelineTasks.length }} 已完成</span>
          </div>
        </div>
        <p v-if="importSuccess" class="import-success" role="status">✓ {{ importSuccess }}</p>
        <p v-if="!plans.plan" class="preview-label">界面预览 · 生成计划后替换为真实 Agent 结果</p>
        <p v-if="!timelineTasks.length" class="empty-timeline">暂无任务，点击“添加”创建任务</p>
        <div class="timeline-list">
          <article v-for="(task, index) in timelineTasks" :key="task.id" class="glass-task" :class="[taskStatus(task, index), { 'delete-state': deleteMode }]">
            <i class="timeline-dot" />
            <div class="task-copy">
              <h3>{{ task.title }}</h3>
              <p>{{ task.due_at ? `截止 ${dueText(task)} · ${task.duration_minutes} 分钟` : index === 0 ? '09:00–09:25 · 数据结构' : index === 1 ? `现在推荐 · ${task.duration_minutes} 分钟` : '可顺延至 21:30' }}</p>
            </div>
            <span v-if="!deleteMode" class="task-chip">{{ statusText(taskStatus(task, index)) }}</span>
            <div v-if="plans.plan || deleteMode" class="task-card-actions" :class="{ deleting: deleteMode }">
              <button v-if="deleteMode" class="task-delete" type="button" :aria-label="`删除任务：${task.title}`" title="删除任务" @click.stop="deleteTask(task)">删除</button>
              <button v-if="!deleteMode && taskStatus(task, index) !== 'completed'" class="task-open" type="button" @click="startTask(task)" aria-label="开始该任务">→</button>
            </div>
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

    <div v-if="showImport" class="import-backdrop" @click.self="showImport = false">
      <form class="import-dialog" role="dialog" aria-modal="true" aria-labelledby="import-title" @submit.prevent="addTask">
        <div class="import-title-row"><div><small>弹性任务流</small><h2 id="import-title">添加任务</h2></div><button type="button" class="import-close" aria-label="关闭" @click="showImport = false">×</button></div>
        <p class="import-hint">填写课程、知识点和截止时间，系统将以“课程 · 知识点”生成任务，并交给模型安排优先级。</p>
        <div class="import-or"><i />任务信息<i /></div>
        <div class="import-drafts">
          <article v-for="(draft, index) in importDrafts" :key="index" class="import-task-card">
            <div class="import-task-number"><b>任务 {{ index + 1 }}</b><button type="button" aria-label="删除该任务" @click="removeImportDraft(index)">×</button></div>
            <label>课程<input v-model.trim="draft.course" placeholder="例如：高等数学" autofocus /></label>
            <label>知识点<input v-model.trim="draft.knowledgePoint" placeholder="例如：导数应用" /></label>
            <label>截止时间<input v-model="draft.dueAt" type="datetime-local" /></label>
          </article>
        </div>
        <p v-if="importError" class="import-error" role="alert">{{ importError }}</p>
        <div class="import-actions"><button type="button" class="import-cancel" @click="showImport = false">取消</button><button class="import-confirm">添加到今日任务流</button></div>
      </form>
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
.recovery-adjustment{margin:-4px 0 20px;padding:16px 19px;display:flex;align-items:center;justify-content:space-between;gap:20px;border:1px solid #bfe9dc;border-radius:20px;background:linear-gradient(105deg,#e9faf4,#eef3ff);box-shadow:0 8px 20px rgba(53,105,134,.08)}.recovery-adjustment div{display:grid;gap:4px}.recovery-adjustment span{color:#20a77a;font-size:9px;font-weight:900}.recovery-adjustment strong{font-size:14px}.recovery-adjustment p{margin:0;color:#647392;font-size:10px;line-height:1.5}.recovery-adjustment button{flex:0 0 auto;padding:9px 13px;border:0;border-radius:12px;background:#fff;color:#5367f7;font-size:10px;font-weight:800;cursor:pointer}
.plan-row{display:grid;grid-template-columns:542px 260px;gap:18px;margin-bottom:14px}.hero-task{position:relative;height:330px;overflow:hidden;padding:24px;border-radius:28px;background:linear-gradient(116deg,#96dff5 0%,#eed0f2 40%,#9ebaeb 81%);box-shadow:0 14px 20px rgba(140,168,227,.24)}.hero-task:before{content:"";position:absolute;inset:0;background:linear-gradient(110deg,rgba(255,255,255,.16),transparent 55%)}.hero-copy{position:relative;z-index:2;width:100%}.hero-chip{display:inline-flex;padding:7px 14px;border-radius:15px;background:rgba(255,255,255,.78);color:#4f63f6;font-size:11px;font-weight:700}.hero-task h2{margin:14px 0 7px;font-size:25px;color:#25335f}.hero-task p{margin:0;color:#55648d;font-size:12px}.hero-divider{height:1px;margin:14px 0 10px;background:rgba(255,255,255,.82)}.hero-meta{display:flex;align-items:center;gap:30px;margin:0 0 10px}.hero-meta>strong{font-size:42px;line-height:1;color:#25335f}.hero-meta>span{font-size:12px;color:#55648d}.hero-meta>div{display:grid;gap:4px}.hero-meta b{font-size:13px}.hero-meta small{color:#55648d;font-size:10px}.hero-reason{display:grid;gap:4px;padding:9px 14px;border-radius:16px;background:rgba(255,255,255,.45);font-size:11px!important}.hero-actions{display:flex;gap:33px;margin-top:9px}.hero-actions button{height:39px;border:0;border-radius:15px;font-weight:800;cursor:pointer}.start-button{width:201px;background:rgba(255,255,255,.92);color:#4f63f6}.start-button:disabled{opacity:.55;cursor:not-allowed}.ghost-button{width:110px;background:rgba(255,255,255,.38);color:#25335f}
.settings-card{height:330px;padding:20px 18px;display:grid;align-content:start;gap:12px;border:0;border-radius:24px;background:#fff;box-shadow:0 8px 18px rgba(52,71,173,.08)}.settings-title h2{margin:0;font-size:16px}.settings-title p{margin:4px 0 0;color:#7b88aa;font-size:11px}.settings-card label{display:grid;gap:5px;color:#596387;font-size:10px;font-weight:600}.settings-card input{width:100%;height:36px;border:1px solid #e1e6f6;border-radius:12px;padding:0 12px;background:#f7f9ff;color:#172052;font:inherit}.generate-button{height:40px;border:0;border-radius:14px;background:linear-gradient(90deg,#28c7df,#7657f6);color:white;font-size:12px;font-weight:800;cursor:pointer}
.bottom-row{display:grid;grid-template-columns:540px 262px;gap:18px}.timeline-panel,.help-panel{padding:22px;border:1px solid rgba(255,255,255,.82);border-radius:25px;background:rgba(255,255,255,.38);box-shadow:0 12px 32px rgba(66,82,148,.07)}.panel-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.panel-heading h2{margin:0;font-size:18px}.panel-heading>span{padding:7px 12px;border-radius:16px;background:#eef1ff;color:#64719b;font-size:10px}.preview-label{margin:-7px 0 10px;color:#99a2bd;font-size:9px}.timeline-list{position:relative;display:grid;gap:12px;padding-left:21px}.timeline-list:before{content:"";position:absolute;left:5px;top:24px;bottom:24px;border-left:2px dashed #ccd6ea}.glass-task{position:relative;min-height:76px;padding:15px 46px 14px 17px;display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid rgba(255,255,255,.94);border-radius:20px;background:linear-gradient(118deg,rgba(255,255,255,.79),rgba(242,247,255,.52));box-shadow:inset 0 1px 0 rgba(255,255,255,.96),0 9px 22px rgba(76,91,151,.08);backdrop-filter:blur(18px) saturate(125%)}.glass-task:after{content:"";position:absolute;inset:1px;border-radius:19px;background:linear-gradient(120deg,rgba(255,255,255,.38),transparent 42%);pointer-events:none}.timeline-dot{position:absolute;z-index:2;left:-24px;top:30px;width:12px;height:12px;border:3px solid #f6f8ff;border-radius:50%;background:#4f7bf5;box-shadow:0 0 0 1px rgba(214,222,240,.8)}.task-copy{position:relative;z-index:1;min-width:0}.task-copy h3{margin:0 0 8px;font-size:13px}.task-copy p{margin:0;color:#8491b3;font-size:9px}.task-chip{position:relative;z-index:1;flex:0 0 auto;padding:7px 11px;border-radius:15px;background:#eaf1ff;color:#4e73e7;font-size:9px;font-weight:800}.task-open{position:absolute;z-index:3;right:13px;bottom:9px;border:0;background:transparent;color:#6b78a0;cursor:pointer}.glass-task.completed .timeline-dot{background:#25b98e}.glass-task.completed .task-copy h3,.glass-task.completed .task-copy p{color:#a8b2ca}.glass-task.completed .task-chip{background:#e7f8f3;color:#36a887}.glass-task.deferred .timeline-dot{background:#ff8a34}.glass-task.deferred .task-chip{background:#fff0e4;color:#f28037}
.help-panel{padding:22px 18px}.help-heading{margin-bottom:13px}.help-heading p{margin:4px 0 0;color:#96a0bc;font-size:9px}.glass-help{width:100%;height:56px;margin-bottom:10px;padding:0 15px;display:grid;grid-template-columns:25px 1fr auto;align-items:center;gap:9px;border:1px solid rgba(255,255,255,.8);border-radius:18px;text-align:left;font-weight:800;box-shadow:inset 0 1px 0 rgba(255,255,255,.84),0 8px 18px rgba(73,94,158,.07);backdrop-filter:blur(17px);cursor:pointer}.glass-help b{font-size:20px}.glass-help i{font-style:normal;opacity:.55}.glass-help.cyan{color:#20b9d4;background:linear-gradient(105deg,rgba(217,249,252,.83),rgba(235,252,255,.54))}.glass-help.violet{color:#7657f6;background:linear-gradient(105deg,rgba(236,230,255,.87),rgba(246,242,255,.58))}.glass-help.rose{color:#fa7295;background:linear-gradient(105deg,rgba(255,234,241,.88),rgba(255,245,248,.55))}.health-note{display:grid;gap:4px;margin-top:5px;padding:12px 14px;border-radius:16px;background:linear-gradient(110deg,#edf7ff,#efedff);font-size:10px}.health-note span{color:#7380a4;font-size:9px}
.feedback-panel{margin-top:18px;padding:18px 20px;display:grid;grid-template-columns:1fr 1.4fr auto;align-items:center;gap:14px;border-radius:20px;background:rgba(255,255,255,.72);box-shadow:0 12px 28px rgba(65,82,150,.09)}.feedback-panel p{margin:0;color:#5265e8;font-size:9px;font-weight:900}.feedback-panel h3{margin:4px 0 0;font-size:13px}.feedback-panel input{height:38px;border:1px solid #dde3f3;border-radius:11px;padding:0 11px}.feedback-panel button{height:38px;border:0;border-radius:11px;padding:0 15px;background:#596bf0;color:#fff;font-weight:800}
.timeline-panel,.help-panel{height:330px;padding:20px 18px;border:1px solid #e7ebfa;border-radius:24px;background:#fff;box-shadow:0 8px 18px rgba(52,71,173,.07)}.panel-heading{margin-bottom:12px}.panel-heading h2{font-size:17px}.heading-actions{display:flex;align-items:center;gap:10px}.heading-actions button{height:32px;padding:0 12px;border:1px solid rgba(255,255,255,.72);border-radius:16px;background:linear-gradient(90deg,#54dde9,#5d9af4 52%,#8a7bf3);box-shadow:0 7px 16px rgba(88,127,231,.28);color:#fff;font-size:10px;font-weight:800}.heading-actions span{padding:7px 11px;border-radius:13px;background:#eef2ff;color:#596387;font-size:10px}.timeline-list{gap:10px}.glass-task{min-height:62px;padding:13px 44px 13px 14px;border-radius:17px}.glass-task.completed{background:linear-gradient(153deg,rgba(255,255,255,.7),rgba(151,236,218,.22),rgba(255,255,255,.35));box-shadow:inset 1px 2px 7px rgba(32,167,122,.1),0 9px 20px -4px rgba(32,167,122,.18)}.glass-task.pending{background:linear-gradient(153deg,rgba(255,255,255,.7),rgba(166,201,255,.22),rgba(255,255,255,.35));box-shadow:inset 1px 2px 7px rgba(79,99,246,.1),0 9px 20px -4px rgba(79,99,246,.18)}.glass-task.deferred{background:linear-gradient(153deg,rgba(255,255,255,.7),rgba(255,215,184,.22),rgba(255,255,255,.35));box-shadow:inset 1px 2px 7px rgba(255,138,52,.1),0 9px 20px -4px rgba(255,138,52,.18)}.timeline-dot{top:24px}.task-copy h3{margin-bottom:4px;font-size:12px}.task-copy p{font-size:10px}.help-panel{padding:20px 18px}.glass-help{height:48px;margin-bottom:8px;padding:0 14px;border-radius:17px;background:rgba(255,255,255,.18)!important}.glass-help.cyan{box-shadow:inset 1px 2px 7px rgba(40,199,223,.1),0 9px 20px -4px rgba(40,199,223,.18)}.glass-help.violet{box-shadow:inset 1px 2px 7px rgba(118,87,246,.1),0 9px 20px -4px rgba(118,87,246,.18)}.glass-help.rose{box-shadow:inset 1px 2px 7px rgba(255,127,150,.1),0 9px 20px -4px rgba(255,127,150,.18)}.health-note{margin-top:0;padding:10px 14px;border:1px solid rgba(255,255,255,.92);background:rgba(255,255,255,.18);box-shadow:inset 1px 2px 7px rgba(118,87,246,.1),0 9px 20px -4px rgba(118,87,246,.18)}
.heading-actions button{cursor:pointer}.timeline-panel .timeline-list{max-height:225px;overflow-y:auto;padding-right:4px}.import-success{margin:-7px 0 8px;color:#20a77a;font-size:10px;font-weight:800}.import-backdrop{position:fixed;z-index:1000;inset:0;display:grid;place-items:center;padding:20px;background:rgba(25,31,70,.28);backdrop-filter:blur(8px)}.import-dialog{width:min(480px,100%);padding:25px;border:1px solid rgba(255,255,255,.9);border-radius:26px;background:rgba(255,255,255,.96);box-shadow:0 28px 80px rgba(43,56,125,.25)}.import-title-row{display:flex;justify-content:space-between;align-items:flex-start}.import-title-row small{color:#5e72ef;font-weight:900}.import-title-row h2{margin:5px 0 0;font-size:23px}.import-close{width:34px;height:34px;border:0;border-radius:50%;background:#eef1fb;color:#697596;font-size:22px;cursor:pointer}.import-hint{margin:14px 0;color:#7480a0;font-size:12px;line-height:1.7}.file-picker{min-height:64px;padding:11px 15px;display:flex;align-items:center;justify-content:center;gap:8px;border:1px dashed #9ba9e8;border-radius:17px;background:#f5f7ff;color:#596bf0;font-size:12px;font-weight:800;cursor:pointer}.file-picker input{position:absolute;width:1px;height:1px;opacity:0}.file-picker b{max-width:150px;overflow:hidden;color:#7c87a6;text-overflow:ellipsis;white-space:nowrap}.import-or{display:flex;align-items:center;gap:10px;margin:13px 0;color:#a1a9bf;font-size:10px}.import-or i{height:1px;flex:1;background:#e4e8f4}.import-dialog textarea{width:100%;resize:vertical;min-height:130px;padding:13px;border:1px solid #dfe4f3;border-radius:15px;background:#fbfcff;color:#172052;font:12px/1.7 inherit;outline:none}.import-dialog textarea:focus{border-color:#7b87ef;box-shadow:0 0 0 3px rgba(94,114,239,.11)}.import-error{margin:9px 0 0;color:#d84f6b;font-size:11px}.import-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:16px}.import-actions button{height:39px;padding:0 17px;border:0;border-radius:13px;font-weight:800;cursor:pointer}.import-cancel{background:#eef1f8;color:#697596}.import-confirm{background:linear-gradient(90deg,#54dce8,#657fee 60%,#8d72f1);color:#fff;box-shadow:0 8px 18px rgba(93,117,233,.22)}
.import-dialog{width:min(520px,100%);max-height:90vh;overflow-y:auto}.import-drafts{display:grid;gap:10px}.import-task-card{padding:13px;border:1px solid #e0e5f4;border-radius:16px;background:#fafbff}.import-task-number{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;color:#596bf0;font-size:11px}.import-task-number button{border:0;background:transparent;color:#8b95b1;font-size:18px;cursor:pointer}.import-task-card label{display:grid;grid-template-columns:72px 1fr;align-items:center;gap:8px;margin-top:8px;color:#6d7898;font-size:11px;font-weight:700}.import-task-card input{height:38px;border:1px solid #dfe4f3;border-radius:11px;padding:0 11px;background:#fff;color:#172052;font:inherit}.import-task-card input:focus{border-color:#7b87ef;outline:none;box-shadow:0 0 0 3px rgba(94,114,239,.1)}.add-import-task{width:100%;height:38px;margin-top:10px;border:1px dashed #a9b3e8;border-radius:12px;background:#f7f8ff;color:#5e72ef;font-size:11px;font-weight:800;cursor:pointer}
.task-card-actions{position:absolute;z-index:3;right:11px;bottom:7px;display:flex;align-items:center;gap:3px}.task-card-actions button{width:25px;height:25px;padding:0;border:0;border-radius:9px;background:transparent;cursor:pointer}.task-card-actions .task-delete{color:#a4acc1;font-size:17px}.task-card-actions .task-delete:hover{background:#fff0f3;color:#e45d78}.task-card-actions .task-open{position:static;color:#6b78a0}
.empty-timeline{display:grid;place-items:center;height:170px;margin:0;color:#98a2bd;font-size:11px}
.heading-actions{gap:7px}.task-tools{display:flex;gap:5px}.heading-actions .task-tools button{height:30px;padding:0 9px;box-shadow:none;font-size:9px}.heading-actions .task-tools .import-tool{background:linear-gradient(90deg,#54dde9,#7c73f3)}.heading-actions .task-tools .add-tool{border-color:#cbd4fa;background:#f3f5ff;color:#596bf0}.heading-actions .task-tools .delete-tool{border-color:#f1d9df;background:#fff5f7;color:#d96179}.heading-actions .task-tools .delete-tool.active{background:#e7667f;color:#fff}.heading-actions .task-tools button:disabled{opacity:.42;cursor:not-allowed}.task-card-actions .task-delete{width:auto;padding:0 8px;background:#fff0f3;color:#d95c76;font-size:9px;font-weight:800}.task-card-actions .task-delete:hover{background:#ffe3e9;color:#c94560}
.task-card-actions.deleting{top:50%;right:14px;bottom:auto;transform:translateY(-50%)}.task-card-actions.deleting .task-delete{height:32px;padding:0 12px;border:1px solid #ffdbe3;border-radius:12px;font-size:10px}.glass-task.delete-state{padding-right:72px}
.hero-task,.settings-card{height:390px}.settings-card{padding:20px 18px;gap:10px}.settings-card input{height:36px}.settings-card .generate-button{height:40px;margin-top:2px}
.hero-copy{height:100%;display:grid;grid-template-rows:auto auto auto 1px auto auto auto;align-content:space-between}.hero-task h2{margin:0}.hero-divider{margin:0}.hero-meta{margin:0}.hero-reason{margin:0!important}.hero-actions{width:100%;margin:0;justify-content:center}.hero-actions .start-button{width:min(300px,68%)}
@media(max-width:1100px){.today-page{width:100%}.plan-row,.bottom-row{grid-template-columns:minmax(0,1fr)}.settings-card{height:auto}.hero-task{min-height:278px}.timeline-panel,.help-panel{width:100%}}
@media(max-width:760px){.today-header{height:auto;margin-bottom:18px}.today-header h1{font-size:23px}.sync-state{display:none}.status-strip{height:auto;grid-template-columns:repeat(2,1fr);gap:14px;padding:14px}.status-strip>div{border:0;padding:0}.hero-task{padding:22px;min-height:330px}.hero-copy{width:100%}.hero-orbit{right:25px;top:145px;width:105px;height:105px}.hero-reason{left:22px;right:auto;width:200px}.bottom-row{grid-template-columns:1fr}.timeline-panel{padding:18px 14px}.glass-task{padding-right:36px}.feedback-panel{grid-template-columns:1fr}.panel-heading h2{font-size:16px}}
</style>
