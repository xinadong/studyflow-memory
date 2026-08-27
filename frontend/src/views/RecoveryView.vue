<script setup lang="ts">
import { ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import LoadingState from '../components/LoadingState.vue'
import ErrorNotice from '../components/ErrorNotice.vue'
import RecoveryAction from '../components/RecoveryAction.vue'
import { recoverLearning } from '../services/agent'
import { errorMessage } from '../services/api'
import { useSessionStore } from '../stores/session'
import { usePlanStore } from '../stores/plan'
import type { BlockType, RecoveryResponse } from '../types'

const session=useSessionStore(), plans=usePlanStore()
const block=ref<BlockType>((sessionStorage.getItem('studyflow-block') as BlockType) || 'time')
const context=ref(session.selectedTask ? `当前任务：${session.selectedTask.title}` : '')
const result=ref<RecoveryResponse|null>(null), busy=ref(false), error=ref(''), applied=ref(false)
const released=ref<string[]>([])
const options=[{value:'time',icon:'◷',label:'时间不足',desc:'剩余时间无法完成原计划'},{value:'too_hard',icon:'?',label:'内容太难',desc:'暂时找不到理解入口'},{value:'distraction',icon:'◎',label:'容易分心',desc:'注意力频繁离开任务'},{value:'fatigue',icon:'☾',label:'有些疲劳',desc:'当前精力不足以推进'}] as const
function release(item: typeof options[number]){block.value=item.value;if(!released.value.includes(item.value))released.value.push(item.value);if(!context.value)context.value=`当前感受：${item.label}`}
async function recover(acceptance?:boolean){busy.value=true;error.value='';try{result.value=await recoverLearning({user_id:session.userId,course:session.course,block_type:block.value,context:context.value,task_type:session.selectedTask?.task_type||'study',knowledge_point:session.selectedTask?.knowledge_point||session.knowledgePoint||undefined,...(acceptance===undefined?{}:{user_acceptance:acceptance})})}catch(e){error.value=errorMessage(e)}finally{busy.value=false}}
function apply(){applied.value=true;plans.localAdjustment=result.value?.action||'';if(session.selectedTask)plans.statuses[session.selectedTask.id]='deferred';recover(true)}
function reject(){applied.value=false;recover(false)}
</script>
<template><section><PageHeader eyebrow="THOUGHT NEBULA · RECOVERY" title="思绪星云与学习恢复" subtitle="主动释放当前阻塞，Flow Agent 再把它转成一个低压力恢复动作" />
  <div class="nebula card">
    <div class="nebula-copy"><span class="chip">仅学习状态支持</span><h2>此刻，什么正在挡住你？</h2><p>点击一颗星释放想法。它只作为你主动提供的学习信号，不进行情绪诊断。</p></div>
    <button v-for="(item,index) in options" :key="item.value" :class="[`star-${index}`,{active:block===item.value,released:released.includes(item.value)}]" @click="release(item)"><b>{{ item.icon }}</b><strong>{{ item.label }}</strong><small>{{ released.includes(item.value)?'已释放':item.desc }}</small></button>
    <div class="nebula-center">✦<small>{{ released.length ? `已释放 ${released.length} 个信号` : '点击星点' }}</small></div>
  </div>
  <div class="card panel context-form"><div><p class="eyebrow">主动反馈信号 · {{ options.find(item=>item.value===block)?.label }}</p><h2>把具体情况交给 Flow Agent</h2></div><div class="field"><label for="context">补充当前情况</label><textarea id="context" v-model="context" rows="3" placeholder="例如：今晚只剩 20 分钟，但这部分概念还没看懂。" /></div><button class="btn btn-primary" :disabled="busy" @click="recover()">生成一个低压力恢复动作 →</button></div>
  <LoadingState v-if="busy" text="正在结合阻塞类型与过往恢复经验…"/><ErrorNotice v-if="error" :message="error" @retry="recover()"/>
  <RecoveryAction v-if="result" :result="result" @accept="apply" @reject="reject"/>
  <div v-if="applied" class="notice success">方案已应用到当前浏览器会话；后端暂无任务状态更新接口，因此不会写入长期计划。</div>
  <div v-if="result" class="impact card panel"><div><p class="eyebrow">调整影响 · 会话演示</p><h2>应用后，计划会发生这些变化</h2></div><div class="grid-3"><div class="metric"><span>当前任务</span><strong>{{ session.selectedTask?.duration_minutes || 25 }} 分钟</strong><small class="muted">保留核心目标</small></div><div class="metric"><span>本次动作</span><strong>1 项</strong><small class="muted">来自真实恢复建议</small></div><div class="metric"><span>长期数据</span><strong>不写入</strong><small class="muted">仅本次浏览器会话</small></div></div></div>
</section></template>
<style scoped>
.nebula{position:relative;min-height:470px;overflow:hidden;margin-bottom:18px;background:radial-gradient(circle at 50% 48%,#393d88 0,#1b275c 42%,#0d173d 78%);border-color:#344077}.nebula:before,.nebula:after{content:"";position:absolute;inset:0;background-image:radial-gradient(#fff 1px,transparent 1px);background-size:34px 34px;opacity:.28}.nebula:after{background-size:71px 71px;transform:translate(13px,19px);opacity:.18}.nebula-copy{position:absolute;z-index:2;left:28px;top:26px;width:310px;color:white}.nebula-copy h2{margin:14px 0 7px}.nebula-copy p{font-size:12px;line-height:1.6;color:#cdd5ff}.nebula button{position:absolute;z-index:3;width:132px;min-height:78px;border:1px solid rgba(255,255,255,.28);border-radius:22px;padding:12px;background:rgba(255,255,255,.1);backdrop-filter:blur(10px);color:white;display:grid;gap:3px;text-align:left}.nebula button b{font-size:19px;color:#71e8f2}.nebula button small{font-size:9px;color:#cdd5ff;line-height:1.4}.nebula button.active{border-color:#72e9f4;background:linear-gradient(135deg,rgba(40,199,223,.55),rgba(118,87,246,.55));box-shadow:0 0 30px rgba(84,221,233,.35)}.nebula button.released{animation:release .55s ease}.star-0{left:8%;top:38%}.star-1{right:8%;top:31%}.star-2{left:15%;bottom:8%}.star-3{right:14%;bottom:10%}.nebula-center{position:absolute;z-index:2;left:50%;top:58%;transform:translate(-50%,-50%);width:92px;height:92px;border-radius:50%;display:grid;place-content:center;text-align:center;color:white;font-size:28px;background:radial-gradient(circle at 35% 25%,white,#45d5e4 22%,#7657f6 64%,#30206f);box-shadow:0 0 50px rgba(84,221,233,.45)}.nebula-center small{display:block;font-size:8px;margin-top:3px}.context-form{display:grid;gap:15px;margin-bottom:18px}.context-form h2{margin:4px 0}.impact{margin-top:18px}.impact h2{margin:4px 0 18px}@keyframes release{50%{transform:scale(1.07);filter:brightness(1.25)}}
@media(max-width:760px){.nebula{min-height:560px}.nebula-copy{width:auto;right:22px}.nebula button{width:120px}.star-0{left:7%;top:35%}.star-1{right:7%;top:35%}.star-2{left:7%;bottom:10%}.star-3{right:7%;bottom:10%}.nebula-center{top:60%}}
</style>
