<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { usePlanStore } from '../stores/plan'
import { useAuthStore } from '../stores/auth'
import { syncAccountScopedState } from '../stores/accountState'
import { getHealth, errorMessage } from '../services/api'
import ErrorNotice from './ErrorNotice.vue'
import LoadingState from './LoadingState.vue'
import appIcon from '../assets/studyflow-app.png'
import AgentIdentity from './AgentIdentity.vue'
import MemoryReference from './MemoryReference.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const session = useSessionStore()
const plans = usePlanStore()
const tasksLoading = ref(true)
const tasksError = ref('')
let taskLoadVersion = 0
async function restoreTasks() {
  const version = ++taskLoadVersion
  tasksLoading.value = true
  tasksError.value = ''
  session.selectedTask = null
  try { await plans.loadTasks(session.userId) }
  catch (cause) { if (version === taskLoadVersion) tasksError.value = errorMessage(cause) }
  finally { if (version === taskLoadVersion) tasksLoading.value = false }
}
watch(() => auth.user?.id, userId => {
  syncAccountScopedState(userId ?? null)
  if (!userId) return
  session.userId = userId
  void restoreTasks()
}, { immediate: true })
async function logout() {
  await auth.logout()
  await router.replace('/login')
}
const backendStatus = ref<'checking' | 'online' | 'offline'>('checking')
let healthCheckTimer: number | undefined
const nav = [
  { to: '/today', icon: '⌂', label: '弹性任务流' },
  { to: '/study', icon: '◉', label: '理解检验' },
  { to: '/recovery', icon: '✦', label: '思绪星云' },
  { to: '/profile', icon: '◔', label: '个人中心' },
]
const showAside = computed(() => !['/recovery', '/profile', '/study/session'].includes(route.path))
const isStudy = computed(() => route.path === '/study')
async function checkBackend() {
  try {
    const health = await getHealth()
    backendStatus.value = health.status === 'ok' ? 'online' : 'offline'
  } catch {
    backendStatus.value = 'offline'
  }
}
onMounted(() => {
  void checkBackend()
  healthCheckTimer = window.setInterval(() => void checkBackend(), 5_000)
})
onBeforeUnmount(() => window.clearInterval(healthCheckTimer))
</script>

<template>
  <div class="ambient ambient-one" />
  <div class="ambient ambient-two" />
  <div class="shell" :class="{ 'without-aside': !showAside }">
    <aside class="sidebar">
      <RouterLink class="brand" to="/today">
        <img :src="appIcon" alt="StudyFlow" />
        <span><strong>StudyFlow</strong><small>让计划流动，让理解发生</small></span>
      </RouterLink>
      <div class="agent-online" :class="backendStatus"><i /> {{ backendStatus === 'checking' ? '正在检查后端' : backendStatus === 'online' ? 'Agent 在线' : '后端未连接' }}</div>
      <nav aria-label="主要导航">
        <RouterLink v-for="item in nav" :key="item.to" :to="item.to">
          <span class="nav-icon">{{ item.icon }}</span><span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-principle"><b>反馈记忆闭环</b><div><span>学习</span><i>→</i><span>反馈</span><i>→</i><span>记忆</span><i>→</i><span>再调整</span></div><small>每次调整都成为下一次的依据</small></div>
      <div class="user-field">
        <span>当前账号</span>
        <strong>{{ auth.user?.email }}</strong>
        <button type="button" @click="logout">退出登录</button>
      </div>
    </aside>
    <main class="main-content"><LoadingState v-if="tasksLoading" text="正在恢复保存的任务…" /><ErrorNotice v-else-if="tasksError" :message="tasksError" @retry="restoreTasks" /><RouterView v-else /></main>
    <aside v-if="showAside" class="context-aside" :class="{ 'study-aside': isStudy }">
      <template v-if="isStudy">
        <section class="study-agent-card">
          <AgentIdentity />
          <h2>让每个问题都有依据</h2>
          <p class="muted">根据你选择的任务、材料和提问方式，本轮只生成一个核心问题，避免一次抛出过多提示。</p>
          <div class="study-selection"><b>当前选择</b><strong>{{ session.selectedTask?.title || '尚未选择学习任务' }}</strong><span>提问方式以本轮选择为准</span></div>
        </section>
        <section class="study-memory-card"><p class="eyebrow">反馈记忆</p><h2>反馈记忆如何参与提问</h2><p class="muted">只采用已经确认的学习偏好，并清楚展示它如何改变本轮提问。</p><ol><li><b>检索</b><span>按适用范围查找偏好</span></li><li><b>筛选</b><span>待确认的记忆不直接使用</span></li><li><b>使用</b><span>生成问题后可查看实际引用</span></li></ol></section>
        <section class="study-privacy"><b>材料仅用于本轮提问</b><span>页面明确区分当前选择、已确认记忆与本轮生成结果，不把推测写成事实。</span></section>
      </template>
      <template v-else>
      <section class="agent-intro">
      <AgentIdentity />
      <h2>让每一步都有依据</h2>
      <p class="muted">结合已确认的学习偏好，为本轮任务提供调整建议。</p>
      <div class="aside-rule"><span>检索</span><i /><span>筛选</span><i /><span>使用</span></div>
      </section>
      <MemoryReference compact :retrieved="plans.plan?.retrieved_memory_ids" :used="plans.plan?.used_memory_ids" :candidates="plans.plan?.candidate_memory_ids" :evidence="plans.plan?.memory_evidence" />
      <div class="demo-boundary"><span class="save-icon" aria-hidden="true">✓</span><div><b>任务与复习安排已保存</b><span>临时偏好仅用于本次请求</span></div></div>
      </template>
    </aside>
  </div>
  <nav class="mobile-nav" aria-label="移动端导航">
    <RouterLink v-for="item in nav" :key="item.to" :to="item.to">
      <span>{{ item.icon }}</span><small>{{ item.label }}</small>
    </RouterLink>
  </nav>
