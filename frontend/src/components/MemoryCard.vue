<script setup lang="ts">
import { ref } from 'vue'
import type { ConfirmationStatus, MemoryItem } from '../types'
import { memoryTypeLabels, statusLabels } from '../types'
const props = defineProps<{ memory: MemoryItem }>()
const emit = defineEmits<{ update: [status: ConfirmationStatus]; edit: [content: string]; remove: [] }>()
const editing = ref(false)
const content = ref(props.memory.content)
function save(){ emit('edit', content.value); editing.value = false }
</script>
<template>
  <article class="memory-card card">
<div class="row between"><span class="chip" :class="memory.confirmation_status">{{ statusLabels[memory.confirmation_status] }}</span><code class="id-button" :title="memory.id">#{{ memory.id.slice(0,8) }}</code></div>
    <p class="type">{{ memoryTypeLabels[memory.memory_type] }} · {{ memory.course }}</p>
    <textarea v-if="editing" v-model="content" rows="3" aria-label="编辑记忆内容" />
    <p v-else class="content">{{ memory.content }}</p>
    <div class="meta"><span>置信度 {{ Math.round(memory.confidence * 100) }}%</span><span>使用 {{ memory.use_count }} 次</span><span>{{ memory.knowledge_point || '通用偏好' }}</span></div>
    <div class="actions">
      <template v-if="editing"><button class="btn btn-primary" @click="save">保存</button><button class="btn" @click="editing=false">取消</button></template>
      <template v-else><button v-if="memory.confirmation_status==='pending'" class="btn btn-primary" @click="$emit('update','confirmed')">确认</button><button v-if="memory.confirmation_status==='pending'" class="btn" @click="$emit('update','rejected')">拒绝</button><button class="btn" @click="editing=true">编辑</button><button v-if="memory.confirmation_status!=='archived'" class="btn" @click="$emit('update','archived')">归档</button><button class="btn btn-danger" @click="$emit('remove')">删除</button></template>
    </div>
  </article>
</template>
<style scoped>
.memory-card{padding:19px;display:grid;gap:12px}.type{margin:0;color:var(--brand);font-size:12px;font-weight:800}.content{margin:0;line-height:1.65;font-weight:650}.meta{display:flex;gap:12px;flex-wrap:wrap;color:var(--muted);font-size:11px}.actions{display:flex;gap:8px;flex-wrap:wrap}.actions .btn{min-height:34px;padding:7px 12px;font-size:12px}.id-button{border:0;background:none;color:var(--muted);font-size:11px}.memory-card textarea{border:1px solid var(--border);border-radius:12px;padding:10px;color:var(--text);resize:vertical}.confirmed{background:#e9fbf5;color:var(--green)}.rejected{background:#fff0f3;color:#c45168}.archived{background:#f1f2f6;color:var(--muted)}
</style>
