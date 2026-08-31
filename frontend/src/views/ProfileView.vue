<script setup lang="ts">
import { computed, ref } from 'vue'
import MemoryCenterView from './MemoryCenterView.vue'
import { useMemoryStore } from '../stores/memory'
import { usePlanStore } from '../stores/plan'
import { useSessionStore } from '../stores/session'
import flowAgentOrb from '../assets/flow-agent-orb.svg'

const session = useSessionStore()
const memories = useMemoryStore()
const plans = usePlanStore()
const activeRange = ref<'week' | 'month'>('week')
const toast = ref('')
const profileOpen = ref(false)
const planRecordsOpen = ref(false)
const goals = ref([
  { label: '迁移完成', value: 62, color: '#7657f6' },
  { label: '理解完成', value: 81, color: '#28c7df' },
  { label: '普通完成', value: 94, color: '#4f63f6' },
])
const activityData = {
  week: [
    { label: '一', hours: 1.4 }, { label: '二', hours: 2.2 },
    { label: '三', hours: 1.6 }, { label: '四', hours: 2.8 },
    { label: '五', hours: 1.9 }, { label: '六', hours: 2.6 },
    { label: '日', hours: 1.7 },
  ],
  month: [
    { label: '第1周', hours: 12.6 }, { label: '第2周', hours: 14.2 },
    { label: '第3周', hours: 16.8 }, { label: '第4周', hours: 13.4 },
    { label: '第5周', hours: 6.1 },
  ],
} as const
const chartData = computed(() => {
  const data = activityData[activeRange.value]
  const max = Math.max(...data.map(item => item.hours))
  return data.map(item => ({ ...item, height: Math.max(18, Math.round(item.hours / max * 88)) }))
})
const activitySubtitle = computed(() => activeRange.value === 'week'
  ? '本周每日有效学习时长'
  : '本月各周有效学习时长')
const planTasks = computed(() => plans.plan?.tasks ?? [])
const completedPlanCount = computed(() => planTasks.value.filter(task => plans.statuses[task.id] === 'completed').length)

function planStatus(taskId: string) {
  const status = plans.statuses[taskId] || 'pending'
  return status === 'completed' ? '已完成' : status === 'active' ? '进行中' : status === 'deferred' ? '已顺延' : '待开始'
}

