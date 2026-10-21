<script setup lang="ts">
defineProps<{ preferred: number | null; maximum: number | null; disabled?: boolean }>()
const emit = defineEmits<{ 'update:preferred': [value: number | null]; 'update:maximum': [value: number | null] }>()
function value(event: Event) {
  const input = event.target as HTMLInputElement
  return input.value === '' ? null : input.valueAsNumber
}
</script>
<template>
  <div class="duration-fields">
    <label>首选时长<span><input type="number" min="1" max="240" step="1" :disabled="disabled" :value="preferred" placeholder="例如：15" aria-label="首选时长（分钟）" @input="emit('update:preferred', value($event))" /><small>min</small></span></label>
    <label>最多时长<span><input type="number" min="1" max="240" step="1" :disabled="disabled" :value="maximum" placeholder="例如：30" aria-label="最多时长（分钟）" @input="emit('update:maximum', value($event))" /><small>min</small></span></label>
    <p>两项均可选。填写后以这些数值为准；“最多”只限制上限，不代表必须排满。</p>
  </div>
</template>
<style scoped>
.duration-fields{display:grid;grid-template-columns:1fr 1fr;gap:10px 14px;min-width:0}.duration-fields>label{display:grid;gap:7px;color:#687ba2;font-size:11px}.duration-fields label>span{position:relative;display:block;min-width:0}.duration-fields input{width:100%;min-width:0;height:36px;padding:0 48px 0 11px;border:1px solid #dfe5f5;border-radius:10px;background:#fff;color:#435c83;font:inherit}.duration-fields small{position:absolute;right:23px;top:50%;transform:translateY(-50%);font-size:10px;color:#94a0bc;pointer-events:none}.duration-fields p{grid-column:1/-1;margin:0!important;font-size:10px!important;color:#8392b0!important;line-height:1.8}.duration-fields input:focus{outline:2px solid #c4c9f0;outline-offset:1px}
</style>
