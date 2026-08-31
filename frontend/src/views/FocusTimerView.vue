<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { usePlanStore } from '../stores/plan'
import { useSessionStore } from '../stores/session'

const router = useRouter()
const session = useSessionStore()
const plans = usePlanStore()
const task = computed(() => session.selectedTask)
const resumableSeconds = task.value && session.focusTaskId === task.value.id ? session.focusRemainingSeconds : null
const remainingSeconds = ref(resumableSeconds ?? Math.max(1, task.value?.duration_minutes || 25) * 60)
const running = ref(true)
const showMoreTime = ref(false)
const extraMinutes = ref<number | null>(null)
const timeError = ref('')
let timer: number | undefined

const timeText = computed(() => {
  const minutes = Math.floor(remainingSeconds.value / 60).toString().padStart(2, '0')
  const seconds = (remainingSeconds.value % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
})
const progress = computed(() => {
  const total = Math.max(1, (task.value?.duration_minutes || 25) * 60)
  return Math.max(0, Math.min(100, remainingSeconds.value / total * 100))
})

function tick() {
  if (running.value && remainingSeconds.value > 0) remainingSeconds.value -= 1
  if (task.value) session.setFocusProgress(task.value.id, remainingSeconds.value)
  if (remainingSeconds.value === 0) running.value = false
}
function openMoreTime() {
  running.value = false
  showMoreTime.value = true
  timeError.value = ''
}
function continueLearning() {
  if (extraMinutes.value === null || !Number.isFinite(extraMinutes.value) || extraMinutes.value < 1 || extraMinutes.value > 240) {
    timeError.value = '请输入 1–240 分钟。'
    return
  }
  const addedMinutes = Math.round(extraMinutes.value)
  remainingSeconds.value += addedMinutes * 60
  if (task.value) {
    task.value.duration_minutes = Math.ceil(remainingSeconds.value / 60)
    session.setFocusProgress(task.value.id, remainingSeconds.value)
    plans.localAdjustment = `检测到“时间不够”：已在当时剩余时间的基础上增加 ${addedMinutes} 分钟，当前剩余 ${timeText.value}。`
  }
  showMoreTime.value = false
  running.value = true
}
function closeMoreTime() {
  showMoreTime.value = false
  running.value = true
}
function finishEarly() {
  if (task.value) plans.statuses[task.value.id] = 'completed'
  session.clearFocusProgress()
  session.selectedTask = null
  router.push('/today')
}
function releaseThought() {
  if (task.value) session.setFocusProgress(task.value.id, remainingSeconds.value)
  sessionStorage.setItem('studyflow-block', 'distraction')
  router.push('/recovery')
}

onMounted(() => {
  if (!task.value) {
    router.replace('/today')
    return
  }
  timer = window.setInterval(tick, 1000)
  session.setFocusProgress(task.value.id, remainingSeconds.value)
})
onBeforeUnmount(() => {
  if (timer !== undefined) window.clearInterval(timer)
  if (task.value) session.setFocusProgress(task.value.id, remainingSeconds.value)
})
</script>

<template>
  <section v-if="task" class="focus-page">
    <header class="focus-header"><span>FOCUS FLOW</span><h1>{{ task.title }}</h1><p>{{ task.description }}</p></header>
    <article class="timer-card" :class="{ finished: remainingSeconds === 0 }">
      <div class="timer-orbit"><div class="timer-core"><small>{{ remainingSeconds === 0 ? '本轮时间已到' : '专注倒计时' }}</small><strong>{{ timeText }}</strong><span>{{ running ? '保持当前节奏' : '计时已暂停' }}</span></div></div>
      <div class="progress-track"><i :style="{ width: `${progress}%` }" /></div>
      <p>任务预计 {{ task.duration_minutes }} 分钟 · 离开此页会暂停并保留当前倒计时</p>
      <div class="focus-actions">
        <button type="button" class="more-time" @click="openMoreTime">时间不够</button>
        <button type="button" class="finish-early" @click="finishEarly">提前完成</button>
        <button type="button" class="release-thought" @click="releaseThought">✦ 杂念释放</button>
      </div>
    </article>

    <div v-if="showMoreTime" class="time-backdrop" @click.self="closeMoreTime">
      <form class="time-dialog" role="dialog" aria-modal="true" aria-labelledby="more-time-title" @submit.prevent="continueLearning">
        <button type="button" class="dialog-close" aria-label="关闭" @click="closeMoreTime">×</button>
        <span>追加本轮时间</span><h2 id="more-time-title">希望增加多少分钟？</h2>
        <p>填写的分钟数会加在当前剩余时间上，不会重置已经完成的倒计时。</p>
        <label><input v-model.number="extraMinutes" type="number" min="1" max="240" step="1" placeholder="例如：10" autofocus /><b>分钟</b></label>
        <p v-if="timeError" class="time-error" role="alert">{{ timeError }}</p>
        <div class="dialog-actions"><button type="button" @click="closeMoreTime">取消</button><button class="continue-button">增加并继续</button></div>
      </form>
    </div>
  </section>
</template>

<style scoped>
.focus-page{width:820px;color:#172052}.focus-header{text-align:center;margin:18px 0 28px}.focus-header>span{color:#6379ee;font-size:11px;font-weight:900;letter-spacing:.12em}.focus-header h1{margin:8px 0 6px;font-size:30px}.focus-header p{margin:0;color:#7a86a7;font-size:13px}.timer-card{padding:34px 42px;border:1px solid rgba(255,255,255,.9);border-radius:34px;background:linear-gradient(135deg,rgba(215,249,252,.85),rgba(237,224,255,.82) 53%,rgba(218,228,255,.9));box-shadow:0 24px 60px rgba(80,100,180,.15);text-align:center}.timer-orbit{width:290px;height:290px;margin:0 auto 22px;padding:12px;border-radius:50%;background:conic-gradient(#51dce8,#747df5,#b77cf0,#51dce8);box-shadow:0 18px 42px rgba(101,121,221,.2)}.timer-core{height:100%;display:grid;place-content:center;gap:8px;border-radius:50%;background:rgba(250,252,255,.94);box-shadow:inset 0 0 30px rgba(93,120,226,.1)}.timer-core small{color:#6576d9;font-weight:800}.timer-core strong{font-size:62px;line-height:1;letter-spacing:-2px}.timer-core span{color:#8993ae;font-size:11px}.progress-track{height:7px;overflow:hidden;border-radius:7px;background:rgba(255,255,255,.7)}.progress-track i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#4edce9,#697cf3,#a478ef);transition:width 1s linear}.timer-card>p{margin:12px 0 24px;color:#7a86a7;font-size:11px}.focus-actions{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.focus-actions button{height:48px;border:0;border-radius:16px;font-weight:900;cursor:pointer}.more-time{background:#fff;color:#5269df}.finish-early{background:linear-gradient(90deg,#52d9e6,#657ef1);color:#fff}.release-thought{background:#202b5c;color:#fff}.time-backdrop{position:fixed;z-index:1000;inset:0;display:grid;place-items:center;padding:20px;background:rgba(25,31,70,.3);backdrop-filter:blur(8px)}.time-dialog{position:relative;width:min(430px,100%);padding:28px;border-radius:26px;background:#fff;box-shadow:0 30px 80px rgba(35,47,110,.28);text-align:left}.time-dialog>span{color:#6477e8;font-size:10px;font-weight:900}.time-dialog h2{margin:7px 0 8px;font-size:22px}.time-dialog>p{color:#7a86a7;font-size:12px}.dialog-close{position:absolute;right:20px;top:18px;width:34px;height:34px;border:0;border-radius:50%;background:#eef1fa;color:#7782a0;font-size:20px}.time-dialog label{height:58px;margin:20px 0 8px;display:grid;grid-template-columns:1fr 64px;align-items:center;border:1px solid #dfe4f3;border-radius:16px;overflow:hidden}.time-dialog input{height:100%;min-width:0;padding:0 16px;border:0;outline:0;font-size:25px;font-weight:800}.time-dialog label b{color:#7480a0}.time-error{color:#d9506c!important}.dialog-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}.dialog-actions button{height:40px;padding:0 18px;border:0;border-radius:13px;background:#eef1f8;color:#697596;font-weight:800}.dialog-actions .continue-button{background:linear-gradient(90deg,#52d9e6,#7772ef);color:#fff}@media(max-width:760px){.focus-page{width:100%}.timer-card{padding:26px 18px}.timer-orbit{width:230px;height:230px}.timer-core strong{font-size:50px}.focus-actions{grid-template-columns:1fr}}
</style>
