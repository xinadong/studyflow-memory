import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { ReviewRecommendation, Task, UnderstandingLevel } from '../types'

export interface TutorConfig {
  course: string
  knowledgePoint: string
  taskType: string
  level: UnderstandingLevel
  material: string
  task: Task | null
}

export interface TutorMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  guidanceType?: 'question' | 'hint' | 'correction' | 'full_answer' | 'encouragement'
  missingDimensions?: string[]
  hintChoices?: boolean
  visualSteps?: string[]
}

const savedConfig = sessionStorage.getItem('studyflow-tutor-config')
const savedMessages = sessionStorage.getItem('studyflow-tutor-messages')

export const useTutorStore = defineStore('tutor', () => {
  const config = ref<TutorConfig | null>(savedConfig ? JSON.parse(savedConfig) : null)
  const messages = ref<TutorMessage[]>(savedMessages ? JSON.parse(savedMessages) : [])
  const masteryStatus = ref<'ongoing' | 'ready'>('ongoing')
  const masterySummary = ref('')
  const reviewRecommendation = ref<ReviewRecommendation | null>(null)

  watch(config, value => value
    ? sessionStorage.setItem('studyflow-tutor-config', JSON.stringify(value))
    : sessionStorage.removeItem('studyflow-tutor-config'), { deep: true })
  watch(messages, value => sessionStorage.setItem('studyflow-tutor-messages', JSON.stringify(value)), { deep: true })

  function start(value: TutorConfig) {
    config.value = value
    messages.value = []
    masteryStatus.value = 'ongoing'
    masterySummary.value = ''
    reviewRecommendation.value = null
  }
  function addMessage(message: Omit<TutorMessage, 'id'>) {
    messages.value.push({ ...message, id: `${Date.now()}-${messages.value.length}` })
  }
  function clear() {
    config.value = null
    messages.value = []
    masteryStatus.value = 'ongoing'
    masterySummary.value = ''
    reviewRecommendation.value = null
  }
  return { config, messages, masteryStatus, masterySummary, reviewRecommendation, start, addMessage, clear }
})
