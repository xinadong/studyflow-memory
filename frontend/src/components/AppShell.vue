<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useSessionStore } from '../stores/session'
import appIcon from '../assets/studyflow-app.png'

const route = useRoute()
const session = useSessionStore()
const nav = [
  { to: '/today', icon: '⌂', label: '弹性任务流' },
  { to: '/study', icon: '◉', label: '理解检验' },
  { to: '/recovery', icon: '✦', label: '思绪星云' },
]
const showAside = computed(() => route.path !== '/recovery')
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
      <nav aria-label="主要导航">
        <RouterLink v-for="item in nav" :key="item.to" :to="item.to">
          <span class="nav-icon">{{ item.icon }}</span><span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-principle"><span>学习</span><i>→</i><span>反馈</span><i>→</i><span>记忆</span><i>→</i><span>再调整</span></div>
      <label class="user-field">
        <span>演示用户</span>
        <input v-model.trim="session.userId" aria-label="演示用户 ID" />
      </label>
    </aside>
    <main class="main-content"><RouterView /></main>
    <aside v-if="showAside" class="context-aside">
      <div class="assistant-orb"><span>✦</span></div>
      <p class="eyebrow">FLOW AGENT</p>
      <h2>让每一步都有依据</h2>
      <p class="muted">反馈记忆贯穿三个功能，但不是额外功能。这里仅解释本轮哪些已确认经验真正改变了计划或提问。</p>
      <div class="aside-rule"><span>检索</span><i /><span>筛选</span><i /><span>使用</span></div>
      <div class="notice">当前用户：<strong>{{ session.userId }}</strong></div>
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
.shell { width: min(1440px, 100%); min-height: 100vh; margin: 0 auto; display: grid; grid-template-columns: 232px minmax(0, 1fr) 310px; }
.shell.without-aside { grid-template-columns: 232px minmax(0, 1fr); }
.sidebar { position: sticky; top: 0; height: 100vh; padding: 28px 18px 22px; border-right: 1px solid rgba(218,224,242,.9); background: rgba(250,251,255,.8); backdrop-filter: blur(18px); display: flex; flex-direction: column; }
.brand { display: flex; align-items: center; gap: 11px; text-decoration: none; margin: 0 7px 34px; }
.brand img { width: 46px; height: 46px; object-fit: cover; border-radius: 14px; box-shadow: 0 8px 18px rgba(79,99,246,.2); }
.brand span { display: grid; gap: 3px; }
.brand strong { font-size: 17px; }
.brand small { color: var(--muted); font-size: 9px; white-space: nowrap; }
nav { display: grid; gap: 7px; }
nav a { display: flex; align-items: center; gap: 12px; text-decoration: none; padding: 12px 14px; border-radius: 14px; color: var(--muted); font-weight: 700; }
nav a:hover { background: #f0f3ff; color: var(--brand); }
nav a.router-link-active { color: var(--brand); background: white; box-shadow: 0 8px 20px rgba(52,71,173,.08); }
.nav-icon { width: 24px; height: 24px; display: grid; place-items: center; border-radius: 8px; background: #eef2ff; }
.sidebar-principle { margin-top: 30px; padding: 16px 10px; border-top: 1px solid var(--border); display: flex; flex-wrap: wrap; gap: 5px; color: var(--muted); font-size: 10px; font-weight: 800; }
.sidebar-principle i { color: var(--brand); font-style: normal; }
.user-field { margin-top: auto; display: grid; gap: 7px; color: var(--muted); font-size: 11px; font-weight: 700; }
.user-field input { min-width: 0; border: 1px solid var(--border); border-radius: 12px; padding: 9px; color: var(--text); background: white; }
.main-content { min-width: 0; padding: 34px 32px 70px; }
.context-aside { position: sticky; top: 24px; height: max-content; margin: 24px 24px 0 0; padding: 28px 24px; border-radius: 28px; background: linear-gradient(145deg, rgba(255,255,255,.94), rgba(238,239,255,.94)); box-shadow: var(--shadow); border: 1px solid white; }
.context-aside h2 { margin-bottom: 12px; font-size: 22px; }
.context-aside p { line-height: 1.7; }
.assistant-orb { width: 80px; height: 80px; display: grid; place-items: center; margin-bottom: 22px; border-radius: 50%; background: radial-gradient(circle at 35% 25%, white, #54dde9 26%, #7271ed 68%, #4330a8); box-shadow: 0 0 38px rgba(84,221,233,.5); }
.assistant-orb span { color: white; font-size: 27px; }
.aside-rule { display: flex; align-items: center; gap: 7px; color: var(--brand); font-size: 11px; font-weight: 800; margin: 24px 0; }
.aside-rule i { flex: 1; height: 1px; background: #cfd6ff; }
.mobile-nav { display: none; }
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
