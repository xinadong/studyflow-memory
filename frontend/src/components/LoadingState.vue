<script setup lang="ts">
defineProps<{ text?: string }>()
</script>
<template><div class="loading" aria-live="polite"><span /><strong>{{ text || 'Flow Agent 正在思考…' }}</strong></div></template>
<style scoped>
.loading { display:flex; align-items:center; gap:12px; padding:18px; border-radius:18px; color:var(--brand); background:#eef2ff; }
.loading span { width:20px; height:20px; border:3px solid #cbd3ff; border-top-color:var(--brand); border-radius:50%; animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg) } }
</style>
