<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import { checkUnderstanding } from '../services/agent'
import { errorMessage } from '../services/api'
import { useSessionStore } from '../stores/session'
import { useTutorStore } from '../stores/tutor'
import { usePlanStore } from '../stores/plan'
import studyflowLogo from '../assets/studyflow-app.png'

const router = useRouter()
const session = useSessionStore()
const tutor = useTutorStore()
const plans = usePlanStore()
const input = ref('')
const busy = ref(false)
const error = ref('')
const thread = ref<HTMLElement | null>(null)
const reviewDate = ref('')
const reviewAdded = ref(false)
const showExitReview = ref(false)
const closeDestination = ref<'/study' | '/today'>('/study')
const config = computed(() => tutor.config)

const strategyLabels = {
  question: '苏格拉底提问', hint: '给出提示', correction: '指出错误',
  full_answer: '完整讲解', encouragement: '继续挑战',
}
const hintOptions = [
  { value: 'example' as const, icon: '◫', label: '示例提示', description: '先看一个最小例子' },
  { value: 'definition' as const, icon: 'Aa', label: '定义提示', description: '只回顾关键定义' },
  { value: 'analogy' as const, icon: '≈', label: '类比提示', description: '联系熟悉的事物' },
  { value: 'diagram' as const, icon: '⌘', label: '图示提示', description: '用流程或简图理解' },
]
type HintPreference = typeof hintOptions[number]['value']

function isHelpRequest(value: string) {
  const normalized = value.replace(/[\s，。！？、,.!?]/g, '').toLowerCase()
  if (normalized.length > 30) return false
  const hasHelpMarker = [
    '不会', '不知道', '不太会', '不清楚', '没思路', '没有思路',
    '不太知道', '不怎么知道', '卡住了', '卡住', '不理解', '没懂',
    '看不懂', '想不出来', '答不上来', '没概念', '毫无头绪',
    '请提示', '给点提示', '帮我一下', '提示一下',
  ].some(marker => normalized.includes(marker))
  return hasHelpMarker || /^(我|这个|这题|这个问题)?(也|真的|确实|还是)?(不太|不怎么|完全|实在)?(会|知道|清楚|明白|理解|懂)$/.test(normalized)
}

function isFullAnswerRequest(value: string) {
  const normalized = value.replace(/[\s，。！？、,.!?]/g, '').toLowerCase()
  return [
    '直接告诉我答案', '告诉我答案', '给我答案', '完整答案', '公布答案',
    '直接讲答案', '完整讲解', '不想猜了', '我想看答案',
  ].some(marker => normalized.includes(marker))
}

async function scrollToBottom() {
  await nextTick()
  thread.value?.scrollTo({ top: thread.value.scrollHeight, behavior: 'smooth' })
}

async function begin() {
  if (!config.value || tutor.messages.length) return
  busy.value = true
  error.value = ''
  try {
    const result = await checkUnderstanding({
      user_id: session.userId, course: config.value.course,
      knowledge_point: config.value.knowledgePoint, task_type: config.value.taskType,
      material: config.value.material, level: config.value.level,
    })
    tutor.addMessage({ role: 'assistant', content: result.question, guidanceType: 'question' })
    await scrollToBottom()
  } catch (cause) { error.value = errorMessage(cause) }
  finally { busy.value = false }
}

