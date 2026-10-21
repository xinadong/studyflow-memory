<script setup lang="ts">
import AppShell from './components/AppShell.vue'
import LoginView from './views/LoginView.vue'
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <LoginView v-if="route.meta.public" />
  <AppShell v-else />
</template>
