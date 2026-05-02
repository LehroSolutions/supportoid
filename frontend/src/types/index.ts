export interface User {
  username: string
  role: "admin" | "analyst" | "support"
}

export interface LoginResponse {
  ok: boolean
  user: User | null
  message: string
}

export interface StatsReport {
  total_processed: number
  escalations: number
  active_sessions: number
  traces: number
  version: string
  model_version: number
  model_accuracy: number
  avg_confidence: number
  avg_quality: number
  knowledge_entries: number
  feedback_records: number
  cache_hit_rate: number
  errors: number
  costs: CostSummary
}

export interface CostSummary {
  conversation_id: string | null
  total_conversations: number
  total_cost_usd: number
  total_calls: number
  total_input_tokens: number
  total_output_tokens: number
  calls_by_model: Record<string, number>
  cost_by_model: Record<string, number>
}

export interface TraceSummary {
  session_id: string
  duration_s: number
  steps: number
  escalated: boolean
  error: string | null
  user_input: string
  summary: string
}

export interface KBQualityReport {
  total_entries: number
  overall_avg: number
  report_generated: string | null
  grade_distribution: Record<string, number>
  dimension_averages: Record<string, number>
  top_entries: Record<string, unknown>
  needs_attention: Record<string, unknown>
}

export interface ChatRequest {
  message: string
  conversation_id?: string
  user_id?: string
  tier?: string
}

export interface ChatResponse {
  conversation_id: string
  response: string
  intent: string
  confidence: number
  sentiment: number
  urgency: number
  tone: string
  quality_score: number
  should_escalate: boolean
  escalation_reason: string
  source: string
  kb_results_used: number
  suggested_actions: string[]
  processing_time_ms: number
  role: "admin" | "analyst" | "support"
  timestamp: string
}

export interface FeedbackRequest {
  conversation_id: string
  rating: number
  feedback_text?: string
  corrected_intent?: string
}

export interface FeedbackAck {
  status: "recorded" | "rejected"
  conversation_id: string
  rating: number
  retrain: Record<string, unknown> | null
  message: string
}

export interface ProblemDetail {
  type: string
  title: string
  status: number
  detail: string
  instance?: string
  request_id?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface SecurityReport {
  auth_failures_24h: number
  rate_limit_hits_24h: number
  active_sessions: number
  total_sessions: number
  suspicious_ips: string[]
}

export interface CacheStats {
  total_entries: number
  hit_rate: number
  miss_rate: number
  evictions: number
  memory_usage_mb: number
}

export interface MemoryStatus {
  rss_mb: number
  heap_mb: number
  gc_collections: number
  optimization_available: boolean
}

export interface RateLimitStatus {
  active_limits: Record<string, { current: number; limit: number; reset_at: string }>
  global_enabled: boolean
}

export interface HealthCheck {
  status: "healthy" | "degraded" | "unhealthy"
  service: string
  version: string
  uptime_seconds: number
  checks: Record<string, { ok: boolean; latency_ms: number; detail?: string }>
}
