<script setup lang="ts">
defineProps<{ eyebrow?: string; title: string; subtitle?: string }>()
</script>
<template><header class="page-header"><div><p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p><h1>{{ title }}</h1><p v-if="subtitle" class="muted">{{ subtitle }}</p></div><slot /></header></template>
<style scoped>
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 24px; }
h1 { margin: 4px 0 8px; font-size: clamp(27px, 3vw, 38px); line-height: 1.2; }
p { margin-bottom: 0; }
@media(max-width:760px){.page-header{display:grid} h1{font-size:27px}}
</style>