function formatDueAt(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function notify(message: string) {
  toast.value = message
  window.setTimeout(() => { toast.value = '' }, 2200)
}

function openMemories() {
  document.getElementById('memories')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <div class="profile-page">
    <header class="profile-heading">
      <div><p class="eyebrow">PERSONAL CENTER</p><h1>个人中心</h1><p>回看你的学习节奏，让每次反馈成为下一次调整的依据。</p></div>
      <button class="icon-button" type="button" aria-label="打开设置" @click="notify('设置功能将在后续版本开放')">⚙</button>
    </header>

    <section class="hero-card">
      <div class="profile-avatar"><span>{{ session.userId.slice(0, 1).toUpperCase() }}</span><i /></div>
      <div class="identity">
        <span class="status-chip">连续学习 12 天</span>
        <h2>{{ session.userId }}</h2>
        <p>今天也在稳步前进 · 本周已学习 14.2 小时</p>
      </div>
      <button class="edit-button" type="button" @click="profileOpen = !profileOpen">{{ profileOpen ? '收起资料' : '编辑资料' }}</button>
      <div v-if="profileOpen" class="edit-panel">
        <label>昵称<input placeholder="例如：小杨同学" /></label>
        <label>本周目标<input placeholder="例如：18 小时" /></label>
        <button type="button" @click="profileOpen = false; notify('个人资料已保存')">保存更改</button>
      </div>
    </section>

    <section class="metrics-grid" aria-label="学习数据概览">
      <article><span class="metric-icon violet">◷</span><div><b>14.2h</b><small>本周学习</small></div><em>+12%</em></article>
      <article><span class="metric-icon cyan">◎</span><div><b>86%</b><small>平均专注率</small></div><em>稳定</em></article>
      <article><span class="metric-icon pink">✓</span><div><b>11 / 15</b><small>已完成任务</small></div><em>4 项待办</em></article>
    </section>

    <div class="content-grid">
      <section class="surface activity-card">
        <div class="card-heading"><div><h2>学习活跃度</h2><p>{{ activitySubtitle }}</p></div><div class="segmented"><button :class="{ active: activeRange === 'week' }" :aria-pressed="activeRange === 'week'" @click="activeRange = 'week'">本周</button><button :class="{ active: activeRange === 'month' }" :aria-pressed="activeRange === 'month'" @click="activeRange = 'month'">本月</button></div></div>
        <div class="chart">
          <div v-for="item in chartData" :key="item.label" class="bar-column"><span>{{ item.hours }}h</span><i :style="{ height: `${item.height}%` }" /><small>{{ item.label }}</small></div>
        </div>
      </section>

      <section class="surface mastery-card">
        <div class="card-heading"><div><h2>掌握分布</h2><p>状态来自复述与迁移证据</p></div><button class="text-button" @click="openMemories">查看知识记忆 →</button></div>
        <div class="goal-list"><div v-for="goal in goals" :key="goal.label"><div><span>{{ goal.label }}</span><b :style="{ color: goal.color }">{{ goal.value }}%</b></div><i><em :style="{ width: `${goal.value}%`, background: goal.color }" /></i></div></div>
        <p class="evidence-note">完成 ≠ 掌握；确认后的理解证据才会进入反馈记忆。</p>
      </section>

      <section class="surface memory-card">
        <div class="memory-orb" aria-hidden="true"><img :src="flowAgentOrb" alt="" /><span>✦</span></div><div><p class="eyebrow">FLOW AGENT · 反馈记忆</p><h2>已读取 {{ memories.items.length }} 条有效记忆</h2><p>{{ memories.pendingCount ? `其中 ${memories.pendingCount} 条待你确认，尚不会影响 Agent。` : '当前没有待确认记忆。' }}</p><button class="text-button" @click="openMemories">查看与管理记忆 →</button></div>
      </section>

      <section class="surface plan-card">
        <div class="health-ring"><div><b>79%</b><span>稳定</span></div></div>
        <div><p class="eyebrow">计划健康</p><h2>节奏保持得不错</h2><p>本周完成 2 次自动修复，保留了必须提交的核心任务。</p></div>
        <button class="primary-button" @click="planRecordsOpen = true">查看计划记录</button>
      </section>
    </div>

    <section id="memories" class="profile-memories surface">
      <MemoryCenterView embedded />
    </section>

    <div v-if="planRecordsOpen" class="records-backdrop" @click.self="planRecordsOpen = false">
      <section class="records-dialog" role="dialog" aria-modal="true" aria-labelledby="records-title">
        <div class="records-heading"><div><p class="eyebrow">CURRENT SESSION · PLAN LOG</p><h2 id="records-title">本周计划记录</h2><span>记录来自当前浏览器会话中的弹性任务流。</span></div><button type="button" aria-label="关闭计划记录" @click="planRecordsOpen = false">×</button></div>
        <template v-if="planTasks.length">
          <div class="records-summary"><div><b>{{ planTasks.length }}</b><span>计划任务</span></div><div><b>{{ completedPlanCount }}</b><span>已完成</span></div><div><b>{{ plans.totalMinutes }}</b><span>计划分钟</span></div></div>
          <div class="records-list">
            <article v-for="task in planTasks" :key="task.id">
              <i :class="plans.statuses[task.id] || 'pending'" />
              <div><strong>{{ task.title }}</strong><span>{{ task.course || session.course }} · {{ task.duration_minutes }} 分钟<span v-if="task.due_at"> · 截止 {{ formatDueAt(task.due_at) }}</span></span></div>
              <em :class="plans.statuses[task.id] || 'pending'">{{ planStatus(task.id) }}</em>
            </article>
          </div>
          <p v-if="plans.plan?.explanation" class="records-reason"><b>本轮安排依据</b>{{ plans.plan.explanation }}</p>
        </template>
        <div v-else class="records-empty"><span>◇</span><h3>还没有可查看的计划记录</h3><p>先在弹性任务流中生成或导入任务，记录会保存在当前浏览器会话中。</p></div>
        <div class="records-actions"><button type="button" @click="planRecordsOpen = false">关闭</button><RouterLink to="/today" @click="planRecordsOpen = false">前往弹性任务流 →</RouterLink></div>
      </section>
    </div>

    <Transition name="toast"><div v-if="toast" class="toast" role="status">{{ toast }}</div></Transition>
  </div>
</template>

<style scoped>
.profile-memories{margin-top:22px;scroll-margin-top:24px}
.profile-page{max-width:1120px;margin:0 auto;padding:0 34px 64px}.profile-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}.profile-heading h1{margin:5px 0 8px;font-size:34px;letter-spacing:-.04em}.profile-heading p{margin:0;color:var(--muted);font-size:13px}.icon-button,.edit-button,.segmented button,.text-button,.primary-button{border:0}.icon-button{width:44px;height:44px;border-radius:15px;background:#fff;color:var(--brand);font-size:20px;box-shadow:var(--shadow)}
.hero-card{position:relative;display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:22px;min-height:190px;padding:30px 34px;border:1px solid rgba(255,255,255,.86);border-radius:30px;background:linear-gradient(115deg,rgba(226,251,255,.88),rgba(225,232,255,.9) 53%,rgba(241,226,255,.86));box-shadow:0 14px 34px rgba(52,71,173,.12);overflow:hidden}.hero-card:after{content:"";position:absolute;width:220px;height:220px;right:13%;bottom:-145px;border-radius:50%;background:radial-gradient(circle,#fff 0,rgba(255,255,255,.08) 68%)}.profile-avatar{position:relative;width:104px;height:104px;display:grid;place-items:center;border:5px solid rgba(255,255,255,.75);border-radius:34px;background:linear-gradient(145deg,#55d9e8,#527cf4 55%,#8865f5);box-shadow:0 14px 28px rgba(79,99,246,.23);color:white;font-size:34px;font-weight:800}.profile-avatar i{position:absolute;right:-4px;bottom:-4px;width:25px;height:25px;border:5px solid #e8ecff;border-radius:50%;background:#2fca93}.identity{z-index:1}.identity h2{margin:12px 0 6px;font-size:27px}.identity p{margin:0;color:var(--muted);font-size:13px}.status-chip{display:inline-flex;padding:6px 11px;border-radius:999px;background:#5367f7;color:#fff;font-size:11px;font-weight:800}.edit-button{z-index:1;padding:11px 17px;border-radius:14px;background:rgba(255,255,255,.83);color:var(--brand);font-weight:800}.edit-panel{grid-column:2/4;z-index:2;display:flex;gap:10px;padding-top:8px}.edit-panel label{display:grid;gap:5px;color:var(--muted);font-size:10px}.edit-panel input{width:180px;padding:9px 11px;border:1px solid #dfe5f7;border-radius:11px;color:var(--text)}.edit-panel button{align-self:end;padding:10px 15px;border:0;border-radius:11px;background:var(--brand);color:#fff;font-weight:800}
.metrics-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin:18px 0}.metrics-grid article{display:flex;align-items:center;gap:14px;padding:18px 20px;border-radius:21px;background:#fff;box-shadow:0 9px 24px rgba(52,71,173,.07)}.metric-icon{width:42px;height:42px;display:grid;place-items:center;border-radius:14px;font-weight:900}.metric-icon.violet{background:#eeebff;color:#7657f6}.metric-icon.cyan{background:#e4f9fc;color:#1598ad}.metric-icon.pink{background:#fff0f4;color:#ee6983}.metrics-grid article div{display:grid;gap:2px}.metrics-grid b{font-size:20px}.metrics-grid small{color:var(--muted)}.metrics-grid em{margin-left:auto;padding:5px 8px;border-radius:999px;background:#eaf9f3;color:#20a77a;font-size:10px;font-style:normal;font-weight:800}
.content-grid{display:grid;grid-template-columns:1.25fr .95fr;gap:18px}.surface{padding:24px;border:1px solid rgba(225,230,244,.9);border-radius:25px;background:rgba(255,255,255,.9);box-shadow:var(--shadow)}.card-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.card-heading h2,.memory-card h2,.plan-card h2{margin:0 0 5px;font-size:19px}.card-heading p,.memory-card p,.plan-card p{margin:0;color:var(--muted);font-size:11px}.segmented{display:flex;padding:3px;border-radius:12px;background:#eef1ff}.segmented button{padding:6px 10px;border-radius:9px;background:transparent;color:var(--muted);font-size:10px;font-weight:800}.segmented button.active{background:#fff;color:var(--brand);box-shadow:0 3px 8px rgba(52,71,173,.1)}.chart{height:210px;display:flex;align-items:flex-end;gap:18px;padding:31px 10px 0;border-bottom:1px solid #e4e8f5;background:repeating-linear-gradient(to bottom,transparent 0,transparent 48px,#edf0f8 49px)}.bar-column{height:100%;flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:7px}.bar-column span{font-size:9px;color:var(--brand);font-weight:800}.bar-column i{width:min(32px,72%);min-height:24px;border-radius:11px 11px 5px 5px;background:linear-gradient(#8d7af9,#5367f7)}.bar-column:nth-child(2n) i{background:linear-gradient(#6fdaea,#23bed7)}.bar-column small{padding-bottom:7px;color:var(--muted)}
.text-button{padding:0;background:transparent;color:var(--brand);font-size:11px;font-weight:800}.goal-list{display:grid;gap:19px;margin-top:28px}.goal-list>div>div{display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px}.goal-list i{display:block;height:9px;border-radius:99px;background:#eef1ff;overflow:hidden}.goal-list i em{display:block;height:100%;border-radius:99px}.evidence-note{margin:22px 0 0;padding:11px 13px;border-radius:13px;background:#f5f7ff;color:var(--muted);font-size:10px}.memory-card,.plan-card{display:flex;align-items:center;gap:18px}.memory-orb{position:relative;flex:0 0 76px;width:76px;height:76px;overflow:hidden;border-radius:50%}.memory-orb img{position:absolute;inset:0;display:block;width:100%;height:100%}.memory-orb span{position:absolute;inset:8px 23px 21px 16px;display:grid;place-items:center;color:#fff;font-size:48px;font-weight:700;line-height:1}.memory-card>div:nth-child(2){display:grid;gap:4px}.memory-card .text-button{width:max-content;margin-top:5px}.health-ring{flex:0 0 82px;height:82px;display:grid;place-items:center;border-radius:50%;background:conic-gradient(#5367f7 0 79%,#e7ebff 79%)}.health-ring>div{width:63px;height:63px;display:grid;place-content:center;text-align:center;border-radius:50%;background:#fff}.health-ring b{font-size:17px;color:var(--brand)}.health-ring span{font-size:9px;color:var(--green)}.plan-card>div:nth-child(2){flex:1}.primary-button{padding:10px 14px;border-radius:13px;background:#4f63f6;color:white;font-size:11px;font-weight:800;white-space:nowrap}.toast{position:fixed;z-index:50;right:28px;bottom:28px;padding:13px 18px;border-radius:15px;background:#172052;color:#fff;box-shadow:0 12px 30px rgba(23,32,82,.28);font-size:12px}.toast-enter-active,.toast-leave-active{transition:.2s}.toast-enter-from,.toast-leave-to{opacity:0;transform:translateY(8px)}
.records-backdrop{position:fixed;z-index:1000;inset:0;display:grid;place-items:center;padding:22px;background:rgba(23,32,82,.32);backdrop-filter:blur(10px)}
.records-dialog{width:min(720px,100%);max-height:min(760px,90vh);overflow-y:auto;padding:28px;border:1px solid rgba(255,255,255,.92);border-radius:28px;background:rgba(255,255,255,.98);box-shadow:0 30px 90px rgba(35,47,110,.3)}
.records-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.records-heading h2{margin:5px 0 5px;font-size:25px}.records-heading span{color:var(--muted);font-size:11px}.records-heading>button{width:38px;height:38px;border:0;border-radius:50%;background:#eef1fa;color:#7782a0;font-size:23px;cursor:pointer}
.records-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:22px 0}.records-summary div{display:grid;gap:4px;padding:15px;border-radius:17px;background:linear-gradient(110deg,#eefaff,#f2efff)}.records-summary b{color:var(--brand);font-size:22px}.records-summary span{color:var(--muted);font-size:10px}
.records-list{display:grid;gap:10px}.records-list article{display:grid;grid-template-columns:12px minmax(0,1fr) auto;align-items:center;gap:12px;padding:14px 15px;border:1px solid #e5e9f6;border-radius:17px;background:#fafbff}.records-list article>i{width:9px;height:9px;border-radius:50%;background:#9da7c2}.records-list article>i.completed{background:#20a77a}.records-list article>i.active{background:#5367f7}.records-list article>i.deferred{background:#ff8a34}.records-list article>div{display:grid;gap:4px;min-width:0}.records-list strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}.records-list article span{color:var(--muted);font-size:10px}.records-list em{padding:6px 9px;border-radius:999px;background:#eef1f8;color:#7782a0;font-size:9px;font-style:normal;font-weight:800}.records-list em.completed{background:#e7f8f2;color:#20a77a}.records-list em.active{background:#e9edff;color:#5367f7}.records-list em.deferred{background:#fff0e4;color:#e77b30}
.records-reason{display:grid;gap:6px;margin:16px 0 0;padding:14px 16px;border-radius:16px;background:#f1f8ff;color:var(--muted);font-size:11px;line-height:1.6}.records-reason b{color:#28a9c2}.records-empty{display:grid;place-items:center;padding:46px 20px;text-align:center}.records-empty>span{font-size:34px;color:#8793ef}.records-empty h3{margin:12px 0 6px}.records-empty p{max-width:390px;margin:0;color:var(--muted);font-size:11px;line-height:1.7}.records-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:22px}.records-actions button,.records-actions a{height:40px;padding:0 17px;display:inline-flex;align-items:center;border:0;border-radius:13px;background:#eef1f8;color:#697596;text-decoration:none;font-size:11px;font-weight:800}.records-actions a{background:#5367f7;color:#fff}
@media(max-width:1050px){.profile-page{padding:0 26px 60px}.content-grid{grid-template-columns:1fr}.memory-card,.plan-card{min-height:142px}}
@media(max-width:760px){.profile-page{padding:0 0 24px}.profile-heading h1{font-size:28px}.profile-heading p{max-width:250px}.hero-card{grid-template-columns:auto 1fr;padding:24px 20px}.profile-avatar{width:78px;height:78px;border-radius:26px;font-size:27px}.identity h2{font-size:22px}.edit-button{grid-column:1/3;width:100%}.edit-panel{grid-column:1/3;display:grid}.edit-panel input{width:100%}.metrics-grid{grid-template-columns:1fr}.content-grid{grid-template-columns:1fr}.chart{gap:7px}.surface{padding:19px}.memory-card,.plan-card{align-items:flex-start;flex-wrap:wrap}.primary-button{width:100%}.records-dialog{padding:21px}.records-summary{gap:7px}.records-list article{grid-template-columns:10px minmax(0,1fr)}.records-list em{grid-column:2;justify-self:start}.records-actions{display:grid;grid-template-columns:1fr 1fr}.records-actions button,.records-actions a{justify-content:center;padding:0 10px}}
</style>
