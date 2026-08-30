<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import MemoryReference from '../components/MemoryReference.vue'
import UnderstandingQuestion from '../components/UnderstandingQuestion.vue'
import { checkUnderstanding } from '../services/agent'
import { errorMessage } from '../services/api'
import { usePlanStore } from '../stores/plan'
import { useSessionStore } from '../stores/session'
import type { Task, UnderstandingCheckResponse, UnderstandingLevel } from '../types'
import uploadMaterialIcon from '../assets/upload-material.svg'

const session = useSessionStore(), plans = usePlanStore()
const level = ref<UnderstandingLevel>('recall'), material = ref(''), answer = ref('')
const materialInput = ref<HTMLInputElement | null>(null)
const selectedMaterialName = ref('')
const result = ref<UnderstandingCheckResponse | null>(null), busy = ref(false), error = ref('')
const levels: UnderstandingLevel[] = ['recall', 'relate', 'transfer']
const levelCards = [
  { value:'recall' as const, icon:'▤', title:'复述概念', subtitle:'用自己的话讲清楚' },
  { value:'relate' as const, icon:'⌘', title:'关联知识', subtitle:'连接已学内容' },
  { value:'transfer' as const, icon:'↗', title:'迁移应用', subtitle:'把理解用于新问题' },
]
const showCustomTask = ref(false)
const customError = ref('')
const customTask = reactive({ course: '', knowledgePoint: '' })
const availableTasks = computed(() => plans.plan?.tasks.length ? plans.plan.tasks : plans.previewTasks)
const activeTask = computed(() => session.selectedTask || availableTasks.value[0])
function selectTask(task: Task){ session.selectedTask=task; result.value=null; answer.value='' }
function rawTaskStatus(task: Task, index:number){ return plans.plan ? plans.statuses[task.id] : index===0?'completed':index===2?'deferred':'pending' }
function taskStatus(task: Task, index:number){const status=rawTaskStatus(task,index);return status==='completed'?'已完成':status==='deferred'?'已顺延':status==='active'?'进行中':'待开始'}
function statusClass(task: Task, index:number){const status=rawTaskStatus(task,index);return status==='completed'?'status-0':status==='deferred'?'status-2':'status-1'}
function openCustomTask(){customTask.course=session.course;customTask.knowledgePoint='';customError.value='';showCustomTask.value=true}
function saveCustomTask(){
  if(!customTask.course.trim()||!customTask.knowledgePoint.trim()){customError.value='请填写课程和知识点。';return}
  const task:Task={id:`custom-${Date.now()}`,course:customTask.course.trim(),title:`${customTask.course.trim()} · ${customTask.knowledgePoint.trim()}`,description:'理解检验自定义任务',duration_minutes:25,task_type:'study',knowledge_point:customTask.knowledgePoint.trim()}
  plans.addImportedTasks([task]);session.course=task.course!;session.knowledgePoint=task.knowledge_point!;selectTask(task);showCustomTask.value=false
}
function chooseMaterial(){ materialInput.value?.click() }
async function onMaterialSelected(event: Event){
  const file = (event.target as HTMLInputElement).files?.[0]
  if(!file) return
  selectedMaterialName.value = file.name
  material.value = await file.text()
}
async function requestQuestion(withAnswer=false){ busy.value=true; error.value=''; try{ result.value=await checkUnderstanding({user_id:session.userId,course:session.course,knowledge_point:activeTask.value?.knowledge_point||session.knowledgePoint||'当前知识点',task_type:activeTask.value?.task_type||'study',material:material.value,level:level.value,...(withAnswer?{answer:answer.value}:{})}) }catch(e){error.value=errorMessage(e)}finally{busy.value=false} }
function selectLevel(value:UnderstandingLevel){level.value=value;result.value=null;answer.value=''}
function nextLevel(){const i=levels.indexOf(level.value);selectLevel(levels[Math.min(i+1,levels.length-1)]);requestQuestion()}
</script>

