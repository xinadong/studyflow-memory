<script setup lang="ts">
import { onMounted, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import MemoryReference from '../components/MemoryReference.vue'
import { comparePlans, getMetrics } from '../services/evaluation'
import { errorMessage } from '../services/api'
import { useSessionStore } from '../stores/session'
import type { EvaluationResponse, MetricsResponse, PlanResponse } from '../types'

const session=useSessionStore(), comparison=ref<EvaluationResponse|null>(null),metrics=ref<MetricsResponse|null>(null),busy=ref(false),error=ref('')
async function loadMetrics(){try{metrics.value=await getMetrics()}catch(e){error.value=errorMessage(e)}}
async function compare(){busy.value=true;error.value='';try{comparison.value=await comparePlans({user_id:session.userId,course:session.course,goal:session.goal,available_minutes:25,task_type:'study',knowledge_point:session.knowledgePoint||undefined});await loadMetrics()}catch(e){error.value=errorMessage(e)}finally{busy.value=false}}
const minutes=(plan:PlanResponse)=>plan.tasks.reduce((sum,item)=>sum+item.duration_minutes,0)
onMounted(loadMetrics)
</script>
<template><section><PageHeader eyebrow="EVIDENCE · EVALUATION" title="记忆有没有真正改变结果？" subtitle="同一目标分别运行有记忆和无记忆计划，所有数据来自当前本地运行记录。"><button class="btn btn-primary" :disabled="busy" @click="compare">{{ busy?'正在对照…':'运行一次对照评测' }}</button></PageHeader>
  <div class="notice">这里不展示未测量的准确率或节省比例；只有接口真实返回的任务、Token、延迟和记忆引用会被呈现。</div><LoadingState v-if="busy" text="正在分别运行有记忆与无记忆计划…"/><ErrorNotice v-if="error" :message="error" @retry="compare"/>
  <div v-if="comparison" class="comparison-grid">
    <article v-for="column in [{title:'无记忆计划',mode:'基准策略',plan:comparison.without_memory},{title:'使用记忆计划',mode:'结构化记忆',plan:comparison.with_memory}]" :key="column.mode" class="plan-column card panel">
      <div class="row between"><div><p class="eyebrow">{{ column.mode }}</p><h2>{{ column.title }}</h2></div><span class="chip">{{ minutes(column.plan) }} 分钟</span></div>
      <div v-for="task in column.plan.tasks" :key="task.id" class="compare-task"><strong>{{ task.title }}</strong><span>{{ task.duration_minutes }} 分钟</span><small>{{ task.description }}</small></div>
      <p class="explanation">{{ column.plan.explanation }}</p>
    </article>
  </div>
  <MemoryReference v-if="comparison" :retrieved="comparison.with_memory.retrieved_memory_ids" :used="comparison.with_memory.used_memory_ids" :candidates="comparison.with_memory.candidate_memory_ids"/>
  <div class="section-title"><h2>真实运行指标</h2><span class="chip">本地数据库</span></div><div v-if="metrics" class="metric-grid"><div class="metric"><span>Agent 运行</span><strong>{{ metrics.agent_runs }}</strong><small>{{ metrics.success_count }} 成功 · {{ metrics.failure_count }} 失败</small></div><div class="metric"><span>输入 / 输出 Token</span><strong>{{ metrics.input_tokens }} / {{ metrics.output_tokens }}</strong><small>记忆上下文 {{ metrics.memory_tokens }}</small></div><div class="metric"><span>模型耗时 P50 / P95</span><strong>{{ metrics.model_latency_ms_percentiles.p50 }} / {{ metrics.model_latency_ms_percentiles.p95 }}</strong><small>毫秒</small></div><div class="metric"><span>记忆 使用 / 检索</span><strong>{{ metrics.memory_counts.used }} / {{ metrics.memory_counts.retrieved }}</strong><small>候选 {{ metrics.memory_counts.candidate }}</small></div></div>
</section></template>
<style scoped>.comparison-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin:20px 0}.plan-column h2{margin:4px 0}.compare-task{display:grid;grid-template-columns:1fr auto;gap:6px;padding:14px 0;border-bottom:1px solid var(--border)}.compare-task small{grid-column:1/-1;color:var(--muted)}.explanation{margin:16px 0 0;color:var(--muted);line-height:1.6;font-size:13px}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric small{color:var(--muted)}@media(max-width:900px){.metric-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:650px){.comparison-grid,.metric-grid{grid-template-columns:1fr}}</style>
