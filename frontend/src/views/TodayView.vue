<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import TaskCard from '../components/TaskCard.vue'
import MemoryReference from '../components/MemoryReference.vue'
import { createPlan } from '../services/agent'
import { submitFeedback } from '../services/memories'
import { errorMessage } from '../services/api'
import { useSessionStore } from '../stores/session'
import { usePlanStore } from '../stores/plan'
import type { Task, TaskStatus } from '../types'

const router = useRouter()
const session = useSessionStore()
const plans = usePlanStore()
const busy = ref(false)
const error = ref('')
const editing = ref(!plans.plan)
const showFeedback = ref(false)
const preference = ref('我希望每个学习任务控制在 15 分钟以内')
const feedbackState = ref('')
const form = reactive({ available_minutes: 25, task_type: 'study' })
const dateText = computed(() => new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' }).format(new Date()))
const completed = computed(() => Object.values(plans.statuses).filter(value => value === 'completed').length)

async function generatePlan() {
  busy.value = true; error.value = ''
  try {
    plans.setPlan(await createPlan({ user_id: session.userId, course: session.course, goal: session.goal, available_minutes: form.available_minutes, task_type: form.task_type, knowledge_point: session.knowledgePoint || undefined }))
    editing.value = false
  } catch (e) { error.value = errorMessage(e) }
  finally { busy.value = false }
}
function startTask(task: Task) { session.selectedTask = task; plans.statuses[task.id] = 'active'; router.push('/study') }
function setStatus(id: string, status: TaskStatus) { plans.statuses[id] = status }
function recover(type: 'time' | 'too_hard') { sessionStorage.setItem('studyflow-block', type); router.push('/recovery') }
async function savePreference() {
  feedbackState.value = 'saving'; error.value = ''
  try {
    await submitFeedback({ user_id: session.userId, course: session.course, content: preference.value, feedback_type: 'task_preference', explicit: true, task_type: 'study', knowledge_point: session.knowledgePoint || undefined })
    feedbackState.value = 'saved'
  } catch (e) { feedbackState.value = ''; error.value = errorMessage(e) }
}
</script>

<template>
  <section>
    <PageHeader eyebrow="TODAY · FLOW" :title="`早上好，${session.userId}`" :subtitle="`${dateText} · 今天，让进度流动起来`">
      <button class="btn btn-secondary" @click="editing = !editing">{{ editing ? '收起设置' : '调整学习目标' }}</button>
    </PageHeader>

    <form v-if="editing" class="card panel plan-form" @submit.prevent="generatePlan">
      <div class="section-title"><div><p class="eyebrow">NEW PLAN</p><h2>创建今日学习计划</h2></div><span class="chip">真实 Agent</span></div>
      <div class="grid-2">
        <div class="field"><label for="course">课程</label><input id="course" v-model.trim="session.course" required /></div>
        <div class="field"><label for="point">知识点</label><input id="point" v-model.trim="session.knowledgePoint" placeholder="例如 BFS" /></div>
      </div>
      <div class="field"><label for="goal">学习目标</label><input id="goal" v-model.trim="session.goal" required minlength="1" /></div>
      <div class="field minutes-field"><label for="minutes">可用时间：{{ form.available_minutes }} 分钟</label><input id="minutes" v-model.number="form.available_minutes" type="range" min="5" max="120" step="5" /></div>
      <button class="btn btn-primary" :disabled="busy">{{ busy ? '正在生成…' : '生成今日计划 →' }}</button>
    </form>
    <LoadingState v-if="busy" text="正在检索记忆并拆分学习任务…" />
    <ErrorNotice v-if="error" :message="error" @retry="generatePlan" />

    <template v-if="plans.plan">
      <div class="status-summary card">
        <div><small>今日节奏</small><strong>稳定</strong></div>
        <div><strong>{{ plans.plan.tasks.length }} 项</strong><small>计划任务</small></div>
        <div><strong>{{ completed }} 项</strong><small>理解完成</small></div>
        <div><strong>{{ plans.totalMinutes }} 分钟</strong><small>计划用时</small></div>
      </div>

      <article v-if="plans.plan.tasks[0]" class="hero-task">
        <span class="chip">现在最值得做</span>
        <h2>{{ plans.plan.tasks[0].title }}</h2><p>{{ plans.plan.tasks[0].description }}</p>
        <div class="hero-numbers"><strong>{{ plans.plan.tasks[0].duration_minutes }}</strong><span>分钟</span></div>
        <div class="agent-reason"><b>Flow Agent 推荐</b><span>{{ plans.plan.explanation }}</span></div>
        <div class="row"><button class="btn hero-primary" @click="startTask(plans.plan.tasks[0])">▶ 开始学习</button><button class="btn hero-secondary" @click="recover('time')">时间不够</button></div>
      </article>

      <MemoryReference class="mobile-trace" :retrieved="plans.plan.retrieved_memory_ids" :used="plans.plan.used_memory_ids" :candidates="plans.plan.candidate_memory_ids" />
      <div class="section-title"><h2>今日任务时间线</h2><span class="chip">{{ completed }}/{{ plans.plan.tasks.length }}</span></div>
      <div class="timeline stack">
        <TaskCard v-for="task in plans.plan.tasks" :key="task.id" :task="task" :status="plans.statuses[task.id] || 'pending'" @start="startTask" @status="setStatus(task.id, $event)" />
      </div>

      <div class="section-title"><h2>需要一点帮助？</h2><span class="muted small">随时调整，不打断节奏</span></div>
      <div class="quick-help card">
        <button @click="recover('too_hard')"><b>？</b><span>我卡住了</span></button>
        <button @click="recover('time')"><b>↘</b><span>缩小任务</span></button>
        <button @click="showFeedback=!showFeedback"><b>◇</b><span>记录调整偏好</span></button>
      </div>
      <form v-if="showFeedback" class="inline-feedback card panel" @submit.prevent="savePreference"><div><p class="eyebrow">反馈记忆 · 任务流内部机制</p><h3>告诉 Agent 你希望怎样调整任务</h3><p class="muted small">明确反馈会保存为任务偏好，并在下一次相似计划中参与检索。</p></div><div class="field"><label for="preference">任务调整偏好</label><input id="preference" v-model.trim="preference" required /></div><button class="btn btn-primary" :disabled="feedbackState==='saving'">{{feedbackState==='saving'?'正在记录…':feedbackState==='saved'?'已记录为反馈记忆':'记录并用于后续计划'}}</button></form>
      <div class="agent-note card"><span class="agent-mark">✦</span><div><p class="eyebrow">FLOW AGENT · 本轮说明</p><h3>{{ plans.localAdjustment || '计划已根据当前目标与反馈记忆完成生成' }}</h3><p>{{ plans.plan.explanation }}</p></div></div>
    </template>

    <div v-else-if="!editing && !busy" class="card panel empty"><div class="assistant-orb">✦</div><h2>还没有今天的计划</h2><p class="muted">告诉 Flow Agent 你的学习目标和可用时间，它会先检索记忆，再拆成可执行任务。</p><button class="btn btn-primary" @click="editing=true">创建今日计划</button></div>
  </section>
</template>

<style scoped>
.plan-form{display:grid;gap:18px;margin-bottom:20px}.plan-form .section-title{margin:0}.minutes-field input{accent-color:var(--brand)}.status-summary{display:grid;grid-template-columns:repeat(4,1fr);padding:18px;margin-bottom:20px}.status-summary>div{display:grid;gap:5px;padding:0 18px;border-right:1px solid var(--border)}.status-summary>div:last-child{border:0}.status-summary strong{font-size:18px}.status-summary small{color:var(--muted)}.hero-task{position:relative;overflow:hidden;padding:28px;border-radius:28px;background:linear-gradient(120deg,#96dff5,#eed0f2 48%,#9ebaea);box-shadow:0 15px 34px rgba(141,168,228,.24)}.hero-task:after{content:"";position:absolute;width:240px;height:240px;right:-100px;bottom:-130px;border-radius:50%;background:rgba(255,255,255,.38)}.hero-task h2{font-size:26px;margin:18px 0 6px}.hero-task>p{color:#55648d}.hero-numbers{display:flex;align-items:baseline;gap:7px;margin:20px 0}.hero-numbers strong{font-size:42px}.agent-reason{display:grid;gap:5px;padding:14px 16px;margin-bottom:16px;border-radius:16px;background:rgba(255,255,255,.46);color:#55648d;font-size:12px}.hero-primary{background:rgba(255,255,255,.92);color:var(--brand);min-width:190px}.hero-secondary{background:rgba(255,255,255,.38)}.timeline{position:relative;padding-left:18px}.timeline:before{content:"";position:absolute;left:4px;top:20px;bottom:20px;width:2px;background:#dce5f3}.timeline>*{position:relative}.timeline>*:before{content:"";position:absolute;left:-23px;top:28px;width:10px;height:10px;border:3px solid var(--bg);border-radius:50%;background:var(--brand)}.quick-help{padding:14px;display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.quick-help button{border:0;border-radius:18px;padding:16px;display:grid;place-items:center;gap:8px;font-weight:800;color:var(--text)}.quick-help button:nth-child(1){background:#e4f9fc;color:var(--cyan)}.quick-help button:nth-child(2){background:#eee9ff;color:var(--violet)}.quick-help button:nth-child(3){background:#fff0f3;color:var(--pink)}.quick-help b{font-size:24px}.inline-feedback{display:grid;gap:14px;margin-top:16px}.inline-feedback h3{margin:3px 0}.agent-note{display:grid;grid-template-columns:auto 1fr;gap:14px;align-items:center;padding:20px;margin-top:20px;background:linear-gradient(135deg,#f7fbff,#eeecff)}.agent-mark,.assistant-orb{display:grid;place-items:center;color:white;background:linear-gradient(135deg,var(--cyan),var(--violet));border-radius:14px}.agent-mark{width:42px;height:42px}.agent-note h3{margin:2px 0 6px;font-size:15px}.agent-note p{margin:0;color:var(--muted);font-size:12px}.empty{text-align:center;padding-block:70px}.empty .assistant-orb{width:72px;height:72px;margin:0 auto 18px;border-radius:50%;font-size:25px}.mobile-trace{margin-top:20px}
@media(max-width:760px){.status-summary{grid-template-columns:repeat(2,1fr);gap:14px}.status-summary>div{border:0;padding:0}.hero-task h2{font-size:21px}.quick-help{gap:7px}.quick-help button{padding:12px 5px;font-size:11px}.hero-primary{min-width:0}.hero-task .row{display:grid;grid-template-columns:1fr 1fr}}
</style>
