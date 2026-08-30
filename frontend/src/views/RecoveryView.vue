<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import RecoveryAction from '../components/RecoveryAction.vue'
import { recoverLearning } from '../services/agent'
import { errorMessage } from '../services/api'
import { useSessionStore } from '../stores/session'
import { usePlanStore } from '../stores/plan'
import nebulaBackground from '../assets/thought-nebula-bg.png'
import sendIcon from '../assets/thought-send.svg'
import voiceIcon from '../assets/thought-voice.svg'
import type { BlockType, RecoveryResponse } from '../types'

const session = useSessionStore()
const plans = usePlanStore()
const block = ref<BlockType>((sessionStorage.getItem('studyflow-block') as BlockType) || 'time')
const context = ref(session.selectedTask ? `当前任务：${session.selectedTask.title}` : '')
const result = ref<RecoveryResponse | null>(null)
const busy = ref(false)
const error = ref('')
const applied = ref(false)
const appliedSummary = ref('')
const launched = ref(false)
const launchSequence = ref(0)

interface LaunchPreset {
  path: string
  starPoints: string
  duration: number
}

const launchPreset = ref<LaunchPreset | null>(null)
let launchResetTimer: number | undefined
let previousStarSize = 0

function randomBetween(min: number, max: number) {
  return Math.random() * (max - min) + min
}

function createStarPoints(size: number) {
  const points: string[] = []
  const outerRadius = size / 2
  const innerRadius = outerRadius * 0.45
  for (let index = 0; index < 10; index += 1) {
    const radius = index % 2 === 0 ? outerRadius : innerRadius
    const angle = -Math.PI / 2 + index * Math.PI / 5
    points.push(`${(Math.cos(angle) * radius).toFixed(1)},${(Math.sin(angle) * radius).toFixed(1)}`)
  }
  return points.join(' ')
}

function createLaunchPreset(): LaunchPreset {
  let starSize = Math.round(randomBetween(38, 72))
  if (Math.abs(starSize - previousStarSize) < 8) {
    starSize = starSize > 55 ? Math.max(38, starSize - 13) : Math.min(72, starSize + 13)
  }
  previousStarSize = starSize

  const startX = Math.round(randomBetween(820, 950))
  const startY = Math.round(randomBetween(480, 545))
  const endX = Math.round(randomBetween(105, 430))
  const endY = Math.round(randomBetween(48, 165))
  const controlOneX = Math.round(startX - randomBetween(130, 300))
  const controlOneY = Math.round(startY - randomBetween(10, 120))
  const controlTwoX = Math.round(endX + randomBetween(90, 330))
  const controlTwoY = Math.round(endY + randomBetween(35, 240))

  return {
    path: `M ${startX} ${startY} C ${controlOneX} ${controlOneY} ${controlTwoX} ${controlTwoY} ${endX} ${endY}`,
    starPoints: createStarPoints(starSize),
    duration: Number(randomBetween(1.15, 1.7).toFixed(2)),
  }
}

function startLaunch() {
  if (launchResetTimer !== undefined) window.clearTimeout(launchResetTimer)
  launchSequence.value += 1
  launchPreset.value = createLaunchPreset()
  launched.value = true
  launchResetTimer = window.setTimeout(() => {
    launched.value = false
    launchPreset.value = null
    context.value = ''
  }, (launchPreset.value.duration + 0.55) * 1000)
}

function inferBlockType(value: string): BlockType {
  if (/学不会|不会做|太难|看不懂|跟不上/.test(value)) return 'too_hard'
  if (/时间不够|来不及|没时间|赶不完/.test(value)) return 'time'
  if (/累|疲惫|困|没精神/.test(value)) return 'fatigue'
  return 'distraction'
}

