<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ConfirmationStatus, MemoryItem } from '../types'
import DurationFields from './DurationFields.vue'
import { memoryTypeLabels, statusLabels } from '../types'
const props = defineProps<{ memory: MemoryItem }>()
const emit = defineEmits<{ update: [status: ConfirmationStatus]; edit: [payload: Partial<MemoryItem>]; remove: [] }>()
const editing = ref(false)
const content = ref(props.memory.content)
const scopeLabel = computed(() => {
  const scope = props.memory.scope || (props.memory.knowledge_point ? 'knowledge_point' : 'course')
  return scope === 'global' ? '全局 · 所有课程' : scope === 'course'
    ? '课程 · ' + props.memory.course : '知识点 · ' + props.memory.course + ' / ' + props.memory.knowledge_point
})
const preferred = ref<number|null>(props.memory.preferred_minutes ?? null)
const maximum = ref<number|null>(props.memory.max_minutes ?? null)
const editError = ref('')
function save(){
  if(preferred.value && maximum.value && preferred.value > maximum.value){ editError.value='首选时长不能超过最多时长。';return }
  editError.value=''
  const numericChanged=preferred.value!==(props.memory.preferred_minutes??null)||maximum.value!==(props.memory.max_minutes??null)
  emit('edit', {content:content.value,...(props.memory.memory_type==='task_preference'&&numericChanged?{preferred_minutes:preferred.value,max_minutes:maximum.value}:{})})
  editing.value = false
}
</script>
<template>
  <article class="memory-card card">
<div class="row between"><span class="chip" :class="memory.confirmation_status">{{ statusLabels[memory.confirmation_status] }}</span><code class="id-button" :title="memory.id">#{{ memory.id.slice(0,8) }}</code></div>
    <p class="type">{{ memoryTypeLabels[memory.memory_type] }}</p>
    <textarea v-if="editing" v-model="content" rows="3" aria-label="编辑记忆内容" />
    <DurationFields v-if="editing && memory.memory_type==='task_preference'" v-model:preferred="preferred" v-model:maximum="maximum" />
    <p v-if="editing && editError" class="edit-error" role="alert">{{ editError }}</p>
    <p v-if="!editing" class="content">{{ memory.content }}</p>
    <p v-if="memory.memory_type==='task_preference'" class="duration-summary"><span v-if="memory.preferred_minutes">首选 {{ memory.preferred_minutes }} min</span><span v-if="memory.max_minutes">最多 {{ memory.max_minutes }} min</span><span v-if="!memory.preferred_minutes && !memory.max_minutes">时长未明确，可编辑补充</span></p>
    <p v-if="memory.replaced_by_id" class="scope-label">此版本已被新偏好替代，保留用于回溯。</p>
    <p class="scope-label">{{ scopeLabel }}</p>
    <div class="meta"><span>置信度 {{ Math.round(memory.confidence * 100) }}%</span><span>使用 {{ memory.use_count }} 次</span></div>
    <div class="actions">
      <template v-if="editing"><button class="btn btn-primary" @click="save">保存</button><button class="btn" @click="editing=false">取消</button></template>
      <template v-else><button v-if="memory.confirmation_status==='pending'" class="btn btn-primary" @click="$emit('update','confirmed')">确认</button><button v-if="memory.confirmation_status==='pending'" class="btn" @click="$emit('update','rejected')">拒绝</button><button class="btn" @click="editing=true">编辑</button><button v-if="memory.confirmation_status!=='archived'" class="btn" @click="$emit('update','archived')">归档</button><button class="btn btn-danger" @click="$emit('remove')">删除</button></template>
    </div>
  </article>
</template>
<style scoped>
.edit-error{margin:0;font-size:11px;color:#bc6678}
.duration-summary{display:flex;gap:8px;flex-wrap:wrap;margin:0;font-size:11px;color:#6866bd}.duration-summary span{padding:5px 8px;border-radius:7px;background:#eeedfc}

.scope-label{margin:0;padding:7px 9px;border-radius:8px;background:#f5f6fd;color:#7886aa;font-size:10px;line-height:1.6}

.memory-card{padding:19px;display:grid;gap:12px}.type{margin:0;color:var(--brand);font-size:12px;font-weight:800}.content{margin:0;line-height:1.65;font-weight:650}.meta{display:flex;gap:12px;flex-wrap:wrap;color:var(--muted);font-size:11px}.actions{display:flex;gap:8px;flex-wrap:wrap}.actions .btn{min-height:34px;padding:7px 12px;font-size:12px}.id-button{border:0;background:none;color:var(--muted);font-size:11px}.memory-card textarea{border:1px solid var(--border);border-radius:12px;padding:10px;color:var(--text);resize:vertical}.confirmed{background:#e9fbf5;color:var(--green)}.rejected{background:#fff0f3;color:#c45168}.archived{background:#f1f2f6;color:var(--muted)}
</style>