async function send() {
  const answer = input.value.trim()
  if (!answer || busy.value || !config.value) return
  if (isHelpRequest(answer)) {
    tutor.addMessage({ role: 'user', content: answer })
    tutor.addMessage({
      role: 'assistant', guidanceType: 'hint', hintChoices: true,
      content: '没关系，我们先不看完整答案。你希望我用哪种方式给你一个轻量提示？',
    })
    input.value = ''
    error.value = ''
    await scrollToBottom()
    return
  }
  const history = tutor.messages.map(message => ({ role: message.role, content: message.content }))
  const requestsFullAnswer = isFullAnswerRequest(answer)
  tutor.addMessage({ role: 'user', content: answer })
  input.value = ''
  busy.value = true
  error.value = ''
  await scrollToBottom()
  try {
    const result = await checkUnderstanding({
      user_id: session.userId, course: config.value.course,
      knowledge_point: config.value.knowledgePoint, task_type: config.value.taskType,
      material: config.value.material, level: config.value.level, answer,
      conversation_history: history,
      ...(requestsFullAnswer ? { guidance_request: 'full_answer' as const } : {}),
    })
    const content = result.mastery_status === 'ready'
      ? `${result.feedback}\n\n你已经能够较完整地解释并迁移这个知识点，本环节可以完成。`
      : `${result.feedback}${result.question ? `\n\n${result.question}` : ''}`
    tutor.addMessage({
      role: 'assistant', content, guidanceType: result.guidance_type,
      missingDimensions: result.missing_dimensions,
    })
    tutor.masteryStatus = result.mastery_status
    tutor.masterySummary = result.mastery_summary || ''
    tutor.reviewRecommendation = result.review_recommendation || null
    if (result.review_recommendation) reviewDate.value = result.review_recommendation.due_date
    await scrollToBottom()
  } catch (cause) {
    error.value = errorMessage(cause)
    tutor.messages.pop()
    input.value = answer
  }
  finally { busy.value = false }
}

async function chooseHint(preference: HintPreference, messageId: string) {
  if (busy.value || !config.value) return
  const choice = hintOptions.find(item => item.value === preference)!
  const chooser = tutor.messages.find(message => message.id === messageId)
  if (chooser) chooser.hintChoices = false
  const history = tutor.messages.map(message => ({ role: message.role, content: message.content }))
  tutor.addMessage({ role: 'user', content: `我想先看${choice.label}` })
  busy.value = true
  error.value = ''
  await scrollToBottom()
  try {
    const result = await checkUnderstanding({
      user_id: session.userId, course: config.value.course,
      knowledge_point: config.value.knowledgePoint, task_type: config.value.taskType,
      material: config.value.material, level: config.value.level,
      answer: `我不会，请使用${choice.label}给我一个轻量提示`,
      conversation_history: history, hint_preference: preference,
    })
    tutor.addMessage({
      role: 'assistant', guidanceType: 'hint',
      content: preference === 'diagram'
        ? `请沿着图中的步骤观察：\n\n${result.question}`
        : `${result.feedback}${result.question ? `\n\n${result.question}` : ''}`,
      missingDimensions: result.missing_dimensions,
      visualSteps: preference === 'diagram' ? result.visual_steps : [],
    })
    tutor.masteryStatus = 'ongoing'
    await scrollToBottom()
  } catch (cause) {
    error.value = errorMessage(cause)
    tutor.messages.pop()
    if (chooser) chooser.hintChoices = true
  } finally { busy.value = false }
}

function exitSession() {
  closeDestination.value = '/study'
  showExitReview.value = true
}

function finishSession() {
  closeDestination.value = '/today'
  if (reviewAdded.value) {
    leaveSession()
    return
  }
  showExitReview.value = true
}

function leaveSession() {
  tutor.clear()
  void router.push(closeDestination.value)
}

function addReviewToPlan() {
  if (!config.value || !tutor.reviewRecommendation || !reviewDate.value) return
  const dueAt = new Date(`${reviewDate.value}T19:30:00`)
  plans.addReviewTask({
    id: `review-${session.userId}-${config.value.course}-${config.value.knowledgePoint}`,
    course: config.value.course,
    title: `${config.value.knowledgePoint} · 对话后复习`,
    description: `根据苏格拉底伴学掌握证据安排：${tutor.masterySummary}`,
    duration_minutes: tutor.reviewRecommendation.duration_minutes,
    task_type: 'review', knowledge_point: config.value.knowledgePoint,
    due_at: dueAt.toISOString(),
  }, tutor.reviewRecommendation.reason)
  reviewAdded.value = true
}

function addReviewAndLeave() {
  if (reviewAdded.value) {
    leaveSession()
    return
  }
  addReviewToPlan()
  if (reviewAdded.value) leaveSession()
}