<template>
<section class="study-page">
  <header class="study-header"><p class="study-eyebrow">SOCRATIC CHECK · FLOW TUTOR</p><h1>苏格拉底理解检验</h1><p>选择今天的学习任务与提问方式，让 Flow Tutor 只问一个真正关键的问题。</p></header>
  <section class="selection-section">
    <div class="selection-heading"><span class="step-badge">01</span><h2>选择要检验的学习任务</h2><span class="choice-pill">必选</span></div>
    <div class="task-selector"><div class="selector-toolbar"><span>从今日任务中选择一项</span><button type="button" @click="openCustomTask">＋ 自定义任务</button></div>
      <button v-for="(task,index) in availableTasks" :key="task.id" type="button" class="task-option" :class="{active:activeTask?.id===task.id}" @click="selectTask(task)"><span class="radio"><i /></span><span class="task-label"><strong>{{task.title}}</strong><small>{{task.duration_minutes}} 分钟 · {{task.description}}</small></span><span class="status" :class="statusClass(task,index)">{{taskStatus(task,index)}}</span></button>
    </div>
  </section>
  <div v-if="showCustomTask" class="custom-backdrop" @click.self="showCustomTask=false">
    <form class="custom-dialog" role="dialog" aria-modal="true" aria-labelledby="custom-task-title" @submit.prevent="saveCustomTask">
      <button type="button" class="custom-close" aria-label="关闭" @click="showCustomTask=false">×</button>
      <p>理解检验</p><h2 id="custom-task-title">添加自定义任务</h2><span>任务会同步加入弹性任务流的今日任务时间线。</span>
      <label>课程<input v-model.trim="customTask.course" required placeholder="例如：高等数学" autofocus /></label>
      <label>知识点<input v-model.trim="customTask.knowledgePoint" required placeholder="例如：导数应用" /></label>
      <div v-if="customError" class="custom-error" role="alert">{{customError}}</div>
      <div class="custom-actions"><button type="button" @click="showCustomTask=false">取消</button><button class="custom-save">添加并选中</button></div>
    </form>
  </div>
  <section class="selection-section level-section">
    <div class="selection-heading mode-heading"><span class="step-badge">02</span><div><h2>选择苏格拉底提问方式</h2><p>决定 Flow Tutor 如何追问</p></div><span class="choice-pill">单选</span></div>
    <div class="mode-grid"><button v-for="item in levelCards" :key="item.value" type="button" class="mode-card" :class="{active:level===item.value}" @click="selectLevel(item.value)"><span class="mode-icon">{{item.icon}}</span><i v-if="level===item.value"/><strong>{{item.title}}</strong><small>{{item.subtitle}}</small></button></div>
  </section>
  <div class="action-grid">
    <article class="upload-card"><span class="upload-icon" aria-hidden="true"><img :src="uploadMaterialIcon" alt="" /></span><span class="upload-copy"><strong>添加文本材料</strong><small>正文仅用于生成本轮问题</small></span><span class="file-types">{{ selectedMaterialName || '支持 TXT · Markdown；PDF、Word、图片待接入解析' }}</span><button class="choose-material" type="button" @click="chooseMaterial">选择文本</button><input ref="materialInput" class="sr-only" type="file" accept=".txt,.md,text/plain,text/markdown" @change="onMaterialSelected"/></article>
    <button v-if="!result&&!busy" class="start-companion" type="button" @click="requestQuestion()"><strong>开始伴学 <span>→</span></strong><small>已选择 1 个任务 · 1 种方式</small></button>
  </div>
  <LoadingState v-if="busy" text="正在结合课程材料与解释偏好生成问题…"/><ErrorNotice v-if="error" :message="error" @retry="requestQuestion(Boolean(answer))"/><UnderstandingQuestion v-if="result" :result="result" :answer="answer" :busy="busy" @update:answer="answer=$event" @submit="requestQuestion(true)"/><MemoryReference v-if="result" :retrieved="result.retrieved_memory_ids" :used="result.used_memory_ids" :candidates="result.candidate_memory_ids"/>
  <div v-if="result?.assessed_level" class="finish-row card panel"><div><span class="chip success">本轮形成性反馈已生成</span><h3>回答证据将用于更新相关知识状态</h3><p class="muted small">这不是严格的掌握证明，也不会跨主题推断你的能力。</p></div><button class="btn btn-primary" :disabled="level==='transfer'" @click="nextLevel">下一层检验 →</button></div>
