export type MemoryType =
  | 'task_preference'
  | 'explanation_preference'
  | 'knowledge_state'
  | 'recovery_experience'
  | 'review_schedule'

export type ConfirmationStatus = 'pending' | 'confirmed' | 'rejected' | 'archived'
export type BlockType = 'time' | 'too_hard' | 'distraction' | 'fatigue'
export type UnderstandingLevel = 'recall' | 'relate' | 'transfer'
export type TaskStatus = 'pending' | 'active' | 'completed' | 'deferred'

export interface Task {
  id: string
  course?: string
  title: string
  description: string
  duration_minutes: number
  task_type: string
  knowledge_point?: string | null
  due_at?: string | null
}

export interface ImportedTaskConstraint { title: string; due_at: string }

export interface MemoryTrace {
  retrieved_memory_ids: string[]
  used_memory_ids: string[]
  candidate_memory_ids: string[]
}

export interface PlanRequest {
  user_id: string
  course: string
  goal: string
  available_minutes: number
  task_type: string
  knowledge_point?: string
  imported_tasks?: ImportedTaskConstraint[]
}

export interface PlanResponse extends MemoryTrace {
  tasks: Task[]
  explanation: string
  metrics: Record<string, number>
}

export interface UnderstandingCheckRequest {
  user_id: string
  course: string
  knowledge_point: string
  task_type: string
  material: string
  level: UnderstandingLevel
  answer?: string
  conversation_history?: Array<{ role: 'user' | 'assistant'; content: string }>
  hint_preference?: 'example' | 'definition' | 'analogy' | 'diagram'
  guidance_request?: 'full_answer'
}

export interface UnderstandingCheckResponse extends MemoryTrace {
  level: string
  assessed_level?: string | null
  question: string
  feedback: string
  missing_dimensions: string[]
  guidance_type: 'question' | 'hint' | 'correction' | 'full_answer' | 'encouragement'
  mastery_status: 'ongoing' | 'ready'
  visual_steps: string[]
  mastery_summary?: string | null
  review_recommendation?: ReviewRecommendation | null
  metrics: Record<string, number>
}

export interface ReviewRecommendation {
  due_date: string
  duration_minutes: number
  reason: string
}

export interface RecoveryRequest {
  user_id: string
  course: string
  block_type: BlockType
  context: string
  task_type: string
  knowledge_point?: string
  user_acceptance?: boolean
}

export interface RecoveryResponse extends MemoryTrace {
  action: string
  reason: string
  metrics: Record<string, number>
}

export interface MemoryItem {
  id: string
  user_id: string
  memory_type: MemoryType
  course: string
  task_type?: string | null
  knowledge_point?: string | null
  block_type?: BlockType | null
  content: string
  source_feedback?: string | null
  confidence: number
  confirmation_status: ConfirmationStatus
  created_at: string
  last_used_at?: string | null
  use_count: number
  active: boolean
}

export interface MemoryList { items: MemoryItem[]; total: number }

export interface FeedbackRequest {
  user_id: string
  course: string
  feedback_type?: MemoryType
  content: string
  explicit?: boolean
  task_type?: string
  knowledge_point?: string
  block_type?: BlockType
}

export interface FeedbackResponse { feedback_id: string; memories: MemoryItem[] }

export interface EvaluationResponse {
  without_memory: PlanResponse
  with_memory: PlanResponse
  delta: Record<string, number | string>
}

export interface MetricsResponse {
  agent_runs: number
  success_count: number
  failure_count: number
  input_tokens: number
  output_tokens: number
  memory_tokens: number
  retry_count: number
  format_repair_count: number
  retrieval_latency_ms_percentiles: { p50: number; p95: number }
  model_latency_ms_percentiles: { p50: number; p95: number }
  memory_counts: { retrieved: number; used: number; candidate: number }
  models: string[]
  runs: Array<Record<string, unknown>>
  errors: Array<Record<string, unknown>>
}

export const memoryTypeLabels: Record<MemoryType, string> = {
  task_preference: '任务偏好',
  explanation_preference: '解释偏好',
  knowledge_state: '知识状态',
  recovery_experience: '恢复经验',
  review_schedule: '复习计划',
}

export const statusLabels: Record<ConfirmationStatus, string> = {
  pending: '待确认', confirmed: '已确认', rejected: '已拒绝', archived: '已归档',
}
