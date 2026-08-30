<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { usePlanStore } from '../stores/plan'
import appIcon from '../assets/studyflow-app.png'

const route = useRoute()
const session = useSessionStore()
const plans = usePlanStore()
const nav = [
  { to: '/today', icon: '⌂', label: '弹性任务流' },
  { to: '/study', icon: '◉', label: '理解检验' },
  { to: '/recovery', icon: '✦', label: '思绪星云' },
]
const showAside = computed(() => route.path !== '/recovery')
const isStudy = computed(() => route.path === '/study')
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
      <div class="agent-online"><i /> Agent 在线</div>
      <nav aria-label="主要导航">
        <RouterLink v-for="item in nav" :key="item.to" :to="item.to">
          <span class="nav-icon">{{ item.icon }}</span><span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-principle"><b>反馈记忆闭环</b><div><span>学习</span><i>→</i><span>反馈</span><i>→</i><span>记忆</span><i>→</i><span>再调整</span></div><small>每次调整都成为下一次的依据</small></div>
      <label class="user-field">
        <span>演示用户</span>
        <input v-model.trim="session.userId" aria-label="演示用户 ID" />
      </label>
    </aside>
    <main class="main-content"><RouterView /></main>
    <aside v-if="showAside" class="context-aside" :class="{ 'study-aside': isStudy }">
      <template v-if="isStudy">
        <section class="study-agent-card">
          <div class="assistant-orb"><span>✦</span></div>
          <p class="eyebrow">FLOW AGENT</p><h2>让每个问题都有依据</h2>
          <p class="muted">根据你选择的任务、材料和提问方式，本轮只生成一个核心问题，避免一次抛出过多提示。</p>
          <div class="study-selection"><b>当前选择</b><strong>{{ session.selectedTask?.title || '高等数学 · 导数应用' }}</strong><span>复述概念 · 可追加关联知识</span></div>
        </section>
        <section class="study-memory-card"><p class="eyebrow">反馈记忆</p><h2>本轮如何使用已有经验</h2><p class="muted">只采用已经确认的学习偏好，并清楚展示它如何改变本轮提问。</p><ol><li><b>检索</b><span>找到：先复述，再追问关联</span></li><li><b>筛选</b><span>与本次学习任务相关</span></li><li><b>使用</b><span>首问采用“复述概念”</span></li></ol></section>
        <section class="study-privacy"><b>材料仅用于本轮提问</b><span>页面明确区分当前选择、已确认记忆与本轮生成结果，不把推测写成事实。</span></section>
      </template>
      <template v-else>
      <div class="assistant-orb"><span>✦</span></div>
      <p class="eyebrow">FLOW AGENT</p>
      <h2>让每一步都有依据</h2>
      <p class="muted">反馈记忆不是第四个功能，而是贯穿任务生成、理解检验与恢复调整的内部机制。</p>
      <div class="aside-rule"><span>检索</span><i /><span>筛选</span><i /><span>使用</span></div>
      <div class="memory-proof">
        <div class="proof-title"><b>本轮实际使用 {{ plans.plan?.used_memory_ids.length || 0 }} 条记忆</b></div>
        <div class="used-memory"><b>任务偏好 · 已确认</b><span>{{ plans.plan?.used_memory_ids[0] || '生成计划后显示真实记忆 ID' }}</span></div>
        <div class="memory-impact"><b>因此发生的改变</b><span>{{ plans.plan?.explanation || '生成计划后显示真实 Agent 调整说明。' }}</span></div>
        <div class="memory-counts"><div><b>{{ plans.plan?.retrieved_memory_ids.length || 0 }}</b><span>检索到</span></div><div><b>{{ plans.plan?.used_memory_ids.length || 0 }}</b><span>实际使用</span></div><div><b>{{ plans.plan?.candidate_memory_ids.length || 0 }}</b><span>待确认</span></div></div>
      </div>
      <div class="demo-boundary"><b>演示边界</b><span>任务状态和计划调整仅保存在本次浏览器会话。</span></div>
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
.agent-online{width:max-content;padding:7px 12px;border-radius:14px;background:#e7f8f2;color:#20a77a;font-size:11px}.agent-online i{display:inline-block;width:6px;height:6px;margin-right:5px;border-radius:50%;background:#20a77a}
.sidebar-principle { margin-top:0; padding:16px; border:0; border-radius:18px; background:linear-gradient(90deg,#eef2ff,#f1ecff); color: var(--muted); font-size: 9px; box-shadow:none }
.sidebar-principle b{display:block;margin-bottom:11px;color:#172052;font-size:10px}.sidebar-principle div{display:flex;align-items:center;gap:4px;font-weight:800}.sidebar-principle i { color: var(--brand); font-style: normal; }.sidebar-principle small{display:block;margin-top:9px;color:#9ba4bf;font-size:8px}
.user-field { margin-top: auto; display: grid; gap: 7px; padding:14px; border-radius:16px; background:#fff; color: var(--muted); font-size: 10px; font-weight: 700; }
.user-field input { min-width: 0; border: 1px solid var(--border); border-radius: 12px; padding: 9px; color: var(--text); background: white; }
.main-content { min-width: 0; padding: 40px 0 70px 36px; }
.context-aside { position: sticky; top: 0; height: 100vh; margin-left:36px; padding: 40px 28px; display:flex; flex-direction:column; gap:18px; background:rgba(255,255,255,.28); border-left:0; }
.context-aside h2 { margin:0; font-size: 22px; line-height:1.25; }
.context-aside p { line-height: 1.7; }
.assistant-orb { width: 74px; height: 81px; display: grid; place-items: center; margin-bottom: 0; border-radius: 32px; background: radial-gradient(circle,#28c7df,#4f8feb 55%,#7657f6); box-shadow: 0 10px 24px rgba(79,99,245,.28); }
.assistant-orb span { color: white; font-size: 27px; }
.aside-rule { display:flex;gap:8px;margin:0;font-size:10px }.aside-rule span{padding:7px 10px;border-radius:13px;background:#eef2ff;color:#596387}.aside-rule span:last-child{background:#eee9ff;color:#7657f6}.aside-rule i{display:none}
.memory-proof{margin-top:0;padding:18px;border:1px solid #d9d5ff;border-radius:22px;background:rgba(255,255,255,.78);box-shadow:0 8px 16px rgba(52,71,173,.1)}.proof-title{margin-bottom:12px;font-size:14px}.used-memory,.memory-impact{display:grid;gap:6px;padding:12px;margin-bottom:10px;border-radius:15px;font-size:11px}.used-memory{background:#f7f5ff}.used-memory b{color:#7657f6;font-size:10px}.memory-impact{background:#ecf8ff}.memory-impact b{color:#28a9c2;font-size:10px}.memory-counts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.memory-counts div{display:grid;gap:3px;padding:10px 8px;border-radius:14px;background:#f6f8ff}.memory-counts b{font-size:18px;color:#4f63f6}.memory-counts div:nth-child(2) b{color:#20a77a}.memory-counts div:nth-child(3) b{color:#ff8a34}.memory-counts span{color:#7b88aa;font-size:9px}.demo-boundary{display:grid;gap:5px;padding:14px;border-radius:18px;background:#fff8ef;font-size:10px}.demo-boundary b{color:#ff8a34;font-size:11px}.demo-boundary span{color:#596387;line-height:1.5}
.mobile-nav { display: none; }
.context-aside.study-aside{gap:18px;padding:40px 28px;background:transparent}.study-agent-card,.study-memory-card,.study-privacy{border:1px solid rgba(255,255,255,.9);border-radius:24px;background:rgba(255,255,255,.62)}.study-agent-card{padding:24px;background:linear-gradient(110deg,rgba(235,252,255,.84),rgba(240,232,255,.78))}.study-agent-card .assistant-orb{width:76px;height:76px;margin-bottom:20px}.study-agent-card h2,.study-memory-card h2{margin:6px 0 10px;font-size:20px}.study-agent-card>p.muted,.study-memory-card>p.muted{margin:0;font-size:12px;line-height:1.55}.study-selection{margin-top:20px;padding:15px;display:grid;gap:7px;border-radius:18px;background:rgba(255,255,255,.58)}.study-selection b{color:var(--brand);font-size:10px}.study-selection strong{font-size:12px}.study-selection span{color:var(--muted);font-size:10px}.study-memory-card{padding:22px}.study-memory-card ol{margin:17px 0 0;padding:0;display:grid;gap:14px;list-style:none;counter-reset:trace}.study-memory-card li{counter-increment:trace;display:grid;grid-template-columns:22px 38px 1fr;align-items:center;gap:7px;font-size:10px}.study-memory-card li:before{content:counter(trace);width:22px;height:22px;display:grid;place-items:center;border-radius:50%;background:#e3e8ff;color:var(--brand);font-weight:800}.study-memory-card li:last-child:before{background:#4fd9e9;color:white}.study-memory-card li span{color:var(--muted)}.study-privacy{padding:18px 20px;display:grid;gap:8px}.study-privacy b{font-size:13px}.study-privacy span{color:var(--muted);font-size:10px;line-height:1.5}
@media (max-width: 1100px) { .shell, .shell.without-aside { grid-template-columns: 210px minmax(0, 1fr); } .context-aside { display: none; } }
@media (max-width: 760px) {
  .shell, .shell.without-aside { display: block; }
  .sidebar { display: none; }
  .main-content { padding: 20px 14px 94px; }
  .mobile-nav { position: fixed; z-index: 20; display: grid; grid-template-columns: repeat(3,1fr); bottom: 10px; left: 12px; right: 12px; padding: 6px; border-radius: 20px; background: rgba(255,255,255,.94); backdrop-filter: blur(16px); box-shadow: 0 10px 30px rgba(52,71,173,.18); }
  .mobile-nav a { justify-content: center; display: grid; gap: 1px; padding: 5px; font-size: 15px; text-align: center; }
  .mobile-nav small { font-size: 9px; }
}
</style>