onMounted(() => {
  if (!config.value) void router.replace('/study')
  else void begin()
})
</script>

<template>
  <section v-if="config" class="tutor-page">
    <header class="tutor-header">
      <button class="exit-button" type="button" @click="exitSession">← 退出伴学</button>
      <div><p>FLOW TUTOR · SOCRATIC SESSION</p><h1>{{ config.knowledgePoint }}</h1><span>{{ config.course }} · {{ config.level }}</span></div>
      <div class="session-state" :class="tutor.masteryStatus"><i />{{ tutor.masteryStatus === 'ready' ? '可以完成' : '伴学进行中' }}</div>
    </header>

    <div ref="thread" class="chat-thread" aria-live="polite">
      <div class="welcome"><b>本轮目标</b><span>通过连续解释、关联与迁移，形成可验证的理解。Flow Tutor 会按你的回答决定提示程度。</span></div>
      <article v-for="message in tutor.messages" :key="message.id" class="message" :class="message.role">
        <div class="avatar" :class="{ 'assistant-logo': message.role === 'assistant' }">
          <img v-if="message.role === 'assistant'" :src="studyflowLogo" alt="StudyFlow" />
          <span v-else>你</span>
        </div>
        <div class="bubble">
          <small v-if="message.role === 'assistant'">{{ strategyLabels[message.guidanceType || 'question'] }}</small>
          <p>{{ message.content }}</p>
          <div v-if="message.visualSteps?.length" class="visual-flow" aria-label="图示提示">
            <template v-for="(step,index) in message.visualSteps" :key="`${message.id}-${index}`">
              <div class="visual-node"><i>{{ index + 1 }}</i><span>{{ step }}</span></div>
              <b v-if="index < message.visualSteps.length - 1" class="visual-arrow">↓</b>
            </template>
          </div>
          <div v-if="message.hintChoices" class="hint-choices">
            <button v-for="option in hintOptions" :key="option.value" type="button" @click="chooseHint(option.value,message.id)">
              <b>{{ option.icon }}</b><span><strong>{{ option.label }}</strong><small>{{ option.description }}</small></span>
            </button>
          </div>
          <div v-if="message.missingDimensions?.length" class="dimensions"><span v-for="item in message.missingDimensions" :key="item">可补充：{{ item }}</span></div>
        </div>
      </article>
      <article v-if="busy" class="message assistant"><div class="avatar assistant-logo"><img :src="studyflowLogo" alt="StudyFlow" /></div><div class="bubble thinking"><i/><i/><i/></div></article>
      <ErrorNotice v-if="error" :message="error" @retry="tutor.messages.length ? send() : begin()" />
      <div v-if="tutor.masteryStatus === 'ready'" class="complete-card"><span>✓</span><div><b>本环节已达到完成条件</b><p>{{ tutor.masterySummary || '你已经展示了概念解释与迁移证据。它是形成性判断，不等同于严格考试证明。' }}</p></div><button type="button" @click="finishSession">完成并返回任务流</button></div>
      <div v-if="tutor.masteryStatus === 'ready' && tutor.reviewRecommendation" class="review-card">
        <div><small>对话反馈 → 复习建议</small><b>建议再次复习 {{ config.knowledgePoint }}</b><p>{{ tutor.reviewRecommendation.reason }}</p></div>
        <label>复习日期<input v-model="reviewDate" type="date" /></label>
        <button type="button" :disabled="reviewAdded" @click="addReviewToPlan">{{ reviewAdded ? '已加入计划' : '确认加入计划' }}</button>
      </div>
    </div>

    <form class="composer" @submit.prevent="send">
      <textarea v-model="input" :disabled="busy || tutor.masteryStatus === 'ready'" rows="2" placeholder="用自己的话回答，也可以说出你卡住的地方…" @keydown.enter.exact.prevent="send" />
      <button type="submit" :disabled="busy || !input.trim() || tutor.masteryStatus === 'ready'" aria-label="发送回答">↑</button>
      <span>Enter 发送 · Flow Tutor 会根据回答选择提示、纠错或完整讲解</span>
    </form>

    <div v-if="showExitReview" class="exit-review-backdrop" @click.self="showExitReview = false">
      <section class="exit-review-dialog" role="dialog" aria-modal="true" aria-labelledby="exit-review-title">
        <button class="dialog-close" type="button" aria-label="关闭" @click="showExitReview = false">×</button>
        <small>SESSION SUMMARY · 会话收尾</small>
        <h2 id="exit-review-title">{{ tutor.reviewRecommendation ? `${config.knowledgePoint} 掌握情况` : '当前证据不足' }}</h2>
        <p class="mastery-evidence">{{ tutor.masterySummary || '本轮尚无可评估的有效回答，因此不会推测你已经掌握或未掌握该知识点。' }}</p>
        <div v-if="tutor.reviewRecommendation" class="dialog-recommendation">
          <div><b>建议复习</b><p>{{ tutor.reviewRecommendation.reason }}</p></div>
          <label>安排到哪一天<input v-model="reviewDate" type="date" /></label>
        </div>
        <div class="dialog-actions">
          <button type="button" class="secondary" @click="leaveSession">{{ tutor.reviewRecommendation ? '暂不加入，直接退出' : '确认退出' }}</button>
          <button v-if="tutor.reviewRecommendation" type="button" class="primary" :disabled="!reviewDate" @click="addReviewAndLeave">{{ reviewAdded ? '已加入，退出' : '加入计划并退出' }}</button>
          <button type="button" class="ghost" @click="showExitReview = false">继续伴学</button>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.tutor-page{width:min(980px,calc(100vw - 310px));height:calc(100vh - 70px);display:grid;grid-template-rows:auto 1fr auto;border:1px solid rgba(221,227,247,.9);border-radius:30px;background:rgba(255,255,255,.82);box-shadow:0 24px 70px rgba(70,88,160,.12);overflow:hidden}.tutor-header{min-height:104px;padding:20px 26px;display:grid;grid-template-columns:160px 1fr 150px;align-items:center;border-bottom:1px solid #e9edfa;background:linear-gradient(100deg,#f0fbff,#f4efff)}.exit-button{justify-self:start;border:0;background:transparent;color:#6172b0;font-weight:800}.tutor-header>div:nth-child(2){display:grid;justify-items:center;gap:3px}.tutor-header p{margin:0;color:#677af2;font-size:9px;font-weight:900}.tutor-header h1{margin:0;font-size:25px}.tutor-header span{color:#7b87aa;font-size:10px}.session-state{justify-self:end;padding:9px 13px;border-radius:16px;background:#eef2ff;color:#61709d;font-size:11px;font-weight:800}.session-state i{display:inline-block;width:7px;height:7px;margin-right:6px;border-radius:50%;background:#6e7ff5}.session-state.ready{background:#e5f8f1;color:#159c72}.session-state.ready i{background:#20b982}.chat-thread{min-height:0;padding:25px 38px 34px;overflow-y:auto}.welcome{margin:0 auto 28px;padding:13px 17px;display:flex;gap:12px;border-radius:16px;background:#f5f7ff;color:#7280a5;font-size:11px}.welcome b{color:#5265d9}.message{margin:0 auto 24px;display:flex;gap:12px;max-width:780px}.message.user{flex-direction:row-reverse}.avatar{width:36px;height:36px;flex:0 0 36px;display:grid;place-items:center;border-radius:12px;background:linear-gradient(135deg,#58dce7,#7e69f2);color:white;font-size:12px;font-weight:900}.user .avatar{background:#e8edff;color:#5d6edc}.bubble{max-width:690px;padding:16px 19px;border-radius:8px 20px 20px 20px;background:#f1f5ff;color:#172052;box-shadow:0 8px 22px rgba(76,93,160,.07)}.user .bubble{border-radius:20px 8px 20px 20px;background:linear-gradient(120deg,#5bd8e6,#7875ee);color:white}.bubble small{display:block;margin-bottom:7px;color:#6375ed;font-size:9px;font-weight:900}.bubble p{margin:0;white-space:pre-line;line-height:1.72;font-size:14px}.dimensions{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.dimensions span{padding:5px 8px;border-radius:11px;background:#fff1e8;color:#ee7c39;font-size:9px}.thinking{display:flex;gap:5px;padding:18px 22px}.thinking i{width:6px;height:6px;border-radius:50%;background:#7a87d9;animation:pulse 1s infinite}.thinking i:nth-child(2){animation-delay:.15s}.thinking i:nth-child(3){animation-delay:.3s}@keyframes pulse{50%{opacity:.3;transform:translateY(-3px)}}.complete-card{margin:20px auto 0;max-width:780px;padding:18px;display:grid;grid-template-columns:42px 1fr auto;align-items:center;gap:13px;border:1px solid #bcebdc;border-radius:20px;background:#effbf7}.complete-card>span{width:42px;height:42px;display:grid;place-items:center;border-radius:50%;background:#28b887;color:#fff;font-weight:900}.complete-card b{color:#137b5b}.complete-card p{margin:5px 0 0;color:#648a7f;font-size:10px}.complete-card button{height:38px;padding:0 14px;border:0;border-radius:13px;background:#25ad80;color:#fff;font-weight:800}.composer{position:relative;margin:0 30px 24px;padding:12px 58px 28px 16px;border:1px solid #dce3f7;border-radius:20px;background:white;box-shadow:0 12px 32px rgba(68,87,160,.12)}.composer textarea{width:100%;resize:none;border:0;outline:0;background:transparent;color:#172052;font:inherit;line-height:1.55}.composer button{position:absolute;right:13px;top:13px;width:38px;height:38px;border:0;border-radius:12px;background:linear-gradient(135deg,#55d9e6,#766df0);color:white;font-size:22px}.composer button:disabled{opacity:.4}.composer>span{position:absolute;left:16px;bottom:8px;color:#9aa4c1;font-size:8px}@media(max-width:1100px){.tutor-page{width:calc(100vw - 270px)}}@media(max-width:760px){.tutor-page{width:100%;height:calc(100vh - 115px);border-radius:22px}.tutor-header{grid-template-columns:90px 1fr 90px;padding:14px}.tutor-header h1{font-size:20px}.session-state{padding:7px;font-size:9px}.chat-thread{padding:18px 14px}.composer{margin:0 12px 12px}.complete-card{grid-template-columns:36px 1fr}.complete-card button{grid-column:1/3}}
.avatar.assistant-logo{width:42px;height:42px;flex-basis:42px;padding:3px;overflow:hidden;border:1px solid rgba(184,205,255,.8);border-radius:14px;background:rgba(255,255,255,.94);box-shadow:0 8px 20px rgba(80,105,199,.18)}
.assistant-logo img{display:block;width:100%;height:100%;border-radius:10px;object-fit:cover}
.hint-choices{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:14px}.hint-choices button{padding:10px;display:flex;align-items:center;gap:9px;border:1px solid #dce4ff;border-radius:13px;background:rgba(255,255,255,.85);color:#263267;text-align:left}.hint-choices button:hover{border-color:#7b86f4;background:#fff;box-shadow:0 6px 16px rgba(83,101,190,.1)}.hint-choices button>b{width:28px;height:28px;display:grid;place-items:center;border-radius:9px;background:linear-gradient(135deg,#e3faff,#ece5ff);color:#6475e9;font-size:11px}.hint-choices button>span{display:grid;gap:2px}.hint-choices strong{font-size:11px}.hint-choices small{margin:0;color:#8792b4;font-size:8px;font-weight:500}@media(max-width:560px){.hint-choices{grid-template-columns:1fr}}
.visual-flow{margin:15px 0 4px;padding:16px;display:grid;justify-items:center;border:1px solid #d8e8ff;border-radius:18px;background:linear-gradient(150deg,#f3fcff,#f5f0ff)}.visual-node{width:min(420px,100%);padding:11px 14px;display:flex;align-items:center;gap:10px;border:1px solid rgba(126,151,239,.35);border-radius:14px;background:rgba(255,255,255,.9);box-shadow:0 6px 14px rgba(71,96,170,.08)}.visual-node i{width:24px;height:24px;flex:0 0 24px;display:grid;place-items:center;border-radius:8px;background:linear-gradient(135deg,#52dce8,#756df0);color:#fff;font-size:10px;font-style:normal;font-weight:900}.visual-node span{font-size:11px;font-weight:700;line-height:1.5}.visual-arrow{height:22px;color:#7585e8;font-size:16px;line-height:22px}
.review-card{margin:14px auto 0;max-width:780px;padding:17px 18px;display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:14px;border:1px solid #d8defa;border-radius:20px;background:linear-gradient(110deg,#f3fbff,#f6f1ff)}.review-card div{display:grid;gap:4px}.review-card small{color:#6174e9;font-size:9px;font-weight:900}.review-card p{margin:0;color:#7380a3;font-size:9px;line-height:1.5}.review-card label{display:grid;gap:5px;color:#69769a;font-size:9px}.review-card input{height:35px;padding:0 9px;border:1px solid #dce2f5;border-radius:11px;background:#fff;color:#28325f}.review-card button{height:38px;padding:0 14px;border:0;border-radius:12px;background:linear-gradient(90deg,#54dbe7,#746df0);color:#fff;font-size:10px;font-weight:800}.review-card button:disabled{opacity:.6}@media(max-width:650px){.review-card{grid-template-columns:1fr}.review-card button{width:100%}}
.exit-review-backdrop{position:fixed;z-index:1200;inset:0;padding:20px;display:grid;place-items:center;background:rgba(26,34,77,.32);backdrop-filter:blur(9px)}.exit-review-dialog{position:relative;width:min(570px,100%);padding:28px;border:1px solid rgba(255,255,255,.94);border-radius:28px;background:rgba(255,255,255,.97);box-shadow:0 30px 90px rgba(43,54,118,.28)}.dialog-close{position:absolute;right:18px;top:17px;width:34px;height:34px;border:0;border-radius:50%;background:#eef1fb;color:#7480a0;font-size:22px}.exit-review-dialog>small{color:#6073eb;font-size:9px;font-weight:900}.exit-review-dialog h2{margin:7px 0 12px;color:#172052;font-size:23px}.mastery-evidence{margin:0;padding:14px 16px;border-radius:16px;background:#f4f7ff;color:#5f6d92;font-size:11px;line-height:1.7}.dialog-recommendation{margin-top:14px;padding:15px;display:grid;grid-template-columns:1fr auto;align-items:center;gap:14px;border:1px solid #dbe2fa;border-radius:17px;background:linear-gradient(110deg,#effbff,#f5f0ff)}.dialog-recommendation div{display:grid;gap:5px}.dialog-recommendation b{color:#5064dd;font-size:12px}.dialog-recommendation p{margin:0;color:#7380a3;font-size:9px;line-height:1.55}.dialog-recommendation label{display:grid;gap:5px;color:#69769a;font-size:9px}.dialog-recommendation input{height:36px;padding:0 9px;border:1px solid #dce2f5;border-radius:11px;background:#fff;color:#28325f}.dialog-actions{margin-top:20px;display:flex;justify-content:flex-end;gap:9px;flex-wrap:wrap}.dialog-actions button{height:39px;padding:0 14px;border:0;border-radius:12px;font-size:10px;font-weight:800}.dialog-actions .primary{background:linear-gradient(90deg,#54dbe7,#746df0);color:#fff}.dialog-actions .secondary{background:#eef1f8;color:#66718f}.dialog-actions .ghost{background:transparent;color:#5d70e6}.dialog-actions button:disabled{opacity:.45}@media(max-width:560px){.dialog-recommendation{grid-template-columns:1fr}.dialog-actions button{width:100%}}
</style>