</template>

<style scoped>
.agent-intro{padding:22px 20px 20px;border:1px solid #e0e5f7;border-radius:24px;background:linear-gradient(130deg,#e7f4fa 0%,#eeeafb 56%,#e7ecfc 100%);box-shadow:0 6px 20px rgba(73,88,153,.05)}
.context-aside .agent-intro h2{margin:24px 0 10px;font-size:19px;font-weight:700;line-height:1.45;letter-spacing:-.3px}
.context-aside .agent-intro p{margin:0 0 18px;color:#8b96b2;font-size:11px;line-height:1.85}
.agent-intro .aside-rule{gap:7px;padding-top:16px;border-top:1px solid rgba(167,180,218,.24)}
.agent-intro .aside-rule span{padding:5px 10px;border-radius:8px;background:rgba(255,255,255,.6);color:#7582a8;font-size:9px;font-weight:500}
.agent-intro .aside-rule span:last-child{background:rgba(255,255,255,.6);color:#8b7bb9}
.agent-intro .aside-rule i{display:block;align-self:center;width:12px;height:1px;background:#d8deef}

.ambient { position: fixed; pointer-events: none; border-radius: 50%; filter: blur(9px); opacity: .55; z-index: -1; }
.ambient-one { width: 340px; height: 340px; right: -80px; top: -110px; background: radial-gradient(circle, #cbd5ff, transparent 70%); }
.ambient-two { width: 280px; height: 280px; left: 22%; bottom: -120px; background: radial-gradient(circle, #c8f5fa, transparent 70%); }
.shell { width: min(1440px, 100%); min-height: 100vh; margin: 0 auto; display: grid; grid-template-columns: 232px 856px 352px; }
.shell.without-aside { grid-template-columns: 232px minmax(0, 1fr); }
.sidebar { position: sticky; top: 0; height: 100vh; padding: 32px 24px 28px; border-right: 1px solid #e7ebfa; background: rgba(255,255,255,.76); display: flex; flex-direction: column; gap:22px; }
.brand { display: flex; align-items: center; gap: 12px; text-decoration: none; margin:0; }
.brand img { width: 50px; height: 50px; object-fit: cover; border-radius: 15px; box-shadow: 0 10px 28px rgba(52,71,173,.1); }
.brand span { display: grid; gap: 3px; }
.brand strong { font-size: 20px; }
.brand small { color: var(--muted); font-size: 10px; white-space: nowrap; }
nav { display: grid; gap: 8px; }
nav a { display: flex; align-items: center; gap: 12px; text-decoration: none; padding: 12px 14px; border-radius: 14px; color: var(--muted); font-weight: 700; }
nav a:hover { background: #f0f3ff; color: var(--brand); }
nav a.router-link-active { color: var(--brand); background: white; box-shadow: 0 8px 20px rgba(52,71,173,.08); }
.nav-icon { width: 24px; height: 24px; display: grid; place-items: center; border-radius: 8px; background: #eef2ff; }
.agent-online{width:max-content;padding:7px 12px;border-radius:14px;background:#eef2ff;color:#65719a;font-size:11px}.agent-online i{display:inline-block;width:6px;height:6px;margin-right:5px;border-radius:50%;background:#8c96b5}.agent-online.online{background:#e7f8f2;color:#20a77a}.agent-online.online i{background:#20a77a}.agent-online.offline{background:#fff0f0;color:#d65d68}.agent-online.offline i{background:#d65d68}
.sidebar-principle { margin-top:0; padding:16px; border:0; border-radius:18px; background:linear-gradient(90deg,#eef2ff,#f1ecff); color: var(--muted); font-size: 9px; box-shadow:none }
.sidebar-principle b{display:block;margin-bottom:11px;color:#172052;font-size:10px}.sidebar-principle div{display:flex;align-items:center;gap:4px;font-weight:800}.sidebar-principle i { color: var(--brand); font-style: normal; }.sidebar-principle small{display:block;margin-top:9px;color:#9ba4bf;font-size:8px}
.user-field { margin-top: auto; display: grid; gap: 7px; padding:14px; border-radius:16px; background:#fff; color: var(--muted); font-size: 10px; font-weight: 700; }
.user-field strong { min-width: 0; overflow: hidden; color: var(--text); text-overflow: ellipsis; white-space: nowrap; }
.user-field button { border: 1px solid var(--border); border-radius: 10px; padding: 8px; color: var(--muted); background: white; font: inherit; cursor: pointer; }
.main-content { min-width: 0; padding: 40px 0 70px 36px; }
.context-aside { position: sticky; top: 0; height: 100vh; margin-left:36px; padding: 40px 28px; display:flex; flex-direction:column; gap:18px; background:linear-gradient(180deg,#f3f5fd 0%,#f6f8ff 70%); border-left:1px solid #e9edf8; }
.context-aside h2 { margin:0; font-size: 22px; line-height:1.25; }
.context-aside p { line-height: 1.7; }
.aside-rule { display:flex;gap:8px;margin:0;font-size:10px }.aside-rule span{padding:7px 10px;border-radius:13px;background:#eef2ff;color:#596387}.aside-rule span:last-child{background:#eee9ff;color:#7657f6}.aside-rule i{display:none}
.memory-proof{margin-top:0;padding:18px;border:1px solid #e5e9f7;border-radius:22px;background:#fff;box-shadow:0 6px 20px rgba(73,88,153,.04)}.proof-title{margin-bottom:12px;font-size:14px}.used-memory,.memory-impact{display:grid;gap:6px;padding:12px;margin-bottom:10px;border-radius:15px;font-size:11px}.used-memory{background:#f7f5ff}.used-memory b{color:#7657f6;font-size:10px}.memory-impact{background:#ecf8ff}.memory-impact b{color:#28a9c2;font-size:10px}.memory-counts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.memory-counts div{display:grid;gap:3px;padding:10px 8px;border-radius:14px;background:#f6f8ff}.memory-counts b{font-size:18px;color:#4f63f6}.memory-counts div:nth-child(2) b{color:#20a77a}.memory-counts div:nth-child(3) b{color:#ff8a34}.memory-counts span{color:#7b88aa;font-size:9px}.demo-boundary{display:flex;align-items:flex-start;gap:10px;padding:4px 12px;font-size:10px}.demo-boundary .save-icon{display:grid;place-items:center;flex:0 0 20px;height:20px;border-radius:50%;background:#e6f3ee;color:#4a9a80;font-size:11px}.demo-boundary>div{display:grid;gap:4px;min-width:0}.demo-boundary b{color:#6b7a99;font-size:10px;line-height:1.7;font-weight:600}.demo-boundary div>span{color:#929db5;font-size:9px;line-height:1.7}
.mobile-nav { display: none; }
.context-aside.study-aside{gap:18px;padding:40px 28px}.study-agent-card,.study-memory-card,.study-privacy{border:1px solid rgba(255,255,255,.9);border-radius:24px;background:rgba(255,255,255,.62)}.study-agent-card{padding:24px;background:linear-gradient(110deg,rgba(235,252,255,.84),rgba(240,232,255,.78))}.study-agent-card h2{margin-top:22px}.study-agent-card h2,.study-memory-card h2{margin:6px 0 10px;font-size:20px}.study-agent-card>p.muted,.study-memory-card>p.muted{margin:0;font-size:12px;line-height:1.55}.study-selection{margin-top:20px;padding:15px;display:grid;gap:7px;border-radius:18px;background:rgba(255,255,255,.58)}.study-selection b{color:var(--brand);font-size:10px}.study-selection strong{font-size:12px}.study-selection span{color:var(--muted);font-size:10px}.study-memory-card{padding:22px}.study-memory-card ol{margin:17px 0 0;padding:0;display:grid;gap:14px;list-style:none;counter-reset:trace}.study-memory-card li{counter-increment:trace;display:grid;grid-template-columns:22px 38px 1fr;align-items:center;gap:7px;font-size:10px}.study-memory-card li:before{content:counter(trace);width:22px;height:22px;display:grid;place-items:center;border-radius:50%;background:#e3e8ff;color:var(--brand);font-weight:800}.study-memory-card li:last-child:before{background:#4fd9e9;color:white}.study-memory-card li span{color:var(--muted)}.study-privacy{padding:18px 20px;display:grid;gap:8px}.study-privacy b{font-size:13px}.study-privacy span{color:var(--muted);font-size:10px;line-height:1.5}
@media (max-width: 1100px) { .shell, .shell.without-aside { grid-template-columns: 210px minmax(0, 1fr); } .context-aside { display: none; } }
@media (max-width: 760px) {
  .shell, .shell.without-aside { display: block; }
  .sidebar { display: none; }
  .main-content { padding: 20px 14px 94px; }
  .mobile-nav { position: fixed; z-index: 20; display: grid; grid-template-columns: repeat(4,1fr); bottom: 10px; left: 12px; right: 12px; padding: 6px; border-radius: 20px; background: rgba(255,255,255,.94); backdrop-filter: blur(16px); box-shadow: 0 10px 30px rgba(52,71,173,.18); }
  .mobile-nav a { justify-content: center; display: grid; gap: 1px; padding: 5px; font-size: 15px; text-align: center; }
  .mobile-nav small { font-size: 9px; }
}
</style>
