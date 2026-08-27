<script setup lang="ts">
import { ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import MemoryReference from '../components/MemoryReference.vue'
import UnderstandingQuestion from '../components/UnderstandingQuestion.vue'
import { checkUnderstanding } from '../services/agent'
import { errorMessage } from '../services/api'
import { useSessionStore } from '../stores/session'
import type { UnderstandingCheckResponse, UnderstandingLevel } from '../types'

const session = useSessionStore()
const level = ref<UnderstandingLevel>('recall')
const material = ref('')
const answer = ref('')
const result = ref<UnderstandingCheckResponse | null>(null)
const busy = ref(false)
const error = ref('')
const levels: UnderstandingLevel[] = ['recall', 'relate', 'transfer']

async function requestQuestion(withAnswer = false) {
  busy.value = true
  error.value = ''
  try {
    result.value = await checkUnderstanding({
      user_id: session.userId,
      course: session.course,
      knowledge_point: session.selectedTask?.knowledge_point || session.knowledgePoint || '当前知识点',
      task_type: session.selectedTask?.task_type || 'study',
      material: material.value,
      level: level.value,
      ...(withAnswer ? { answer: answer.value } : {}),
    })
  } catch (e) { error.value = errorMessage(e) }
  finally { busy.value = false }
}

function selectLevel(value: UnderstandingLevel) {
  level.value = value
  result.value = null
  answer.value = ''
}

function nextLevel() {
  const index = levels.indexOf(level.value)
  selectLevel(levels[Math.min(index + 1, levels.length - 1)])
  requestQuestion()
}
</script>

<template>
  <section>
    <PageHeader eyebrow="SOCRATIC CHECK" title="苏格拉底理解检验" subtitle="每轮只问一个核心问题，从复述到关联，再走向迁移">
      <RouterLink class="btn btn-secondary" to="/recovery">我卡住了</RouterLink>
    </PageHeader>

    <div class="task-context card panel">
      <div><p class="eyebrow">当前检验内容</p><h2>{{ session.selectedTask?.title || session.goal }}</h2><p class="muted">{{ session.course }} · {{ session.selectedTask?.knowledge_point || session.knowledgePoint }}</p></div>
      <span class="chip success">形成性反馈</span>
    </div>

    <div class="principles">
      <div><b>01</b><strong>复述</strong><small>能否用自己的话说明</small></div>
      <i>→</i>
      <div><b>02</b><strong>关联</strong><small>能否连接已有知识</small></div>
      <i>→</i>
      <div><b>03</b><strong>迁移</strong><small>能否用于新情境</small></div>
    </div>

    <div class="card panel material">
      <div class="field"><label for="material">预置课程材料或摘要</label><textarea id="material" v-model="material" rows="3" placeholder="粘贴本次学习材料的关键内容；文件不会被上传。" /></div>
      <span class="chip">本轮材料</span>
    </div>

    <div class="level-row">
      <button v-for="item in levels" :key="item" :class="{ active: level === item }" @click="selectLevel(item)">{{ { recall:'01 复述', relate:'02 关联', transfer:'03 迁移' }[item] }}</button>
    </div>

    <button v-if="!result && !busy" class="btn btn-primary start-check" @click="requestQuestion()">生成本轮核心问题 →</button>
    <LoadingState v-if="busy" text="正在结合课程材料与解释偏好生成问题…" />
    <ErrorNotice v-if="error" :message="error" @retry="requestQuestion(Boolean(answer))" />
    <UnderstandingQuestion v-if="result" :result="result" :answer="answer" :busy="busy" @update:answer="answer=$event" @submit="requestQuestion(true)" />
    <MemoryReference v-if="result" :retrieved="result.retrieved_memory_ids" :used="result.used_memory_ids" :candidates="result.candidate_memory_ids" />

    <div v-if="result?.assessed_level" class="finish-row card panel">
      <div><span class="chip success">本轮形成性反馈已生成</span><h3>回答证据将用于更新相关知识状态</h3><p class="muted small">这不是严格的掌握证明，也不会跨主题推断你的能力。</p></div>
      <button class="btn btn-primary" :disabled="level === 'transfer'" @click="nextLevel">下一层检验 →</button>
    </div>
  </section>
</template>

<style scoped>
.task-context{display:flex;justify-content:space-between;align-items:flex-start}.task-context h2{margin:5px 0 7px}.principles{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;align-items:center;gap:12px;margin:20px 0}.principles>div{display:grid;gap:5px;padding:17px;border-radius:18px;background:white;border:1px solid var(--border)}.principles b{color:var(--brand);font-size:12px}.principles small{color:var(--muted)}.principles i{font-style:normal;color:var(--brand)}.material{display:flex;align-items:center;gap:20px}.material .field{flex:1}.level-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:22px 0}.level-row button{padding:12px;border:0;border-radius:13px;background:#eef2ff;color:var(--muted);font-weight:800}.level-row button.active{background:var(--brand);color:white}.start-check{width:100%;margin-bottom:18px}.finish-row{margin-top:18px;display:flex;justify-content:space-between;align-items:center}.finish-row h3{margin:10px 0 5px}.finish-row p{margin:0}
@media(max-width:760px){.principles{grid-template-columns:1fr}.principles i{display:none}.material,.finish-row{display:grid}.task-context{gap:12px}.level-row{font-size:12px}}
</style>
