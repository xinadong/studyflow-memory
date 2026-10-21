<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { MemoryEvidence, MemoryItem } from '../types'
import { memoryTypeLabels, statusLabels } from '../types'
import { getMemory } from '../services/memories'
import { errorMessage } from '../services/api'

const props = defineProps<{ retrieved?: string[]; used?: string[]; candidates?: string[]; evidence?: MemoryEvidence[]; compact?: boolean }>()
const usedRows = computed(() => props.evidence?.filter(item => item.decision === 'used') || [])
const unusedRows = computed(() => props.evidence?.filter(item => item.decision === 'retrieved_not_used') || [])
const pendingRows = computed(() => props.evidence?.filter(item => item.decision === 'pending') || [])
const opened = ref(false), loading = ref(false), error = ref('')
const snapshot = ref<MemoryItem | null>(null), current = ref<MemoryItem | null>(null)
const dialog = ref<HTMLElement | null>(null)
let request = 0, returnFocus: HTMLElement | null = null
function scopeLabel(memory: MemoryItem) {
  return memory.scope === 'global' ? '全局 · 所有课程' : memory.knowledge_point
    ? '知识点 · ' + memory.course + ' / ' + memory.knowledge_point : '课程 · ' + memory.course
}
async function openMemory(id: string, original?: MemoryItem) {
  const version = ++request
  if (!opened.value) returnFocus = document.activeElement as HTMLElement
  opened.value = true; loading.value = true; error.value = ''
  snapshot.value = original || null; current.value = null
  await nextTick()
  dialog.value?.focus()
  try {
    const value = await getMemory(id)
    if (version === request) current.value = value
  } catch (cause) { if (version === request) error.value = errorMessage(cause) }
  finally { if (version === request) loading.value = false }
}
function close() { opened.value = false; request++; returnFocus?.focus() }
function keepFocus(event: KeyboardEvent) {
  const buttons = dialog.value?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')
  if (!buttons?.length) return
  const first = buttons[0], last = buttons[buttons.length - 1]
  if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.value)) {
    event.preventDefault(); last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first.focus()
  }
}
</script>
<template>
  <section class="memory-reference" :class="{ compact }">
    <div class="reference-head"><div><p class="eyebrow">MEMORY TRACE</p><h3>本轮记忆使用依据</h3></div></div>
    <div class="trace-grid">
      <div><span class="trace-dot retrieved" /><strong>{{ retrieved?.length || 0 }}</strong><small>检索到</small></div>
      <div><span class="trace-dot used" /><strong>{{ used?.length || 0 }}</strong><small>实际使用</small></div>
      <div><span class="trace-dot candidate" /><strong>{{ candidates?.length || 0 }}</strong><small>待确认候选</small></div>
    </div>
    <div v-if="usedRows.length" class="evidence-used"><article v-for="row in usedRows" :key="row.memory.id"><span class="evidence-tag">实际采用 · {{ memoryTypeLabels[row.memory.memory_type] }}</span><p>{{ row.reason }}</p><button type="button" @click="openMemory(row.memory.id, row.memory)">查看原始记忆 →</button></article></div>
    <div v-else-if="used?.length" class="ids"><button v-for="id in used" :key="id" type="button" @click="openMemory(id)">已使用 · {{ id.slice(0, 8) }}</button></div>
    <p v-else class="trace-empty">本轮未采用长期记忆。无本次选择时，Agent 使用默认策略；有临时选择时以本次要求为准。</p>
    <details v-if="unusedRows.length" class="evidence-details"><summary>已检索但未采用 <span>{{ unusedRows.length }}</span></summary><article v-for="row in unusedRows" :key="row.memory.id"><p>{{ row.reason }}</p><button type="button" @click="openMemory(row.memory.id, row.memory)">{{ row.memory.content }} ↗</button></article></details>
    <details v-if="pendingRows.length" class="evidence-details"><summary>待确认，不影响本轮 <span>{{ pendingRows.length }}</span></summary><article v-for="row in pendingRows" :key="row.memory.id"><p>{{ row.reason }}</p><button type="button" @click="openMemory(row.memory.id, row.memory)">{{ row.memory.content }} ↗</button></article></details>
    <Teleport to="body"><div v-if="opened" class="memory-modal" @click.self="close" @keydown.esc.prevent="close" @keydown.tab="keepFocus"><section ref="dialog" class="memory-dialog" role="dialog" aria-modal="true" aria-label="原始记忆详情" tabindex="-1"><header><div><small>MEMORY SOURCE</small><h2>原始记忆</h2></div><button type="button" aria-label="关闭记忆详情" @click="close">×</button></header>
      <div v-if="snapshot" class="memory-snapshot"><b>本轮生成时引用的内容</b><blockquote>{{ snapshot.content }}</blockquote><p>{{ scopeLabel(snapshot) }}</p><div class="structured-values"><span v-if="snapshot.preferred_minutes">首选 {{ snapshot.preferred_minutes }} min</span><span v-if="snapshot.max_minutes">最多 {{ snapshot.max_minutes }} min</span></div></div>
      <p v-if="loading" class="detail-note" role="status">正在读取当前记录…</p><p v-if="error" class="detail-error" role="alert">当前记录读取失败：{{ error }}</p>
      <template v-if="current"><div class="memory-current"><b>当前记录 · {{ statusLabels[current.confirmation_status] }}{{ current.active ? '' : ' · 已删除' }}</b><blockquote>{{ current.content }}</blockquote><p>{{ scopeLabel(current) }}</p><div class="structured-values"><span v-if="current.preferred_minutes">首选 {{ current.preferred_minutes }} min</span><span v-if="current.max_minutes">最多 {{ current.max_minutes }} min</span></div><small>记忆编号 {{ current.id }}</small></div><p v-if="current.replaced_by_id" class="replacement-note">此版本已被新偏好替代。<button type="button" @click="openMemory(current!.replaced_by_id!)">查看替代版本 →</button></p></template>
      <p class="detail-note">这里保留生成时的引用快照；后续修改、归档不会改变当时的使用依据。</p>
    </section></div></Teleport>
  </section>
