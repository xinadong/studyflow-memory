<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { errorMessage } from '../services/api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const error = ref('')

const title = computed(() => mode.value === 'login' ? '欢迎回到 StudyFlow' : '创建你的学习空间')
const submitLabel = computed(() => mode.value === 'login' ? '登录并开始学习' : '注册并开始学习')

function switchMode(next: 'login' | 'register') {
  mode.value = next
  error.value = ''
}

async function submit() {
  error.value = ''
  if (mode.value === 'register' && password.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致。'
    return
  }
  try {
    const credentials = { email: email.value, password: password.value }
    if (mode.value === 'login') await auth.login(credentials)
    else await auth.register(credentials)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/today'
    await router.replace(redirect)
  } catch (cause) {
    error.value = errorMessage(cause)
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card" aria-labelledby="auth-title">
      <div class="auth-mark">S</div>
      <p class="auth-eyebrow">STUDYFLOW MEMORY</p>
      <h1 id="auth-title">{{ title }}</h1>
      <p class="auth-subtitle">让计划流动，让理解发生。你的任务与学习记忆只属于你的账号。</p>
      <div class="auth-tabs" role="tablist" aria-label="账户操作">
        <button type="button" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
        <button type="button" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
      </div>
      <form class="auth-form" @submit.prevent="submit">
        <label>邮箱<input v-model.trim="email" type="email" autocomplete="email" required placeholder="you@example.com" /></label>
        <label>密码<input v-model="password" type="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" minlength="8" required placeholder="至少 8 位" /></label>
        <label v-if="mode === 'register'">确认密码<input v-model="confirmPassword" type="password" autocomplete="new-password" minlength="8" required placeholder="再次输入密码" /></label>
        <p v-if="error" class="auth-error" role="alert">{{ error }}</p>
        <button class="auth-submit" type="submit" :disabled="auth.busy">{{ auth.busy ? '正在处理…' : submitLabel }}</button>
      </form>
      <p class="auth-note">演示账号由部署配置提供；普通账号注册后立即生效。</p>
    </section>
  </main>
</template>

<style scoped>
.auth-page{min-height:100vh;display:grid;place-items:center;padding:28px;background:radial-gradient(circle at 15% 15%,#dff7fb 0,transparent 35%),radial-gradient(circle at 85% 80%,#e9e0ff 0,transparent 40%),#f5f7ff}.auth-card{width:min(430px,100%);padding:40px;border:1px solid rgba(255,255,255,.9);border-radius:30px;background:rgba(255,255,255,.84);box-shadow:0 28px 80px rgba(65,78,145,.16);backdrop-filter:blur(18px)}.auth-mark{width:48px;height:48px;display:grid;place-items:center;border-radius:16px;background:linear-gradient(135deg,#5c71f4,#8b65e9);color:white;font-size:22px;font-weight:900;box-shadow:0 12px 26px rgba(92,113,244,.25)}.auth-eyebrow{margin:24px 0 8px;color:#6b7aed;font-size:10px;font-weight:900;letter-spacing:1.8px}.auth-card h1{margin:0;color:#172052;font-size:28px;line-height:1.25}.auth-subtitle{margin:12px 0 24px;color:#7b87aa;font-size:12px;line-height:1.7}.auth-tabs{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:20px;padding:4px;border-radius:14px;background:#eef1ff}.auth-tabs button{border:0;border-radius:10px;padding:10px;background:transparent;color:#7b87aa;font-weight:800;cursor:pointer}.auth-tabs button.active{background:white;color:#566cf3;box-shadow:0 5px 14px rgba(73,88,153,.1)}.auth-form{display:grid;gap:14px}.auth-form label{display:grid;gap:7px;color:#596387;font-size:11px;font-weight:800}.auth-form input{width:100%;box-sizing:border-box;border:1px solid #e0e5f5;border-radius:13px;padding:12px 13px;color:#172052;background:#fff;font:inherit;font-weight:500;outline:none}.auth-form input:focus{border-color:#7b8aff;box-shadow:0 0 0 3px rgba(92,113,244,.12)}.auth-error{margin:0;padding:10px 12px;border-radius:12px;background:#fff0f0;color:#c65462;font-size:11px;line-height:1.5}.auth-submit{border:0;border-radius:14px;padding:13px;background:linear-gradient(135deg,#5c71f4,#7657ee);color:white;font-weight:900;cursor:pointer;box-shadow:0 12px 24px rgba(92,113,244,.2)}.auth-submit:disabled{cursor:wait;opacity:.65}.auth-note{margin:22px 0 0;color:#9aa4bf;text-align:center;font-size:10px;line-height:1.6}
</style>
