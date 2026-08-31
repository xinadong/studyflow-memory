<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import MemoryCard from '../components/MemoryCard.vue'
import { deleteMemory, listMemories, submitFeedback, updateMemory } from '../services/memories'
import { errorMessage } from '../services/api'
import { useSessionStore } from '../stores/session'
import { useMemoryStore } from '../stores/memory'
import type { ConfirmationStatus, MemoryType } from '../types'

const session=useSessionStore(), memories=useMemoryStore()
withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })
const busy=ref(false), saving=ref(false), error=ref(''), success=ref('')
const filters=reactive<{course:string;memory_type:MemoryType|'';confirmation_status:ConfirmationStatus|''}>({course:'',memory_type:'',confirmation_status:''})
const feedback=reactive<{content:string;feedback_type:MemoryType|'';explicit:boolean}>({content:'',feedback_type:'',explicit:false})

async function load(){busy.value=true;error.value='';try{const data=await listMemories({user_id:session.userId,course:filters.course||undefined,memory_type:filters.memory_type,confirmation_status:filters.confirmation_status,active:true});memories.items=data.items}catch(e){error.value=errorMessage(e)}finally{busy.value=false}}
async function submit(){saving.value=true;error.value='';success.value='';try{const data=await submitFeedback({user_id:session.userId,course:session.course,content:feedback.content,...(feedback.feedback_type?{feedback_type:feedback.feedback_type}:{}),...(feedback.feedback_type?{explicit:feedback.explicit}:{}),task_type:'study',knowledge_point:session.knowledgePoint||undefined});success.value=`反馈已转为 ${data.memories[0]?.confirmation_status==='confirmed'?'已确认':'待确认'}记忆`;feedback.content='';await load()}catch(e){error.value=errorMessage(e)}finally{saving.value=false}}
async function setStatus(id:string,status:ConfirmationStatus){try{await updateMemory(id,{confirmation_status:status});await load()}catch(e){error.value=errorMessage(e)}}
async function edit(id:string,content:string){try{await updateMemory(id,{content});await load()}catch(e){error.value=errorMessage(e)}}
async function remove(id:string){if(!window.confirm('确定删除这条记忆吗？系统会执行软删除并保留审计记录。'))return;try{await deleteMemory(id);await load()}catch(e){error.value=errorMessage(e)}}
onMounted(load)
</script>
<template><section class="memory-center" :class="{ embedded }"><PageHeader v-if="!embedded" eyebrow="MEMORY CENTER" title="让 Agent 记住真正有用的事" subtitle="待确认记忆不会影响计划；你始终可以确认、修改、拒绝或删除。"><span class="chip pending">{{ memories.pendingCount }} 条待确认</span></PageHeader>
  <div v-else class="embedded-heading"><div><p class="eyebrow">MEMORY CENTER</p><h2>我的反馈记忆</h2><p>只有已确认记忆才会影响 Agent；你可以随时确认、修改、归档或删除。</p></div><span class="chip pending">{{ memories.pendingCount }} 条待确认</span></div>
  <form class="feedback-box card panel" @submit.prevent="submit"><div><p class="eyebrow">TELL FLOW AGENT</p><h2>告诉 Flow Agent</h2><p class="muted">明确类型能提高现场演示稳定性；选择自动判断时会调用模型分类。</p></div><div class="field"><label for="feedback">你的反馈</label><textarea id="feedback" v-model.trim="feedback.content" required rows="3" placeholder="例如：先给我看例子，再讲定义。"/></div><div class="feedback-options"><div class="field"><label for="type">记忆类型</label><select id="type" v-model="feedback.feedback_type"><option value="">自动判断类型</option><option value="task_preference">任务偏好</option><option value="explanation_preference">解释偏好</option><option value="recovery_experience">恢复经验</option><option value="review_schedule">复习计划</option></select></div><label class="explicit"><input v-model="feedback.explicit" type="checkbox" :disabled="!feedback.feedback_type"/>这是我的明确偏好</label><button class="btn btn-primary" :disabled="saving||!feedback.content">{{ saving?'正在保存…':'保存为记忆 →' }}</button></div></form>
  <div v-if="success" class="notice success">{{ success }}</div><ErrorNotice v-if="error" :message="error" @retry="load"/>
  <div class="section-title"><h2>我的记忆</h2><button class="link-button" @click="load">刷新</button></div>
  <div class="filters card"><div class="field"><label for="filter-course">课程</label><input id="filter-course" v-model.trim="filters.course" placeholder="全部课程" @change="load"/></div><div class="field"><label for="filter-type">类型</label><select id="filter-type" v-model="filters.memory_type" @change="load"><option value="">全部类型</option><option value="task_preference">任务偏好</option><option value="explanation_preference">解释偏好</option><option value="knowledge_state">知识状态</option><option value="recovery_experience">恢复经验</option><option value="review_schedule">复习计划</option></select></div><div class="field"><label for="filter-status">状态</label><select id="filter-status" v-model="filters.confirmation_status" @change="load"><option value="">全部状态</option><option value="pending">待确认</option><option value="confirmed">已确认</option><option value="rejected">已拒绝</option><option value="archived">已归档</option></select></div></div>
  <LoadingState v-if="busy" text="正在读取你的记忆…"/><div v-else-if="!memories.items.length" class="card panel empty"><h3>没有符合条件的记忆</h3><p class="muted">提交一条反馈，或调整上方筛选条件。</p></div><div v-else class="memory-grid"><MemoryCard v-for="item in memories.items" :key="item.id" :memory="item" @update="setStatus(item.id,$event)" @edit="edit(item.id,$event)" @remove="remove(item.id)"/></div>
</section></template>
<style scoped>.feedback-box{display:grid;gap:18px}.feedback-box h2{margin:4px 0 7px}.feedback-box p{margin-bottom:0}.feedback-options{display:grid;grid-template-columns:1fr auto auto;gap:16px;align-items:end}.explicit{display:flex;align-items:center;gap:8px;min-height:42px;color:var(--muted);font-size:13px}.explicit input{accent-color:var(--brand)}.filters{padding:15px;display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.memory-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px;margin-top:18px}.empty{text-align:center;margin-top:18px}@media(max-width:850px){.memory-grid{grid-template-columns:1fr}}@media(max-width:650px){.feedback-options,.filters{grid-template-columns:1fr}.explicit{min-height:0}}</style>