</template>
<style scoped>
.memory-reference{padding:20px;border-radius:22px;background:linear-gradient(145deg,#fff,#f7f7ff);border:1px solid #e4e7f6;min-width:0}.reference-head h3{margin:6px 0 0;font-size:14px;color:#3e4e79}.reference-head p{margin:0;color:#8b97ba;font-size:9px;letter-spacing:.08em}.trace-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:18px 0}.trace-grid>div{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:3px 6px;padding:9px 7px;border-radius:11px;background:#f1f4fc}.trace-grid strong{font-size:19px;color:#6379b1}.trace-grid small{grid-column:2;color:#8a98b8;font-size:9px}.trace-dot{grid-row:1/3;width:6px;height:6px;border-radius:50%}.retrieved{background:#70bdce}.used{background:#57ac8c}.candidate{background:#a28bd1}.evidence-used article{padding:12px;border-radius:12px;background:#edf8f4;margin-top:8px}.evidence-tag{color:#419776;font-size:10px}.evidence-used p{margin:7px 0 10px;font-size:11px;color:#527c70;line-height:1.85}.memory-reference button{border:0;background:transparent;padding:0;text-align:left;color:#7d85c4;font-size:10px;cursor:pointer;overflow-wrap:anywhere}.evidence-used button{color:#419776}.trace-empty{margin:0;font-size:10px;color:#8b99b8;line-height:1.9}.evidence-details{border-top:1px solid #e9edf6;margin-top:15px;padding-top:13px}.evidence-details summary{color:#7f8dac;font-size:10px;cursor:pointer;line-height:1.6}.evidence-details summary>span{margin-left:5px;color:#a3acc3}.evidence-details article{margin-top:12px;padding-left:10px;border-left:2px solid #e4e9f4}.evidence-details p{font-size:10px;line-height:1.8;color:#8f9cba;margin:0 0 6px}.ids{display:flex;gap:6px;flex-wrap:wrap}.ids button{padding:5px 8px;border-radius:8px;background:#edf8f4;color:#419776}.compact{box-shadow:none}.memory-modal{position:fixed;inset:0;z-index:2200;display:grid;place-items:center;padding:20px;background:#252f562e;backdrop-filter:blur(6px)}.memory-dialog{width:min(500px,100%);max-height:85vh;overflow:auto;padding:26px;border:1px solid #fff;border-radius:24px;background:#fff;box-shadow:0 25px 90px #25305e30;outline:none;color:#344671}.memory-dialog header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}.memory-dialog header small{font-size:9px;color:#98a3bf;letter-spacing:.1em}.memory-dialog h2{margin:7px 0 0;font-size:20px}.memory-dialog header>button{height:30px;width:30px;border:0;border-radius:10px;background:#f1f4fb;color:#8d9cbb;font-size:20px;cursor:pointer}.memory-snapshot,.memory-current{padding:15px;margin-bottom:13px;border:1px solid #e7ebf6;border-radius:14px;background:#f8faff}.memory-snapshot>b,.memory-current>b{font-size:11px;color:#7886ae}.memory-dialog blockquote{margin:12px 0;font-size:13px;line-height:1.9;color:#51678e;white-space:pre-wrap;overflow-wrap:anywhere}.memory-dialog p{font-size:10px;color:#8c9bb9;line-height:1.9}.memory-current>small{display:block;margin-top:13px;font-size:9px;color:#a1acc3;overflow-wrap:anywhere}.structured-values{display:flex;gap:7px;margin-top:10px;flex-wrap:wrap}.structured-values span{padding:5px 8px;border-radius:7px;background:#edecfc;color:#8472bd;font-size:10px}.detail-note{margin:14px 0 0}.memory-dialog .detail-error{color:#ba6c77}.replacement-note{padding:11px;border-radius:10px;background:#f6f2fb}.replacement-note button{border:0;background:transparent;color:#8d74ba;font-size:10px;cursor:pointer}.memory-reference button:focus-visible,.memory-dialog button:focus-visible{outline:2px solid #a1a5e3;outline-offset:4px}
</style>
