import type {
  StatsReport,
  CostSummary,
  TraceSummary,
  KBQualityReport,
  ChatRequest,
  ChatResponse,
  FeedbackRequest,
  FeedbackAck,
  LoginResponse,
  User,
  SecurityReport,
  CacheStats,
  MemoryStatus,
  RateLimitStatus,
  HealthCheck,
  PaginatedResponse,
  ProblemDetail,
} from '../types'

const API_BASE = '/api/v1'

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

class ApiError extends Error {
  status: number
  detail?: ProblemDetail

  constructor(status: number, detail?: ProblemDetail) {
    super(detail?.title || `API Error: ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const isMutating = options?.method === 'POST' || options?.method === 'PUT' || options?.method === 'PATCH' || options?.method === 'DELETE'
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    ...(options?.headers as Record<string, string> | undefined),
  }
  if (isMutating) {
    const csrf = getCsrfToken()
    if (csrf) headers['X-CSRF-Token'] = csrf
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    credentials: 'include',
    headers,
  })

  if (!res.ok) {
    let detail: ProblemDetail | undefined
    try {
      detail = await res.json()
    } catch {
      // non-JSON error
    }
    throw new ApiError(res.status, detail)
  }

  return res.json()
}

function sanitizeInput(input: string): string {
  return input.replace(/<[^>]*>/g, '').trim()
}

export { ApiError }

export const api = {
  auth: {
    login: (username: string, password: string) =>
      fetchApi<LoginResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username: sanitizeInput(username), password }),
      }),
    logout: () =>
      fetchApi<LoginResponse>('/auth/logout', { method: 'POST' }),
    me: () => fetchApi<User>('/auth/me'),
  },

  stats: {
    get: () => fetchApi<StatsReport>('/stats'),
    costs: (conversation_id?: string) =>
      fetchApi<CostSummary>(`/costs${conversation_id ? `?conversation_id=${encodeURIComponent(conversation_id)}` : ''}`),
  },

  traces: {
    list: (limit = 50, offset = 0) =>
      fetchApi<PaginatedResponse<TraceSummary>>(
        `/traces?limit=${limit}&offset=${offset}`
      ),
    get: (sessionId: string) => fetchApi<TraceSummary>(`/traces/${encodeURIComponent(sessionId)}`),
  },

  kb: {
    quality: () => fetchApi<KBQualityReport>('/kb-quality'),
  },

  chat: {
    send: (data: ChatRequest) =>
      fetchApi<ChatResponse>('/chat', {
        method: 'POST',
        body: JSON.stringify({ ...data, message: sanitizeInput(data.message) }),
      }),
  },

  feedback: {
    submit: (data: FeedbackRequest) =>
      fetchApi<FeedbackAck>('/feedback', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  },

  admin: {
    security: () => fetchApi<SecurityReport>('/admin/security/report'),
    cache: () => fetchApi<CacheStats>('/admin/cache/stats'),
    cacheClear: () => fetchApi<{ cleared: number }>('/admin/cache/clear', { method: 'POST' }),
    memory: () => fetchApi<MemoryStatus>('/admin/memory/status'),
    memoryCleanup: () => fetchApi<{ freed_mb: number }>('/admin/memory/cleanup', { method: 'POST' }),
    sessions: () => fetchApi<{ active: number; sessions: Array<{ username: string; created_at: string }> }>('/admin/sessions'),
    rateLimit: () => fetchApi<RateLimitStatus>('/admin/rate-limit'),
    tier: () => fetchApi<Record<string, { rate_limit: number; features: string[] }>>('/admin/tier'),
  },

  health: () => fetchApi<HealthCheck>('/health'),
}