async function recover(acceptance?: boolean) {
  const submittedContext = context.value
  if (acceptance === undefined) {
    block.value = inferBlockType(submittedContext)
    sessionStorage.setItem('studyflow-block', block.value)
    startLaunch()
  }
  busy.value = true
  error.value = ''
  try {
    result.value = await recoverLearning({
      user_id: session.userId,
      course: session.course,
      block_type: block.value,
      context: submittedContext,
      task_type: session.selectedTask?.task_type || 'study',
      knowledge_point: session.selectedTask?.knowledge_point || session.knowledgePoint || undefined,
      ...(acceptance === undefined ? {} : { user_acceptance: acceptance }),
    })
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

function apply() {
  applied.value = true
  appliedSummary.value = plans.applyRecoveryAdjustment(
    block.value,
    session.selectedTask?.id,
    result.value?.action || '',
  )
  recover(true)
}

function reject() {
  applied.value = false
  recover(false)
}

onBeforeUnmount(() => {
  if (launchResetTimer !== undefined) window.clearTimeout(launchResetTimer)
})
</script>

<template>
  <section class="thought-page" :style="{ '--nebula-background': `url(${nebulaBackground})` }">
    <div class="cosmic-veil" aria-hidden="true" />
    <header class="thought-intro">
      <p class="thought-eyebrow">THOUGHT NEBULA · PRIVATE SPACE</p>
      <h1>让此刻的思绪，成为一束光</h1>
      <p>把压力、分心或疲惫轻轻放进星空。<br>每一次表达，都在为混乱找到位置。</p>
    </header>
    <div class="privacy-status">◉ 仅自己可见</div>

    <div v-if="launched && launchPreset" :key="launchSequence" class="launch-scene" aria-live="polite">
      <svg
        class="launch-svg"
        viewBox="0 0 1000 560"
        preserveAspectRatio="none"
        :style="{
          '--launch-duration': `${launchPreset.duration}s`,
          '--trail-fade-delay': `${launchPreset.duration}s`,
        }"
        aria-hidden="true"
      >
        <defs>
          <filter id="star-glow" x="-180%" y="-180%" width="460%" height="460%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <linearGradient id="trail-gradient" x1="1" y1="1" x2="0" y2="0">
            <stop offset="0" stop-color="#88a5e0" stop-opacity="0" />
            <stop offset="0.34" stop-color="#c8ddf5" stop-opacity="0.72" />
            <stop offset="1" stop-color="#ffffff" stop-opacity="0.98" />
          </linearGradient>
        </defs>
        <path class="trail-glow" :d="launchPreset.path" pathLength="1" />
        <path class="trail-core" :d="launchPreset.path" pathLength="1" />
        <g class="moving-star" filter="url(#star-glow)">
          <polygon :points="launchPreset.starPoints" fill="#ffffff" />
          <animateMotion
            :dur="`${launchPreset.duration}s`"
            :path="launchPreset.path"
            fill="freeze"
            calcMode="spline"
            keyTimes="0;1"
            keySplines=".2 .65 .28 1"
          />
        </g>
      </svg>
      <span class="sr-only">心情已化为星星，正在划过星空</span>
    </div>

    <form class="launch-composer" @submit.prevent="recover()">
      <div><h2>{{ launched ? '已发射至星空' : '发射此刻心情' }}</h2><p>当前支持文字输入；语音能力待接入</p></div>
      <div class="thought-input">
        <label class="sr-only" for="thought-context">输入此刻的思绪</label>
        <input id="thought-context" v-model.trim="context" type="text" placeholder="输入此刻的思绪…" :disabled="busy">
        <button class="launch-button" type="submit" :disabled="busy" aria-label="发射此刻心情"><img :src="sendIcon" alt=""></button>
        <span class="input-divider" aria-hidden="true" />
        <button class="voice-button" type="button" disabled title="语音输入暂未接入" aria-label="语音输入暂未接入"><img :src="voiceIcon" alt=""></button>
      </div>
      <small>◉ 默认仅自己可见</small>
    </form>
  </section>

  <section v-if="busy || error || result || applied" class="recovery-output stack">
    <LoadingState v-if="busy" text="正在结合阻塞类型与过往恢复经验…" />
    <ErrorNotice v-if="error" :message="error" @retry="recover()" />
    <RecoveryAction v-if="result && !applied" :result="result" @accept="apply" @reject="reject" />
    <div v-if="applied" class="applied-plan card panel"><div><p class="eyebrow">弹性任务流已更新</p><h2>这次反馈已经改变任务安排</h2><p>{{ appliedSummary }}</p><small>调整已保存在当前浏览器会话；确认后的恢复经验同时交由反馈记忆处理。</small></div><RouterLink class="btn btn-primary" to="/today">查看调整后的任务流 →</RouterLink></div>
    <div v-if="result" class="impact card panel">
      <div><p class="eyebrow">调整影响 · 会话演示</p><h2>应用后，计划会发生这些变化</h2></div>
      <div class="grid-3">
        <div class="metric"><span>当前任务</span><strong>{{ session.selectedTask?.duration_minutes || 25 }} 分钟</strong><small class="muted">保留核心目标</small></div>
        <div class="metric"><span>本次动作</span><strong>1 项</strong><small class="muted">来自真实恢复建议</small></div>
        <div class="metric"><span>长期数据</span><strong>不写入</strong><small class="muted">仅本次浏览器会话</small></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.thought-page{position:relative;min-height:100vh;margin:-40px 0 -70px -36px;overflow:hidden;color:white;background:#0b1838 var(--nebula-background) center/cover no-repeat;isolation:isolate}.cosmic-veil{position:absolute;inset:0;z-index:-1;background:linear-gradient(180deg,rgba(11,24,56,.74),rgba(58,96,160,.04) 42%,rgba(11,24,56,.54)),linear-gradient(180deg,transparent 58%,rgba(11,24,56,.9))}.thought-intro{position:absolute;top:58px;left:46px}.thought-eyebrow{margin-bottom:18px;color:#c8ddf5;font-size:11px;font-weight:800;letter-spacing:.06em}.thought-intro h1{margin:0 0 12px;font-size:clamp(29px,3vw,38px);line-height:1.2}.thought-intro>p:last-child{color:#c8ddf5;font-size:14px;line-height:1.75}.privacy-status{position:absolute;top:66px;right:40px;padding:11px 27px;border:1px solid rgba(200,221,245,.26);border-radius:999px;background:rgba(11,24,56,.38);color:#c8ddf5;font-size:11px;backdrop-filter:blur(18px)}
.launch-composer{position:absolute;right:40px;bottom:66px;left:46px;display:grid;gap:10px;padding:22px 28px 20px;border:1.25px solid rgba(200,221,245,.62);border-radius:30px;background:rgba(200,221,245,.16);box-shadow:0 20px 44px rgba(11,24,56,.42);backdrop-filter:blur(28px)}.launch-composer h2{margin:0;font-size:24px}.launch-composer p{margin:4px 0 0;color:#c8ddf5;font-size:11px}.launch-composer>small{color:#c8ddf5;font-size:10px}.thought-input{display:grid;grid-template-columns:minmax(0,1fr) 44px 1px 44px;align-items:center;min-height:58px;overflow:hidden;border:1px solid rgba(255,255,255,.7);border-radius:19px;background:rgba(200,221,245,.72);box-shadow:inset 2px 3px 6px rgba(58,96,160,.24)}.thought-input input{width:100%;height:56px;padding:0 18px;border:0;outline:0;color:#0b1838;background:transparent}.thought-input input::placeholder{color:rgba(11,24,56,.72)}.thought-input button{width:44px;height:44px;padding:12px;border:0;background:transparent}.thought-input button:not(:disabled):hover{filter:brightness(1.18);transform:scale(1.06)}.thought-input button img{display:block;width:20px;height:20px}.voice-button:disabled{cursor:default;opacity:.75}.input-divider{width:1px;height:28px;background:rgba(58,96,160,.44)}
.launch-scene{position:absolute;inset:126px 34px 255px 40px;pointer-events:none}.launch-svg{width:100%;height:100%;overflow:visible}.trail-core,.trail-glow{fill:none;stroke-linecap:round;stroke-dasharray:1;stroke-dashoffset:1;animation:draw-trail var(--launch-duration) cubic-bezier(.2,.65,.28,1) forwards,fade-trail .45s var(--trail-fade-delay) ease-out forwards}.trail-core{stroke:url(#trail-gradient);stroke-width:2.2;vector-effect:non-scaling-stroke}.trail-glow{stroke:#88a5e0;stroke-width:9;opacity:.5;filter:blur(7px);vector-effect:non-scaling-stroke}.moving-star{animation:star-arrive var(--launch-duration) cubic-bezier(.2,.65,.28,1) both,fade-star .45s var(--trail-fade-delay) ease-out forwards}.recovery-output{margin:96px 0 40px}.impact h2{margin:4px 0 18px}
.applied-plan{display:flex;align-items:center;justify-content:space-between;gap:24px;border-color:#bfe9dc;background:linear-gradient(110deg,#ecfaf5,#eef4ff)}.applied-plan h2{margin:4px 0 8px}.applied-plan p:not(.eyebrow){margin:0;color:#3f5277;line-height:1.65}.applied-plan small{display:block;margin-top:8px;color:#7b88aa}.applied-plan a{text-decoration:none;white-space:nowrap}
@keyframes draw-trail{0%{stroke-dashoffset:1;opacity:0}8%{opacity:1}100%{stroke-dashoffset:0;opacity:1}}@keyframes fade-trail{to{opacity:0}}@keyframes star-arrive{0%{opacity:.15}20%{opacity:1}100%{opacity:1}}@keyframes fade-star{to{opacity:0}}@media(prefers-reduced-motion:reduce){.trail-core,.trail-glow,.moving-star{animation-duration:.01ms!important;animation-delay:0s!important}}
@media(max-width:760px){.thought-page{min-height:calc(100vh - 20px);margin:-20px -14px -94px}.thought-intro{top:34px;left:22px;right:22px}.thought-eyebrow{margin-bottom:12px;font-size:9px}.thought-intro h1{max-width:320px;font-size:26px}.thought-intro>p:last-child{font-size:12px}.privacy-status{top:36px;right:18px;padding:8px 12px;font-size:9px}.launch-composer{right:16px;bottom:92px;left:16px;gap:8px;padding:18px 16px 15px;border-radius:24px}.launch-composer h2{font-size:20px}.thought-input{grid-template-columns:minmax(0,1fr) 38px 1px 38px;min-height:50px}.thought-input input{height:48px;padding:0 12px;font-size:12px}.thought-input button{width:38px;height:38px;padding:9px}.launch-scene{inset:160px 8px 270px}.recovery-output{margin-top:118px}}
</style>
