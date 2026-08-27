<script setup lang="ts">
defineProps<{ retrieved?: string[]; used?: string[]; candidates?: string[]; compact?: boolean }>()
</script>
<template>
  <section class="memory-reference" :class="{ compact }">
    <div class="reference-head"><div><p class="eyebrow">MEMORY TRACE</p><h3>本轮反馈记忆依据</h3></div><span>可解释使用</span></div>
    <div class="trace-grid">
      <div><span class="trace-dot retrieved" /><strong>{{ retrieved?.length || 0 }}</strong><small>检索到</small></div>
      <div><span class="trace-dot used" /><strong>{{ used?.length || 0 }}</strong><small>实际使用</small></div>
      <div><span class="trace-dot candidate" /><strong>{{ candidates?.length || 0 }}</strong><small>待确认候选</small></div>
    </div>
    <div v-if="used?.length" class="ids"><span v-for="id in used" :key="id">已使用 · {{ id.slice(0, 8) }}</span></div>
    <p v-else class="muted small">本轮没有已确认记忆影响结果，Agent 使用默认策略。</p>
  </section>
</template>
<style scoped>
.memory-reference{padding:20px;border-radius:22px;background:linear-gradient(145deg,#fff,#f0f1ff);border:1px solid #dedcff}.reference-head{display:flex;align-items:center;justify-content:space-between}.reference-head h3{margin:3px 0 0}.reference-head p{margin:0}.reference-head>span{font-size:12px;color:var(--brand);font-weight:800}.trace-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:18px 0}.trace-grid>div{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:3px 7px;padding:11px;border-radius:14px;background:rgba(255,255,255,.72)}.trace-grid strong{font-size:18px}.trace-grid small{grid-column:2;color:var(--muted);font-size:9px}.trace-dot{grid-row:1/3;width:9px;height:9px;border-radius:50%}.retrieved{background:var(--cyan)}.used{background:var(--green)}.candidate{background:var(--violet)}.ids{display:flex;gap:6px;flex-wrap:wrap}.ids span{font-size:10px;padding:5px 8px;border-radius:999px;background:#e9fbf5;color:var(--green)}.compact{box-shadow:none}
@media(max-width:520px){.trace-grid{grid-template-columns:1fr}.trace-grid>div{grid-template-columns:auto auto 1fr}.trace-grid small{grid-column:auto}}
</style>
