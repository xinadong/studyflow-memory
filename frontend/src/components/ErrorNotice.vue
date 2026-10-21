<script setup lang="ts">
defineProps<{ message: string }>()
defineEmits<{ retry: [] }>()
</script>
<template><div class="notice error row between" role="alert"><span>{{ message }}</span><button class="link-button" @click="$emit('retry')">重试</button></div></template>
