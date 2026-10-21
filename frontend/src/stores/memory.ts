import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { MemoryItem } from '../types'

export const useMemoryStore = defineStore('memory', () => {
  const items = ref<MemoryItem[]>([])
  const pendingCount = computed(() => items.value.filter(item => item.confirmation_status === 'pending').length)
  return { items, pendingCount }
})
