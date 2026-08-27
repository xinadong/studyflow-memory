import { apiRequest } from './api'
import type { EvaluationResponse, MetricsResponse, PlanRequest } from '../types'

export const comparePlans = (payload: PlanRequest) => apiRequest<EvaluationResponse>('/evaluation/compare', {
  method: 'POST', body: JSON.stringify(payload),
})
export const getMetrics = () => apiRequest<MetricsResponse>('/metrics')
