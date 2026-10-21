<script setup lang="ts">
import type { MemoryScope, PreferencePersistence } from '../types'
withDefaults(defineProps<{ persistence: PreferencePersistence; scope: MemoryScope; course?: string; knowledgePoint?: string; disabled?: boolean; showPersistence?: boolean }>(), { showPersistence: true })
defineEmits<{ 'update:persistence': [value: PreferencePersistence]; 'update:scope': [value: MemoryScope] }>()
</script>
<template>
  <div class="preference-options">
    <div v-if="showPersistence !== false" class="preference-lifetime" role="group" aria-label="偏好使用方式">
      <button type="button" :disabled="disabled" :aria-pressed="persistence === 'once'" :class="{ selected: persistence === 'once' }" @click="$emit('update:persistence', 'once')">仅本次使用</button>
      <button type="button" :disabled="disabled" :aria-pressed="persistence === 'long_term'" :class="{ selected: persistence === 'long_term' }" @click="$emit('update:persistence', 'long_term')">保存为长期偏好</button>
    </div>
    <template v-if="persistence === 'long_term'">
      <label class="preference-scope">适用范围<select :disabled="disabled" :value="scope" @change="$emit('update:scope', ($event.target as HTMLSelectElement).value as MemoryScope)"><option value="global">全局 · 所有课程</option><option value="course">课程 · {{ course || '请先填写课程' }}</option><option value="knowledge_point">知识点 · {{ knowledgePoint || '请先填写知识点' }}</option></select></label>
      <p v-if="scope === 'global'">将在其他课程与知识点中复用；更具体的偏好优先。</p>
      <p v-else-if="scope === 'course'">{{ course ? '仅在「' + course + '」课程中复用。' : '请先填写适用课程。' }}</p>
      <p v-else>{{ course && knowledgePoint ? '仅在「' + course + ' / ' + knowledgePoint + '」中复用。' : '请先填写课程和知识点。' }}</p>
    </template>
    <p v-else>只影响本次安排，不写入长期记忆。</p>
  </div>
</template>
<style scoped>
.preference-options{display:grid;gap:10px;min-width:0}.preference-lifetime{display:flex;flex-wrap:wrap;gap:6px;width:fit-content;padding:4px;border:1px solid #e4e8f5;border-radius:12px;background:#f3f5fc}.preference-lifetime button{min-height:30px;height:auto;padding:7px 12px;border:0;border-radius:9px;background:transparent;color:#7a89ad;font-size:11px;font-weight:500;line-height:1.5}.preference-lifetime button.selected{background:#fff;color:#6866cc;font-weight:700;box-shadow:0 2px 7px #5267b014}.preference-scope{display:flex;align-items:center;gap:12px;color:#7586a8;font-size:11px}.preference-scope select{max-width:100%;min-width:0;padding:8px 10px;border:1px solid #dfe5f5;border-radius:10px;background:#fff;color:#536b95;font:inherit}.preference-options p{margin:0!important;color:#8392b0!important;font-size:10px!important;line-height:1.8}.preference-lifetime button:focus-visible,.preference-scope select:focus-visible{outline:2px solid #9a9fe6;outline-offset:2px}
</style>