</section>
</template>

<style scoped>
.study-page{width:820px;color:var(--text)}.study-header{height:126px}.study-eyebrow{margin:0 0 4px;color:var(--brand);font-size:12px;font-weight:800}.study-header h1{margin:0 0 5px;font-size:34px;line-height:1.18}.study-header>p:last-child{margin:0;color:var(--muted);font-size:13px}.selection-section{margin-bottom:26px}.selection-heading{height:42px;display:grid;grid-template-columns:42px 1fr 78px;align-items:start;gap:14px}.selection-heading h2{margin:0;font-size:21px;line-height:32px}.step-badge{display:grid;place-items:center;width:42px;height:32px;border-radius:16px;background:linear-gradient(90deg,#4fe5f0,#8c73ff);color:#fff;font-size:14px;font-weight:800}.choice-pill{display:grid;place-items:center;width:78px;height:32px;border:1px solid rgba(209,214,209,.8);border-radius:16px;background:rgba(255,255,255,.58);color:var(--muted);font-size:12px}.task-selector{height:286px;padding:18px 23px;border:1px solid rgba(255,255,255,.9);border-radius:24px;background:linear-gradient(100deg,rgba(237,250,255,.82),rgba(242,235,255,.72))}.selector-toolbar{height:39px;display:flex;justify-content:space-between;color:var(--muted);font-size:12px}.selector-toolbar button{border:0;background:transparent;color:var(--brand);font-size:12px;font-weight:800}.task-option{width:100%;height:58px;margin-bottom:12px;padding:0 14px 0 17px;display:grid;grid-template-columns:22px 1fr 86px;align-items:center;gap:13px;border:1px solid rgba(255,255,255,.8);border-radius:18px;background:rgba(255,255,255,.55);color:var(--text);text-align:left}.task-option.active{border-color:#73dbeb;background:rgba(255,255,255,.62)}.radio{width:20px;height:20px;display:grid;place-items:center;border:1px solid #a6b7dc;border-radius:50%;background:#fff}.task-option.active .radio{border-color:#637df5;background:#637df5}.task-option.active .radio i{width:8px;height:8px;border-radius:50%;background:#fff}.task-label{min-width:0;display:grid;gap:3px}.task-label strong{overflow:hidden;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.task-label small{color:#7387b2;font-size:10px}.status{justify-self:end;width:76px;padding:7px 0;border-radius:15px;text-align:center;font-size:10px;font-weight:800}.status-0{background:rgba(214,237,235,.9);color:#21a67a}.status-1{background:rgba(224,232,255,.9);color:#4f7df2}.status-2{background:rgba(255,229,214,.9);color:#ff7329}.level-section{margin-bottom:20px}.mode-heading{height:62px}.mode-heading p{margin:-3px 0 0;color:#7387b2;font-size:11px}.mode-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.mode-card{position:relative;height:178px;padding:20px;display:flex;flex-direction:column;align-items:flex-start;border:1px solid rgba(255,255,255,.9);border-radius:24px;background:rgba(255,255,255,.62);color:var(--text);text-align:left}.mode-card.active{background:linear-gradient(45deg,#8c6bf5,#6191ff 52%,#4fdbed);color:#fff}.mode-icon{width:48px;height:48px;display:grid;place-items:center;border:1px solid rgba(219,211,211,.8);border-radius:14px;background:rgba(255,255,255,.72);color:#617ab8;font-size:21px}.mode-card.active .mode-icon{border-color:rgba(255,255,255,.8);background:rgba(255,255,255,.22);color:#fff}.mode-card>i{position:absolute;right:22px;top:22px;width:12px;height:12px;border-radius:50%;background:#fff}.mode-card strong{margin-top:17px;font-size:19px}.mode-card small{margin-top:10px;color:#7387b2;font-size:12px}.mode-card.active small{color:#ebf5ff}.action-grid{display:grid;grid-template-columns:542px 260px;gap:18px}.upload-card{height:118px;padding:18px 20px;display:grid;grid-template-columns:62px minmax(0,1fr) 116px;grid-template-rows:62px 20px;gap:7px 14px;border:1px solid rgba(255,255,255,.9);border-radius:24px;background:linear-gradient(100deg,rgba(240,252,255,.86),rgba(245,237,255,.78));overflow:hidden}.upload-icon{width:62px;height:62px;display:grid;place-items:center;border:1px solid rgba(255,255,255,.9);border-radius:20px;background:linear-gradient(90deg,rgba(221,251,255,.96),rgba(233,225,255,.96));box-shadow:0 6px 14px rgba(122,145,230,.17)}.upload-icon img{display:block;width:28px;height:28px}.upload-copy{display:grid;align-content:center;gap:7px}.upload-copy strong{font-size:19px}.upload-copy small,.file-types{color:#7387b2;font-size:10px}.file-types{grid-column:1/3;align-self:end;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.choose-material{grid-column:3;grid-row:1/3;align-self:end;width:116px;height:34px;margin-bottom:1px;border:0;border-radius:17px;background:linear-gradient(90deg,#4fe5f0,#617df2);color:#fff;font-size:12px;font-weight:800}.start-companion{height:118px;display:grid;place-content:center;gap:11px;border:0;border-radius:24px;background:linear-gradient(90deg,#4fe5f0,#618cff 55%,#8c6bf5);color:#fff}.start-companion strong{font-size:28px}.start-companion small{color:#ebf5ff;font-size:10px}.finish-row{margin-top:18px;display:flex;justify-content:space-between;align-items:center}.finish-row h3{margin:10px 0 5px}.finish-row p{margin:0}
@media(max-width:1100px){.study-page{width:100%}.task-selector{height:auto}.action-grid{grid-template-columns:minmax(0,2fr) minmax(220px,1fr)}}
@media(max-width:760px){.study-header{height:auto;margin-bottom:24px}.study-header h1{font-size:27px}.selection-heading{grid-template-columns:38px 1fr 60px}.step-badge{width:38px}.choice-pill{width:60px}.selection-heading h2{font-size:18px}.task-selector{padding:14px}.task-option{grid-template-columns:22px minmax(0,1fr);height:auto;min-height:68px}.status{grid-column:2;justify-self:start;margin-top:-8px}.mode-grid,.action-grid{grid-template-columns:1fr}.mode-card{height:142px}.mode-card strong{margin-top:12px}.upload-card{height:auto;min-height:150px;grid-template-columns:62px minmax(0,1fr);grid-template-rows:62px 34px;align-content:center}.file-types{grid-column:1/2}.choose-material{grid-column:2;grid-row:2;justify-self:end}.start-companion{height:96px}.finish-row{display:grid;gap:16px}}
.custom-backdrop{position:fixed;z-index:1000;inset:0;display:grid;place-items:center;padding:20px;background:rgba(25,31,70,.3);backdrop-filter:blur(8px)}.custom-dialog{position:relative;width:min(440px,100%);padding:27px;border-radius:26px;background:#fff;box-shadow:0 30px 80px rgba(35,47,110,.28)}.custom-dialog>p{margin:0;color:#6075ea;font-size:10px;font-weight:900}.custom-dialog h2{margin:7px 0 5px;font-size:23px}.custom-dialog>span{color:#7b87a7;font-size:11px}.custom-close{position:absolute;right:19px;top:18px;width:34px;height:34px;border:0;border-radius:50%;background:#eef1fa;color:#7782a0;font-size:20px}.custom-dialog label{display:grid;gap:6px;margin-top:16px;color:#647091;font-size:11px;font-weight:800}.custom-dialog input{height:42px;padding:0 13px;border:1px solid #dfe4f3;border-radius:13px;background:#fafbff;color:#172052;font:inherit}.custom-error{margin-top:10px;color:#d9506c;font-size:11px}.custom-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}.custom-actions button{height:40px;padding:0 17px;border:0;border-radius:13px;background:#eef1f8;color:#697596;font-weight:800}.custom-actions .custom-save{background:linear-gradient(90deg,#52d9e6,#7772ef);color:#fff}
.task-selector{height:auto;max-height:360px;overflow-y:auto}
</style>
