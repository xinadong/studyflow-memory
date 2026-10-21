<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MemoryCenterView from './MemoryCenterView.vue'
import AgentIdentity from '../components/AgentIdentity.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import { listTasks } from '../services/tasks'
import type { SavedTask } from '../services/tasks'
import { listMemories } from '../services/memories'
import { errorMessage } from '../services/api'
import { useSessionStore } from '../stores/session'
import { memoryTypeLabels, statusLabels } from '../types'
import type { MemoryItem, TaskStatus } from '../types'

type Tab = 'overview' | 'tasks' | 'reviews' | 'memories'
const route = useRoute(), router = useRouter(), session = useSessionStore()
const activeTab = ref<Tab>('overview')
const tasks = ref<SavedTask[]>([])
const memories = ref<MemoryItem[]>([])
const busy = ref(true)
const error = ref('')
const taskFilter = ref<'all' | 'pending' | 'completed'>('all')
const search = ref('')
const statusText: Record<TaskStatus, string> = { pending: '待开始', active: '进行中', completed: '已完成', deferred: '已顺延' }
let version = 0
const studyTasks = computed(() => tasks.value.filter(task => task.task_type !== 'review'))
const reviews = computed(() => tasks.value.filter(task => task.task_type === 'review')
  .sort((a, b) => (a.due_at || '').localeCompare(b.due_at || '')))
const pendingReviews = computed(() => reviews.value.filter(task => task.status !== 'completed'))
const completed = computed(() => tasks.value.filter(task => task.status === 'completed').length)
const confirmed = computed(() => memories.value.filter(item => item.confirmation_status === 'confirmed'))
const pendingMemories = computed(() => memories.value.filter(item => item.confirmation_status === 'pending'))
const percent = computed(() => tasks.value.length ? Math.round(completed.value / tasks.value.length * 100) : 0)
const recentTasks = computed(() => [...tasks.value].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 4))
const recentMemories = computed(() => [...memories.value].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 3))
const tabs = computed(() => [
  { id: 'overview' as Tab, label: '学习概览', count: null },
  { id: 'tasks' as Tab, label: '学习任务', count: studyTasks.value.length },
  { id: 'reviews' as Tab, label: '复习安排', count: reviews.value.length },
  { id: 'memories' as Tab, label: '反馈记忆', count: memories.value.length },
])
const displayedTasks = computed(() => (activeTab.value === 'reviews' ? reviews.value : studyTasks.value)
  .filter(task => (taskFilter.value === 'all' || (taskFilter.value === 'completed'
    ? task.status === 'completed' : task.status !== 'completed'))
    && [task.title, task.course, task.knowledge_point].join(' ').toLowerCase().includes(search.value.trim().toLowerCase())))

