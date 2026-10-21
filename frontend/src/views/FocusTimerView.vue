<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { usePlanStore } from '../stores/plan'
import { useSessionStore } from '../stores/session'
import ErrorNotice from '../components/ErrorNotice.vue'
import { errorMessage } from '../services/api'

const router = useRouter()
const session = useSessionStore()
const plans = usePlanStore()
const task = computed(() => session.selectedTask)
const isPreview = computed(() => task.value?.id.startsWith('preview-') ?? false)
const resumableSeconds = task.value && session.focusTaskId === task.value.id ? session.focusRemainingSeconds : null
const remainingSeconds = ref(resumableSeconds ?? Math.max(1, task.value?.duration_minutes || 25) * 60)
const running = ref(true)
const showMoreTime = ref(false)
const extraMinutes = ref<number | null>(null)
const timeError = ref('')
const saving = ref(false)
const saveError = ref('')
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
async function finishEarly() {
  if (!task.value || saving.value) return
  if (isPreview.value) {
    session.clearFocusProgress()
    session.selectedTask = null
    await router.push('/today')
    return
  }
  saving.value = true
  saveError.value = ''
  running.value = false
  try {
    await plans.completeTask(session.userId, { ...task.value, course: task.value.course || session.course })
    session.clearFocusProgress()
    session.selectedTask = null
    await router.push('/today')
  } catch (cause) { saveError.value = errorMessage(cause) }
  finally { saving.value = false }
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
    <header class="focus-header">
      <div><span class="focus-kicker"><i /> FOCUS FLOW · 专注空间</span><h1>把这一刻，留给专注。</h1><p>不必一次走完所有路，先完成眼前这一小步。</p></div>
      <span class="session-label">{{ isPreview ? '体验模式' : '当前任务' }} <b>01</b></span>
    </header>
    <article class="timer-card" :class="{ finished: remainingSeconds === 0 }">
      <div class="focus-workspace">
        <div class="timer-stage">
          <div class="stage-top"><span><i :class="{ paused: !running }" />{{ remainingSeconds === 0 ? '本轮结束' : running ? '专注进行中' : '已暂停' }}</span><span>STAY IN THE FLOW</span></div>
          <div class="timer-orbit">
            <svg class="timer-ring" viewBox="0 0 300 300" aria-hidden="true"><defs><linearGradient id="focus-ring-gradient" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#42cfdf"/><stop offset=".52" stop-color="#7183f4"/><stop offset="1" stop-color="#a488ed"/></linearGradient></defs><circle class="ring-track" cx="150" cy="150" r="137"/><circle class="ring-progress" cx="150" cy="150" r="137" pathLength="100" :stroke-dasharray="`${progress} 100`"/></svg>
            <div class="timer-core"><small>{{ remainingSeconds === 0 ? '本轮时间已到' : '剩余专注时间' }}</small><strong>{{ timeText }}</strong><span>{{ remainingSeconds === 0 ? '每一步，都算数' : running ? '让注意力慢慢沉下来' : '准备好后，继续向前' }}</span></div>
          </div>
          <div class="stage-bottom"><span>专注当下</span><i /><span>保持自己的节奏</span></div>
        </div>
        <div class="session-detail">
          <span class="detail-kicker">YOUR NEXT SMALL STEP</span>
          <h2>{{ task.title }}</h2><p class="task-description">{{ task.description }}</p>
          <div class="session-facts"><div><span>本轮计划</span><strong>{{ task.duration_minutes }}<small> 分钟</small></strong></div><div><span>当前节奏</span><strong class="pace-label">{{ remainingSeconds === 0 ? '已结束' : running ? '专注中' : '已暂停' }}</strong></div></div>
          <div class="session-progress"><div><span>本轮进度</span><b>{{ Math.round(100 - progress) }}%</b></div><div class="progress-track"><i :style="{ width: `${100 - progress}%` }" /></div></div>
          <div class="focus-reminder"><span aria-hidden="true">↗</span><p>允许思绪偶尔游走，<br />再轻轻把注意力带回来。</p></div>
          <p class="autosave-note"><span aria-hidden="true">◷</span> 离开此页会暂停，并保留当前倒计时</p>
        </div>
      </div>
      <div v-if="isPreview" class="preview-note" role="note">
        <span class="preview-note-icon" aria-hidden="true">✦</span>
        <div><strong>正在体验示例任务</strong><span>体验记录不会保存，创建自己的任务后即可记录学习进度。</span></div>
        <button type="button" @click="router.push('/today')">去创建任务 <span aria-hidden="true">→</span></button>
      </div>
      <ErrorNotice v-if="saveError" class="focus-save-error" :message="saveError" @retry="finishEarly" />
      <div class="focus-actions"><span class="actions-hint">按你的节奏，灵活调整</span>
        <button type="button" class="more-time" :disabled="saving" @click="openMoreTime"><span aria-hidden="true">＋</span> 时间不够</button>
        <button type="button" class="finish-early" :disabled="saving" @click="finishEarly">{{ isPreview ? '结束体验' : saving ? '正在保存…' : remainingSeconds === 0 ? '确认完成' : '提前完成' }}</button>
        <button type="button" class="release-thought" :disabled="saving" @click="releaseThought">✦ 杂念释放</button>
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
.preview-note{display:flex;align-items:center;gap:12px;margin:0 0 18px;padding:14px 16px;border:1px solid rgba(255,255,255,.85);border-radius:18px;background:rgba(255,255,255,.48);text-align:left;color:#65749b}
.preview-note-icon{display:grid;place-items:center;flex:0 0 32px;height:32px;border-radius:11px;background:rgba(111,126,239,.09);color:#7781d9;font-size:17px}
.preview-note>div{display:grid;gap:4px;flex:1;min-width:0}
.preview-note strong{font-size:12px;font-weight:700;color:#53648d}
.preview-note>div>span{font-size:11px;line-height:1.65}
.preview-note button{flex-shrink:0;padding:8px 0 8px 12px;border:0;background:transparent;color:#586bd5;font-size:12px;font-weight:700;cursor:pointer}
.preview-note button:focus-visible{outline:2px solid #697cf3;outline-offset:4px;border-radius:6px}
.focus-save-error{margin-bottom:18px;text-align:left}
@media(max-width:520px){.preview-note{flex-wrap:wrap;gap:10px}.preview-note>div{flex-basis:calc(100% - 44px)}.preview-note button{margin-left:44px;padding:0}}
.time-backdrop{position:fixed;z-index:1000;inset:0;display:grid;place-items:center;padding:20px;background:rgba(25,31,70,.3);backdrop-filter:blur(8px)}.time-dialog{position:relative;width:min(430px,100%);padding:28px;border-radius:26px;background:#fff;box-shadow:0 30px 80px rgba(35,47,110,.28);text-align:left}.time-dialog>span{color:#6477e8;font-size:10px;font-weight:900}.time-dialog h2{margin:7px 0 8px;font-size:22px}.time-dialog>p{color:#7a86a7;font-size:12px}.dialog-close{position:absolute;right:20px;top:18px;width:34px;height:34px;border:0;border-radius:50%;background:#eef1fa;color:#7782a0;font-size:20px}.time-dialog label{height:58px;margin:20px 0 8px;display:grid;grid-template-columns:1fr 64px;align-items:center;border:1px solid #dfe4f3;border-radius:16px;overflow:hidden}.time-dialog input{height:100%;min-width:0;padding:0 16px;border:0;outline:0;font-size:25px;font-weight:800}.time-dialog label b{color:#7480a0}.time-error{color:#d9506c!important}.dialog-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}.dialog-actions button{height:40px;padding:0 18px;border:0;border-radius:13px;background:#eef1f8;color:#697596;font-weight:800}.dialog-actions .continue-button{background:linear-gradient(90deg,#52d9e6,#7772ef);color:#fff}/* Match the shared cyan, blue and lavender theme. */
.focus-page{width:100%;max-width:820px;padding-top:8px}
.focus-header{display:flex;align-items:center;justify-content:space-between;gap:20px;text-align:left;margin:8px 0 26px}
.focus-kicker{display:flex;align-items:center;gap:8px;color:#7b84a6;font-size:9px;font-weight:700;letter-spacing:.13em}
.focus-kicker i{width:6px;height:6px;border-radius:50%;background:var(--brand);box-shadow:0 0 0 4px #e9ecfc}
.focus-header h1{margin:14px 0 9px;font-size:29px;font-weight:650;letter-spacing:-1px;color:var(--text)}
.focus-header p{font-size:11px;color:#929bb4;line-height:1.8}
.session-label{flex-shrink:0;display:flex;align-items:center;gap:12px;padding:9px 12px;border:1px solid #e3e7f3;border-radius:10px;color:#8a95b0;font-size:9px;background:#ffffff80}
.session-label b{border-left:1px solid #e1e5f0;padding-left:12px;color:#63739a;font-size:12px;font-variant-numeric:tabular-nums}
.timer-card{padding:12px;border:1px solid #e5e9f4;border-radius:26px;background:#ffffffdc;box-shadow:0 16px 48px #283c7c09;text-align:left}
.focus-workspace{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:0}
.timer-stage{position:relative;min-width:0;overflow:hidden;display:flex;flex-direction:column;justify-content:space-between;padding:23px 23px 22px;min-height:376px;border-radius:19px;border:1px solid #e3e8fa;background:radial-gradient(ellipse at 8% 0%,#d9f7fbcc,transparent 65%),radial-gradient(ellipse at 100% 100%,#e9e0fbc9,transparent 65%),#edf2ff;color:var(--text)}
.stage-top{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:9px;color:#697ca0}
.stage-top>span:first-child{display:flex;align-items:center;gap:7px}.stage-top>span:last-child{font-size:7px;letter-spacing:.12em;color:#8d9bbc}
.stage-top i{width:5px;height:5px;border-radius:50%;background:#40bba4;box-shadow:0 0 0 3px #40bba416}.stage-top i.paused{background:#aa94cf}
.timer-orbit{position:relative;width:min(100%,278px);height:auto;aspect-ratio:1;margin:20px auto;padding:0;background:transparent;box-shadow:none}
.timer-ring{position:absolute;inset:0;width:100%;height:100%;overflow:visible;transform:rotate(-90deg)}
.timer-ring circle{fill:none;stroke-width:3}.ring-track{stroke:#dce4f5}.ring-progress{stroke:url(#focus-ring-gradient);stroke-linecap:round;transition:stroke-dasharray 1s linear;filter:drop-shadow(0 3px 5px #7183f426)}
.timer-core{position:absolute;inset:15px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;border:1px solid #ffffffdc;background:linear-gradient(145deg,#ffffffcc,#f5f7ffb3);box-shadow:0 12px 35px #7c8fc312,inset 0 2px 14px #ffffff80}
.timer-core small{color:#7d89b0;font-size:10px;letter-spacing:.12em;font-weight:500}.timer-core strong{font-size:60px;font-weight:400;letter-spacing:-2px;font-variant-numeric:tabular-nums;color:var(--text);line-height:1.1}.timer-core span{color:#8898b8;font-size:10px}
.stage-bottom{display:flex;align-items:center;justify-content:center;gap:12px;font-size:9px;color:#8a99b8}.stage-bottom i{width:20px;height:1px;background:#becbe3}
.session-detail{min-width:0;display:flex;flex-direction:column;padding:25px 24px 16px}
.detail-kicker{color:#98a2bb;font-size:8px;letter-spacing:.12em;font-weight:600}.session-detail h2{margin:14px 0 8px;color:var(--text);font-size:21px;line-height:1.5;font-weight:650;overflow-wrap:anywhere}.task-description{margin:0;color:#8b97b0;font-size:11px;line-height:1.8;overflow-wrap:anywhere}
.session-facts{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:24px 0 20px}.session-facts>div{display:grid;gap:8px}.session-facts>div+div{padding-left:18px;border-left:1px solid #e9edf5}.session-facts span{font-size:9px;color:#94a0b9}.session-facts strong{font-size:26px;color:#4a597d;font-weight:500;line-height:1.2}.session-facts small{font-size:10px;font-weight:400;color:#8a96b1}.session-facts .pace-label{font-size:15px;line-height:31px;color:#659f96}
.session-progress>div:first-child{display:flex;justify-content:space-between;margin-bottom:9px;font-size:9px;color:#8d99b2}.session-progress b{color:#7387ae;font-weight:500}.progress-track{height:4px;background:#eef1f8}.progress-track i{background:linear-gradient(90deg,#42cfdf,#7183f4,#a488ed)}
.focus-reminder{display:flex;align-items:flex-start;gap:10px;margin:22px 0 16px;padding:12px;background:#f6f8fc;border-radius:12px;color:#8a98b3}.focus-reminder>span{font-size:18px;color:#8c99c1}.focus-reminder p{margin:0;font-size:10px;line-height:1.85}.autosave-note{margin:auto 0 0;color:#9ba5bb;font-size:8px;line-height:1.8}
.preview-note{margin:12px 4px 0;padding:13px 12px;border:1px solid #e9edf6;border-radius:12px;background:#f8faff;gap:10px}.preview-note-icon{flex-basis:27px;height:27px;font-size:14px;border-radius:9px}.preview-note strong{font-size:10px}.preview-note>div>span{font-size:9px;color:#8a97b0}.preview-note button{font-size:10px;color:#7b85bc}
.focus-actions{display:flex;align-items:center;gap:10px;padding:17px 6px 5px;margin-top:4px}.actions-hint{margin-right:auto;color:#9aa4ba;font-size:9px}.focus-actions button{height:39px;padding:0 17px;border-radius:11px;font-size:10px;font-weight:600;transition:background .2s,box-shadow .2s,transform .2s}.focus-actions button:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 5px 14px #52639814}.focus-actions button:focus-visible{outline:2px solid #7989d3;outline-offset:3px}.focus-actions button:disabled{opacity:.5;cursor:wait}.more-time{border:1px solid var(--border)!important;background:#f7f9ff;color:var(--brand)}.finish-early{order:3;background:linear-gradient(100deg,#42ccdf,#697df1 70%,#8a77ef);color:#fff;box-shadow:0 5px 14px #697df12b}.release-thought{background:#efebff;color:#8a73be}.focus-save-error{margin:12px 4px}
.finished .ring-progress{stroke:#51b69a}.finished .timer-core strong{color:#358a74}
@media(max-width:760px){.focus-page{max-width:100%}.focus-header h1{font-size:25px}.focus-header{margin:4px 0 20px}.session-label{display:none}.focus-workspace{grid-template-columns:1fr}.timer-stage{min-height:340px}.timer-orbit{width:250px;margin:18px auto}.timer-core strong{font-size:56px}.session-detail{padding:24px 16px 12px}.session-detail h2{font-size:20px}.session-facts{margin:18px 0}.focus-reminder{margin:16px 0}.focus-reminder br{display:none}.focus-actions{flex-wrap:wrap;gap:8px}.actions-hint{width:100%;margin:0 0 4px}.focus-actions button{flex:1;padding:0 8px;white-space:nowrap}.preview-note{margin:8px 0 0}.autosave-note{font-size:9px}}
@media(prefers-reduced-motion:reduce){.ring-progress,.progress-track i,.focus-actions button{transition:none}.focus-actions button:hover:not(:disabled){transform:none}}
</style>
