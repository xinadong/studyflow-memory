export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export interface ApiErrorShape {
  status: number
  code: string
  message: string
  retryCount?: number
  fieldErrors?: Record<string, string[]>
}

const messages: Record<string, string> = {
  model_not_configured: '模型尚未配置，请联系演示人员。',
  provider_timeout: '模型响应超时，请稍后重试。',
  provider_unavailable: '模型服务暂时不可用，请稍后重试。',
  provider_rejected: '模型服务拒绝了本次请求。',
  invalid_model_output: '模型返回格式异常，请重新生成。',
  invalid_tool_arguments: 'Agent 工具参数校验失败。',
  unknown_tool: 'Agent 调用了未授权工具。',
}

export class ApiError extends Error implements ApiErrorShape {
  status: number
  code: string
  retryCount?: number
  fieldErrors?: Record<string, string[]>

  constructor(data: ApiErrorShape) {
    super(data.message)
    this.name = 'ApiError'
    this.status = data.status
    this.code = data.code
    this.retryCount = data.retryCount
    this.fieldErrors = data.fieldErrors
  }
}

export async function apiRequest<T>(path: string, options: RequestInit = {}, timeoutMs = 125_000): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
      signal: controller.signal,
    })
    if (response.status === 204) return undefined as T
    const body = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = body?.detail
      const code = typeof detail === 'object' ? detail.code : `http_${response.status}`
      const rawMessage = typeof detail === 'object' ? detail.message : detail
      throw new ApiError({
        status: response.status,
        code,
        message: messages[code] ?? rawMessage ?? `请求失败（${response.status}）`,
        retryCount: typeof detail === 'object' ? detail.retry_count : undefined,
        fieldErrors: response.status === 422 && Array.isArray(detail)
          ? detail.reduce((acc: Record<string, string[]>, item: { loc?: string[]; msg?: string }) => {
              const key = item.loc?.at(-1) ?? 'form'
              ;(acc[key] ??= []).push(item.msg ?? '字段无效')
              return acc
            }, {})
          : undefined,
      })
    }
    return body as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError({ status: 0, code: 'request_timeout', message: '请求等待时间过长，请重试。' })
    }
    throw new ApiError({ status: 0, code: 'network_error', message: `无法连接后端服务（${API_BASE_URL}）。` })
  } finally {
    window.clearTimeout(timer)
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '发生未知错误。'
}
