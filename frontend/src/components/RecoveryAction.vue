<script setup lang="ts">
import type { RecoveryResponse } from '../types'
import MemoryReference from './MemoryReference.vue'
defineProps<{ result: RecoveryResponse }>()
defineEmits<{ accept: []; reject: [] }>()
</script>
<template><article class="recovery-result card panel"><span class="chip pending">Flow Agent 建议</span><h2>{{ result.action }}</h2><p>{{ result.reason }}</p><MemoryReference :retrieved="result.retrieved_memory_ids" :used="result.used_memory_ids" :candidates="result.candidate_memory_ids" compact/><div class="row"><button class="btn btn-primary" @click="$emit('accept')">确认应用方案 →</button><button class="btn btn-secondary" @click="$emit('reject')">暂不调整</button></div></article></template>
<style scoped>.recovery-result{display:grid;gap:17px}.recovery-result h2,.recovery-result p{margin:0}.recovery-result p{line-height:1.7;color:var(--muted)}@media(max-width:520px){.recovery-result .row{display:grid}.recovery-result .btn{width:100%}}</style>