async function load() {
  const current = ++version
  busy.value = true
  error.value = ''
  try {
    const [savedTasks, savedMemories] = await Promise.all([
      listTasks(session.userId), listMemories({ user_id: session.userId, active: true }),
    ])
    if (current !== version) return
    tasks.value = savedTasks.items
    memories.value = savedMemories.items
  } catch (cause) { if (current === version) error.value = errorMessage(cause) }
  finally { if (current === version) busy.value = false }
}
async function refreshMemories() {
  const userId = session.userId
  try {
    const result = await listMemories({ user_id: userId, active: true })
    if (userId === session.userId) memories.value = result.items
  } catch (cause) { error.value = errorMessage(cause) }
}
function selectTab(tab: Tab) {
  activeTab.value = tab
  taskFilter.value = 'all'
  search.value = ''
  void router.replace({ hash: tab === 'overview' ? '' : '#' + tab })
}
watch(() => route.hash, hash => {
  const tab = hash.slice(1)
  activeTab.value = ['tasks', 'reviews', 'memories'].includes(tab) ? tab as Tab : 'overview'
}, { immediate: true })
watch(() => session.userId, () => {
  tasks.value = []; memories.value = []
  void load()
}, { immediate: true })
function dateText(value?: string | null) {
  if (!value) return '未设置日期'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '日期待确认' : date.toLocaleString('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}
</script>

<template>
  <div class="profile-page">
    <header class="profile-heading"><div><p class="eyebrow">MY LEARNING SPACE</p><h1>个人中心</h1><p>回看学习记录，安排下一次复习，管理值得留下的记忆。</p></div><button class="refresh-button" :disabled="busy" @click="load"><span aria-hidden="true">↻</span> {{ busy ? '正在更新' : '刷新记录' }}</button></header>
    <ErrorNotice v-if="error" :message="error" @retry="load" />
    <LoadingState v-if="busy" text="正在整理你的学习记录…" />
    <template v-else-if="!error">
      <section class="profile-banner">
        <div class="profile-person"><div class="profile-avatar" aria-hidden="true">{{ session.userId.slice(0, 1).toUpperCase() || 'S' }}</div><div><span class="space-label">个人学习空间</span><h2>{{ session.userId }}</h2><p>每次完成与反馈，都让下一步更清晰。</p></div></div>
        <div class="banner-progress"><div><span>已保存任务完成情况</span><strong>{{ completed }} <small>/ {{ tasks.length }}</small></strong></div><div class="progress-track" role="progressbar" aria-label="已保存任务完成比例" :aria-valuenow="percent" :aria-valuemin="0" :aria-valuemax="100"><i :style="{ width: percent + '%' }" /></div><p>{{ tasks.length ? '包含学习任务与复习任务' : '添加第一个任务，开始记录你的进展' }}</p></div>
      </section>
      <div class="profile-tabs" role="tablist" aria-label="个人中心内容">
        <button v-for="tab in tabs" :id="'tab-' + tab.id" :key="tab.id" type="button" role="tab" :aria-selected="activeTab === tab.id" :aria-controls="'panel-' + tab.id" :class="{ active: activeTab === tab.id }" @click="selectTab(tab.id)">{{ tab.label }}<span v-if="tab.count !== null">{{ tab.count }}</span></button>
      </div>

      <section v-if="activeTab === 'overview'" id="panel-overview" class="tab-content" role="tabpanel" aria-labelledby="tab-overview">
        <div class="summary-grid">
          <button class="summary-card" @click="selectTab('tasks')"><span class="summary-symbol blue" aria-hidden="true">▤</span><span class="summary-copy"><small>学习任务</small><strong>{{ studyTasks.length }}<em>项</em></strong></span><span class="summary-arrow" aria-hidden="true">↗</span></button>
          <button class="summary-card" @click="selectTab('reviews')"><span class="summary-symbol cyan" aria-hidden="true">◷</span><span class="summary-copy"><small>待复习</small><strong>{{ pendingReviews.length }}<em>项</em></strong></span><span class="summary-arrow" aria-hidden="true">↗</span></button>
          <button class="summary-card" @click="selectTab('memories')"><span class="summary-symbol violet" aria-hidden="true">✦</span><span class="summary-copy"><small>已确认记忆</small><strong>{{ confirmed.length }}<em>条</em></strong></span><span class="summary-arrow" aria-hidden="true">↗</span></button>
        </div>
        <div class="overview-grid">
          <section class="profile-surface"><div class="section-heading"><div><span class="section-eyebrow">NEXT REVIEW</span><h2>下一次，温故知新</h2></div><button class="text-button" @click="selectTab('reviews')">全部复习 →</button></div>
            <div v-if="pendingReviews.length" class="review-list"><article v-for="task in pendingReviews.slice(0, 3)" :key="task.id" class="review-row"><span class="review-date"><small>复习安排</small><b>{{ dateText(task.due_at) }}</b></span><div><strong>{{ task.title }}</strong><p>{{ task.course }} · {{ task.duration_minutes }} 分钟</p></div></article></div>
            <div v-else class="empty-state"><span aria-hidden="true">◷</span><h3>还没有待复习的内容</h3><p>伴学结束后，确认复习建议，就会出现在这里。</p><RouterLink to="/study">开始一次伴学 →</RouterLink></div>
          </section>
          <section class="profile-surface memory-overview"><AgentIdentity /><div class="memory-overview-copy"><h2>记住的，是你的学习方式</h2><p>已确认的记忆可在相关任务中使用；待确认的内容，需要先由你决定。</p></div><div class="memory-status"><div><b>{{ confirmed.length }}</b><span>已确认</span></div><div><b>{{ pendingMemories.length }}</b><span>待确认</span></div><div><b>{{ memories.length - confirmed.length - pendingMemories.length }}</b><span>已归档 / 拒绝</span></div></div><button class="memory-manage" @click="selectTab('memories')">{{ pendingMemories.length ? '查看待确认记忆' : '管理我的反馈记忆' }}<span aria-hidden="true">→</span></button></section>
          <section class="profile-surface"><div class="section-heading"><div><span class="section-eyebrow">RECENT TASKS</span><h2>最近创建的任务</h2></div><button class="text-button" @click="selectTab('tasks')">学习任务 →</button></div><div v-if="recentTasks.length" class="recent-list"><article v-for="task in recentTasks" :key="task.id"><span class="task-check" :class="task.status" aria-hidden="true">{{ task.status === 'completed' ? '✓' : '·' }}</span><div><strong>{{ task.title }}</strong><p>{{ task.course }} · {{ task.duration_minutes }} 分钟<span v-if="task.task_type === 'review'"> · 复习</span></p></div><span class="status-pill" :class="task.status">{{ statusText[task.status] }}</span></article></div><div v-else class="empty-state compact"><h3>从一个小任务开始</h3><p>生成或添加真实任务后，就能在这里回看。</p><RouterLink to="/today">去安排学习 →</RouterLink></div></section>
          <section class="profile-surface"><div class="section-heading"><div><span class="section-eyebrow">RECENT MEMORIES</span><h2>最近留下的记忆</h2></div><button class="text-button" @click="selectTab('memories')">查看全部 →</button></div><div v-if="recentMemories.length" class="memory-snippets"><article v-for="item in recentMemories" :key="item.id"><div><span>{{ memoryTypeLabels[item.memory_type] }}</span><small>{{ statusLabels[item.confirmation_status] }}</small></div><p>{{ item.content }}</p><small>{{ item.scope === 'global' ? '全局 · 所有课程' : item.knowledge_point ? item.course + ' / ' + item.knowledge_point : item.course || '未指定课程' }}</small></article></div><div v-else class="empty-state compact"><h3>把有用的偏好留下来</h3><p>例如喜欢先看例子、每次学习 15 分钟。</p><button class="text-button" @click="selectTab('memories')">记录第一条记忆 →</button></div></section>
        </div>
        <p class="data-note">这里仅汇总当前用户已保存的记录。任务预计时长不代表实际学习时长，完成任务也不等同于掌握知识。</p>
      </section>

      <section v-else-if="activeTab === 'tasks' || activeTab === 'reviews'" :id="'panel-' + activeTab" class="profile-surface task-panel" role="tabpanel" :aria-labelledby="'tab-' + activeTab">
        <div :id="activeTab" class="tab-anchor" />
        <div class="section-heading"><div><span class="section-eyebrow">{{ activeTab === 'reviews' ? 'REVIEW SCHEDULE' : 'LEARNING RECORDS' }}</span><h2>{{ activeTab === 'reviews' ? '让复习有迹可循' : '每一项进展，都有记录' }}</h2><p>{{ activeTab === 'reviews' ? '查看已确认的复习日期与完成状态。' : '查看已保存的学习任务与完成状态。' }}</p></div><RouterLink class="text-button" to="/today">前往任务流 →</RouterLink></div>
        <div class="record-toolbar"><div class="record-filters" aria-label="任务状态筛选"><button :class="{ selected: taskFilter === 'all' }" @click="taskFilter = 'all'">全部</button><button :class="{ selected: taskFilter === 'pending' }" @click="taskFilter = 'pending'">未完成</button><button :class="{ selected: taskFilter === 'completed' }" @click="taskFilter = 'completed'">已完成</button></div><input v-model="search" type="search" aria-label="搜索课程或知识点" placeholder="搜索课程或知识点" /></div>
        <div v-if="displayedTasks.length" class="record-list"><article v-for="task in displayedTasks" :key="task.id"><span class="task-check" :class="task.status" aria-hidden="true">{{ task.status === 'completed' ? '✓' : '·' }}</span><div class="record-copy"><strong>{{ task.title }}</strong><p>{{ task.course }}<span v-if="task.knowledge_point"> · {{ task.knowledge_point }}</span></p></div><div class="record-meta"><span>{{ task.duration_minutes }} min</span><small>{{ activeTab === 'reviews' ? '复习' : '截止' }} {{ dateText(task.due_at) }}</small></div><span class="status-pill" :class="task.status">{{ statusText[task.status] }}</span></article></div><div v-else class="empty-state"><span aria-hidden="true">▤</span><h3>没有符合条件的记录</h3><p>可以调整筛选条件，或先在任务流中添加学习任务。</p><RouterLink to="/today">前往任务流 →</RouterLink></div>
      </section>

      <section v-else id="panel-memories" class="profile-surface memory-panel" role="tabpanel" aria-labelledby="tab-memories"><div id="memories"><MemoryCenterView embedded @changed="refreshMemories" /></div></section>
    </template>
  </div>
</template>

<style scoped>
.profile-page{max-width:1160px;margin:0 auto;padding:0 34px 48px;color:#202c58}.profile-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:0 0 26px}.profile-heading .eyebrow{margin:0 0 7px;color:#687ba8;font-size:10px;font-weight:600;letter-spacing:.12em}.profile-heading h1{margin:0 0 8px;font-size:30px;letter-spacing:-1px}.profile-heading>div>p:last-child{margin:0;color:#65769d;font-size:12px;line-height:1.8}.refresh-button{display:flex;align-items:center;gap:7px;flex-shrink:0;padding:10px 14px;border:1px solid #e4e8f5;border-radius:12px;background:#fff;color:#536a9d;font-size:11px}.refresh-button>span{font-size:18px}.profile-banner{display:flex;align-items:center;justify-content:space-between;gap:28px;padding:28px 30px;border:1px solid #fff;border-radius:26px;background:linear-gradient(120deg,#dcf3fc,#e5e7ff 65%,#eee0fc);box-shadow:0 8px 28px #6979b30a}.profile-person{display:flex;align-items:center;gap:18px;min-width:0}.profile-avatar{display:grid;place-items:center;flex:0 0 68px;height:68px;border:3px solid #ffffffc9;border-radius:23px;background:linear-gradient(140deg,#47c9de,#787bea);color:#fff;font-size:26px;font-weight:700;box-shadow:0 5px 15px #7488d220}.space-label{color:#6576a4;font-size:10px}.profile-person h2{margin:6px 0 7px;font-size:23px;overflow-wrap:anywhere}.profile-person p{margin:0;color:#60749c;font-size:11px;line-height:1.7}.banner-progress{flex:0 0 225px;padding-left:28px;border-left:1px solid #dce0f2}.banner-progress>div:first-child{display:flex;align-items:center;justify-content:space-between;gap:10px}.banner-progress span{color:#62749d;font-size:10px}.banner-progress strong{font-size:23px;color:#5d5ccc;font-weight:600}.banner-progress strong small{font-size:13px;color:#7f8db2}.progress-track{height:5px;margin-top:12px;border-radius:5px;background:#dfe4f4;overflow:hidden}.progress-track i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#70d2e0,#9985e9)}.banner-progress p{margin:9px 0 0;font-size:9px;color:#7585aa}.profile-tabs{display:flex;gap:26px;margin:26px 0 24px;border-bottom:1px solid #e6eaf5;overflow-x:auto}.profile-tabs>button{position:relative;display:flex;align-items:center;gap:7px;flex-shrink:0;padding:0 1px 15px;border:0;background:transparent;color:#687ba4;font-size:12px}.profile-tabs>button.active{color:#4f5bd5;font-weight:700}.profile-tabs>button.active:after{position:absolute;right:0;bottom:0;left:0;height:3px;border-radius:3px;background:#6b6de4;content:''}.profile-tabs>button>span{min-width:18px;padding:2px 5px;border-radius:6px;background:#edf0fa;color:#7585aa;font-size:9px}.profile-tabs>button.active>span{background:#e9eafd;color:#625cd2}.summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-bottom:20px}.summary-card{display:flex;align-items:center;gap:13px;min-width:0;padding:20px;border:1px solid #e9edf7;border-radius:20px;background:#fff;text-align:left}.summary-symbol{display:grid;place-items:center;flex:0 0 40px;height:40px;border-radius:13px;font-size:20px}.summary-symbol.blue{background:#e9edff;color:#6576d8}.summary-symbol.cyan{background:#e2f7fa;color:#28a8bd}.summary-symbol.violet{background:#eee8ff;color:#9167cf}.summary-copy{display:grid;gap:6px}.summary-copy small{color:#63749c;font-size:10px}.summary-copy strong{font-size:25px;line-height:1;color:#273965;font-weight:600}.summary-copy em{margin-left:6px;font-size:10px;font-weight:400;font-style:normal;color:#7586a8}.summary-card:hover{border-color:#cbd4f4;background:#fafbff}.summary-arrow{margin-left:auto;color:#889acc}.overview-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:20px}.profile-surface{min-width:0;padding:24px;border:1px solid #e8ecf6;border-radius:22px;background:#fff;box-shadow:0 6px 22px #56669d09}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-bottom:20px}.section-eyebrow{font-size:9px;letter-spacing:.1em;color:#7b8cb0}.section-heading h2{margin:7px 0 0;font-size:16px;font-weight:650;color:#283965}.section-heading p{margin:8px 0 0;color:#7181a4;font-size:11px;line-height:1.8}.text-button{flex-shrink:0;padding:0;border:0;background:transparent;color:#6667cb;font-size:10px;text-decoration:none}.review-list{display:grid;gap:14px}.review-row{display:flex;align-items:center;gap:14px;padding:14px 0;border-bottom:1px solid #f0f2f8}.review-row:last-child{border:0}.review-date{display:grid;gap:6px;flex:0 0 105px;padding:10px;border-radius:12px;background:#f2f8fc}.review-date small{font-size:9px;color:#7795b1}.review-date b{font-size:11px;color:#527eab;font-weight:500}.review-row>div{min-width:0}.review-row strong,.recent-list strong,.record-copy strong{display:block;font-size:12px;font-weight:600;overflow-wrap:anywhere;color:#3b4f7b}.review-row p,.recent-list p,.record-copy p{margin:6px 0 0;color:#7385a8;font-size:10px;line-height:1.7}.memory-overview{background:linear-gradient(145deg,#eff7ff,#f0eaff);border-color:#e6e5f7}.memory-overview-copy{margin:22px 0 18px}.memory-overview-copy h2{margin:0 0 9px;font-size:16px;font-weight:600}.memory-overview-copy p{margin:0;font-size:11px;color:#6c7ca2;line-height:1.9}.memory-status{display:grid;grid-template-columns:repeat(3,1fr);margin-bottom:20px}.memory-status>div{display:grid;gap:6px;border-right:1px solid #e7e8f5}.memory-status>div:not(:first-child){padding-left:18px}.memory-status>div:last-child{border:0}.memory-status b{font-size:23px;font-weight:500;color:#6565ce}.memory-status span{font-size:9px;color:#7788aa}.memory-manage{display:flex;align-items:center;justify-content:space-between;width:100%;padding:11px 14px;border:1px solid #e4e7f6;border-radius:11px;background:#ffffffa8;color:#6566ba;font-size:11px}.recent-list{display:grid}.recent-list article{display:flex;align-items:center;gap:12px;padding:14px 0;border-bottom:1px solid #f0f2f8}.recent-list article:last-child{border:0}.recent-list article>div{flex:1;min-width:0}.task-check{display:grid;place-items:center;flex:0 0 27px;height:27px;border-radius:9px;background:#f1f3fb;color:#7c8eb4;font-size:18px}.task-check.completed{background:#edf8f3;color:#309674;font-size:13px}.task-check.active{background:#e5e7ff;color:#7a60ce}.status-pill{flex-shrink:0;padding:5px 8px;border-radius:7px;background:#f3f5fb;color:#7486ac;font-size:9px;white-space:nowrap}.status-pill.completed{background:#edf8f3;color:#2c9370}.status-pill.active{background:#efedfc;color:#7a5ec0}.status-pill.deferred{background:#fdf5ec;color:#a87535}.memory-snippets{display:grid;gap:13px}.memory-snippets article{padding:13px;border:1px solid #edf0f8;border-radius:12px;background:#fcfcff}.memory-snippets article>div{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:10px;color:#8170b2}.memory-snippets small{font-size:9px;color:#7b8daf}.memory-snippets p{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;margin:9px 0;font-size:11px;line-height:1.8;color:#586d95;overflow-wrap:anywhere}.empty-state{display:grid;justify-items:center;align-content:center;min-height:205px;padding:26px 12px;text-align:center}.empty-state>span{display:grid;place-items:center;width:42px;height:42px;margin-bottom:12px;border-radius:14px;background:#f1f4fc;color:#8b9fca;font-size:22px}.empty-state h3{margin:0 0 8px;font-size:13px;color:#63779f;font-weight:500}.empty-state p{max-width:270px;margin:0 0 16px;font-size:11px;color:#7a8bad;line-height:1.9}.empty-state a{color:#6667c4;font-size:10px;text-decoration:none}.empty-state.compact{min-height:170px}.data-note{margin:20px 0 0;color:#7a8bad;font-size:10px;line-height:1.8;text-align:center}.record-toolbar{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-bottom:12px;padding-bottom:18px;border-bottom:1px solid #edf0f8}.record-filters{display:flex;gap:4px;padding:3px;border-radius:10px;background:#f5f7fc}.record-filters button{padding:7px 13px;border:0;border-radius:8px;background:transparent;color:#7486aa;font-size:10px}.record-filters button.selected{background:#fff;color:#6266c5;box-shadow:0 2px 5px #6979b310}.record-toolbar input{width:210px;min-width:0;height:34px;padding:0 12px;border:1px solid #e7ebf6;border-radius:10px;background:#fafbfe;color:#657495;font-size:11px}.record-toolbar input::placeholder{color:#8a9ab9}.record-list article{display:flex;align-items:center;gap:14px;padding:19px 0;border-bottom:1px solid #f0f2f8}.record-list article:last-child{border:0}.record-copy{min-width:0;flex:1}.record-meta{display:grid;gap:7px;text-align:right}.record-meta>span{font-size:11px;color:#7183a8}.record-meta small{font-size:9px;color:#8092b2}.memory-panel{scroll-margin-top:24px}.profile-page button:focus-visible,.profile-page a:focus-visible{outline:2px solid #9a9fe6;outline-offset:4px}
@media(max-width:1100px){.profile-page{padding-right:24px;padding-left:0}.overview-grid{grid-template-columns:minmax(0,1fr)}.profile-banner{padding:24px}.banner-progress{flex-basis:180px;padding-left:20px}.summary-card{padding:16px;gap:9px}.summary-symbol{flex-basis:34px;height:34px;border-radius:11px}}
@media(max-width:760px){.profile-page{padding:0 0 24px}.profile-heading{align-items:flex-start;margin-bottom:20px}.profile-heading h1{font-size:25px}.profile-heading>div>p:last-child{font-size:11px}.refresh-button{padding:8px 10px;font-size:10px}.profile-banner{flex-direction:column;align-items:stretch;gap:22px;padding:22px;border-radius:22px}.profile-avatar{flex-basis:54px;height:54px;border-radius:18px;font-size:22px}.profile-person h2{font-size:20px}.banner-progress{flex:auto;padding:16px 0 0;border-left:0;border-top:1px solid #dce0f2}.summary-grid{gap:8px}.summary-card{flex-direction:column;align-items:flex-start;position:relative;padding:14px 12px}.summary-copy strong{font-size:22px}.summary-card:hover{border-color:#cbd4f4;background:#fafbff}.summary-arrow{position:absolute;top:16px;right:10px}.summary-copy{gap:8px}.summary-symbol{width:30px;flex-basis:30px;height:30px;font-size:16px}.profile-tabs{gap:20px;margin-top:22px}.profile-tabs>button{font-size:11px;gap:4px}.profile-surface{padding:19px}.section-heading{gap:8px}.section-heading h2{font-size:15px}.review-row{gap:10px}.review-date{flex-basis:95px}.record-toolbar{align-items:stretch;flex-direction:column}.record-toolbar input{width:100%}.record-list article{gap:10px;flex-wrap:wrap}.record-meta{order:4;flex-basis:100%;margin-left:37px;text-align:left;display:flex;gap:10px}.status-pill{font-size:9px}.data-note{text-align:left}}
</style>
