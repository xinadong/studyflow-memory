import { apiRequest } from './api'
import type {
  PlanRequest, PlanResponse, RecoveryRequest, RecoveryResponse,
  UnderstandingCheckRequest, UnderstandingCheckResponse,
} from '../types'

const post = <T>(path: string, body: unknown) => apiRequest<T>(path, { method: 'POST', body: JSON.stringify(body) })

export const createPlan = (payload: PlanRequest) => post<PlanResponse>('/agent/plan', payload)
export const checkUnderstanding = (payload: UnderstandingCheckRequest) => post<UnderstandingCheckResponse>('/agent/check', payload)
export const recoverLearning = (payload: RecoveryRequest) => post<RecoveryResponse>('/agent/recover', payload)
