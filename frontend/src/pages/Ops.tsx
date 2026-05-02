import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import MagneticButton from '../components/shared/MagneticButton'
import { CardSkeleton } from '../components/shared/Skeleton'
import { containerVariants, springConfig, cn, formatPercent, formatNumber } from '../lib/utils'
import { useAuth } from '../hooks/useAuth'
import {
  Shield, Database, HardDrive, Users, Gauge, Trash2,
  RefreshCw, Activity, Server, AlertTriangle, Clock,
  Cpu, MemoryStick, Zap, Lock, Eye,
} from 'lucide-react'
import type {
  SecurityReport,
  CacheStats,
  MemoryStatus,
  RateLimitStatus,
  HealthCheck,
} from '../types'

function MetricTile({
  icon: Icon,
  label,
  value,
  sub,
  accent,
  delay = 0,
}: {
  icon: React.ElementType
  label: string
  value: string | number
  sub?: string
  accent?: boolean
  delay?: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...springConfig, delay }}
      className="bento-card p-4 space-y-2"
    >
      <div className="flex items-center gap-2">
        <Icon className={cn('w-3.5 h-3.5', accent ? 'text-accent' : 'text-muted-foreground')} />
        <span className="text-[11px] font-mono uppercase tracking-wider text-muted-foreground">{label}</span>
      </div>
      <div className={cn('text-2xl font-semibold tabular-nums tracking-tight', accent && 'text-accent')}>
        {value}
      </div>
      {sub && <span className="text-[11px] font-mono text-muted-foreground/70">{sub}</span>}
    </motion.div>
  )
}

function ActionCard({
  title,
  description,
  icon: Icon,
  mutationFn,
  queryKeyToInvalidate,
  successKey,
  delay = 0,
}: {
  title: string
  description: string
  icon: React.ElementType
  mutationFn: () => Promise<Record<string, number>>
  queryKeyToInvalidate: string
  successKey: string
  delay?: number
}) {
  const qc = useQueryClient()
  const [result, setResult] = useState<number | null>(null)

  const mutation = useMutation({
    mutationFn,
    onSuccess: (data) => {
      setResult(data[successKey] ?? 0)
      qc.invalidateQueries({ queryKey: [queryKeyToInvalidate] })
      setTimeout(() => setResult(null), 3000)
    },
  })

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...springConfig, delay }}
      className="bento-card p-5 space-y-3"
    >
      <div className="flex items-center gap-2.5">
        <motion.div whileHover={{ rotate: 180 }} transition={{ duration: 0.4 }} className="p-2 bg-accent/10 rounded-lg">
          <Icon className="w-4 h-4 text-accent" />
        </motion.div>
        <h3 className="text-sm font-serif text-foreground">{title}</h3>
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
      <div className="flex items-center gap-3">
        <MagneticButton
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="px-4 py-2 text-xs font-mono rounded-lg bg-accent/15 text-accent hover:bg-accent/25 transition-colors"
        >
          {mutation.isPending ? (
            <span className="flex items-center gap-1.5">
              <RefreshCw className="w-3 h-3 animate-spin" /> Running
            </span>
          ) : (
            'Execute'
          )}
        </MagneticButton>
        <AnimatePresence>
          {result !== null && (
            <motion.span
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              className="text-xs font-mono text-success"
            >
              {successKey === 'cleared' ? `${result} cleared` : `${result} MB freed`}
            </motion.span>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}

export default function Ops() {
  const { isAdmin } = useAuth()

  const { data: security, isLoading: secLoading } = useQuery<SecurityReport>({
    queryKey: ['admin', 'security'],
    queryFn: api.admin.security,
    enabled: isAdmin,
  })

  const { data: cache, isLoading: cacheLoading } = useQuery<CacheStats>({
    queryKey: ['admin', 'cache'],
    queryFn: api.admin.cache,
    enabled: isAdmin,
  })

  const { data: memory, isLoading: memLoading } = useQuery<MemoryStatus>({
    queryKey: ['admin', 'memory'],
    queryFn: api.admin.memory,
    enabled: isAdmin,
  })

  const { data: sessions, isLoading: sessLoading } = useQuery<{ active: number; sessions: Array<{ username: string; created_at: string }> }>({
    queryKey: ['admin', 'sessions'],
    queryFn: api.admin.sessions,
    enabled: isAdmin,
  })

  const { data: rateLimit, isLoading: rlLoading } = useQuery<RateLimitStatus>({
    queryKey: ['admin', 'rateLimit'],
    queryFn: api.admin.rateLimit,
    enabled: isAdmin,
  })

  const { data: tiers } = useQuery<Record<string, { rate_limit: number; features: string[] }>>({
    queryKey: ['admin', 'tier'],
    queryFn: api.admin.tier,
    enabled: isAdmin,
  })

  const { data: health } = useQuery<HealthCheck>({
    queryKey: ['health'],
    queryFn: api.health,
    enabled: isAdmin,
    refetchInterval: 30000,
  })

  const isLoading = secLoading || cacheLoading || memLoading || sessLoading || rlLoading

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4">
        <Lock className="w-8 h-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground font-mono">Admin access required</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="skeleton h-7 w-48 rounded" />
        <div className="bento-grid">
          {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
        </div>
      </div>
    )
  }

  const uptimeHrs = health ? (health.uptime_seconds / 3600).toFixed(1) : '—'
  const cacheHit = cache ? formatPercent(cache.hit_rate, 0) : '0%'

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      <motion.div variants={containerVariants} className="mb-2">
        <h2 className="text-display-sm font-serif text-foreground tracking-tight">Operations</h2>
        <p className="text-sm text-muted-foreground mt-1">Infrastructure control plane — security, caching, memory, sessions.</p>
      </motion.div>

      {/* Health bar */}
      {health && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...springConfig, delay: 0.05 }}
          className="bento-card col-span-12 p-4 flex items-center gap-6 flex-wrap"
        >
          <div className="flex items-center gap-2">
            <span className={cn('status-dot', health.status === 'healthy' ? 'status-dot-healthy' : 'status-dot-warning')} />
            <span className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Status</span>
            <span className={cn('text-sm font-semibold', health.status === 'healthy' ? 'text-success' : 'text-warning')}>
              {health.status}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Server className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-xs font-mono text-muted-foreground">{health.version}</span>
          </div>
          <div className="flex items-center gap-2">
            <Clock className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-xs font-mono text-muted-foreground">{uptimeHrs}h uptime</span>
          </div>
          {Object.entries(health.checks).map(([key, check]) => (
            <div key={key} className="flex items-center gap-1.5">
              <span className={cn('status-dot', check.ok ? 'status-dot-healthy' : 'status-dot-warning')} />
              <span className="text-[11px] font-mono text-muted-foreground">{key}</span>
              {check.detail && <span className="text-[11px] font-mono text-muted-foreground/60">({check.detail})</span>}
            </div>
          ))}
        </motion.div>
      )}

      <div className="bento-grid">
        {/* Security section */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...springConfig, delay: 0.1 }}
          className="bento-card col-span-12 lg:col-span-8 p-5 space-y-4"
        >
          <div className="flex items-center gap-2.5">
            <motion.div whileHover={{ rotate: 180 }} transition={{ duration: 0.4 }} className="p-2 bg-accent/10 rounded-lg">
              <Shield className="w-4 h-4 text-accent" />
            </motion.div>
            <h3 className="text-sm font-serif text-foreground">Security</h3>
          </div>
          {security && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricTile icon={AlertTriangle} label="Auth failures 24h" value={security.auth_failures_24h} accent={security.auth_failures_24h > 5} delay={0.15} />
              <MetricTile icon={Lock} label="Rate limit hits" value={security.rate_limit_hits_24h} accent={security.rate_limit_hits_24h > 10} delay={0.18} />
              <MetricTile icon={Users} label="Active sessions" value={security.active_sessions} delay={0.21} />
              <MetricTile icon={Eye} label="Total sessions" value={security.total_sessions} delay={0.24} />
            </div>
          )}
          {security && security.suspicious_ips.length > 0 && (
            <div className="mt-3 p-3 rounded-lg bg-warning/5 border border-warning/15">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle className="w-3.5 h-3.5 text-warning" />
                <span className="text-xs font-mono text-warning">Suspicious IPs</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {security.suspicious_ips.map((ip) => (
                  <code key={ip} className="px-2 py-0.5 text-[11px] font-mono bg-warning/10 text-warning rounded">{ip}</code>
                ))}
              </div>
            </div>
          )}
        </motion.div>

        {/* Rate limit overview */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...springConfig, delay: 0.15 }}
          className="bento-card col-span-12 lg:col-span-4 p-5 space-y-4"
        >
          <div className="flex items-center gap-2.5">
            <motion.div whileHover={{ rotate: 180 }} transition={{ duration: 0.4 }} className="p-2 bg-accent/10 rounded-lg">
              <Gauge className="w-4 h-4 text-accent" />
            </motion.div>
            <h3 className="text-sm font-serif text-foreground">Rate Limiting</h3>
          </div>
          {rateLimit && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-muted-foreground">Global</span>
                <span className={cn('text-xs font-mono', rateLimit.global_enabled ? 'text-success' : 'text-warning')}>
                  {rateLimit.global_enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
              {Object.entries(rateLimit.active_limits).map(([key, val]) => (
                <div key={key} className="flex items-center justify-between py-1.5 border-t border-border/20">
                  <span className="text-[11px] font-mono text-muted-foreground">{key}</span>
                  <span className="text-[11px] font-mono tabular-nums text-foreground">
                    {val.current}/{val.limit}
                  </span>
                </div>
              ))}
              {Object.keys(rateLimit.active_limits).length === 0 && (
                <p className="text-[11px] font-mono text-muted-foreground/60">No active limits</p>
              )}
            </div>
          )}
        </motion.div>

        {/* Cache section */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...springConfig, delay: 0.2 }}
          className="bento-card col-span-12 lg:col-span-6 p-5 space-y-4"
        >
          <div className="flex items-center gap-2.5">
            <motion.div whileHover={{ rotate: 180 }} transition={{ duration: 0.4 }} className="p-2 bg-accent/10 rounded-lg">
              <Database className="w-4 h-4 text-accent" />
            </motion.div>
            <h3 className="text-sm font-serif text-foreground">Cache</h3>
          </div>
          {cache && (
            <div className="grid grid-cols-2 gap-3">
              <MetricTile icon={Zap} label="Hit rate" value={cacheHit} accent={cache.hit_rate > 0.3} delay={0.25} />
              <MetricTile icon={Database} label="Entries" value={formatNumber(cache.total_entries)} delay={0.28} />
              <MetricTile icon={Activity} label="Evictions" value={cache.evictions} delay={0.31} />
              <MetricTile icon={HardDrive} label="Memory" value={`${cache.memory_usage_mb.toFixed(1)} MB`} delay={0.34} />
            </div>
          )}
          <ActionCard
            title="Clear Cache"
            description="Evict all cached responses. Next requests will compute fresh results."
            icon={Trash2}
            mutationFn={api.admin.cacheClear}
            queryKeyToInvalidate="admin/cache"
            successKey="cleared"
            delay={0.37}
          />
        </motion.div>

        {/* Memory section */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...springConfig, delay: 0.25 }}
          className="bento-card col-span-12 lg:col-span-6 p-5 space-y-4"
        >
          <div className="flex items-center gap-2.5">
            <motion.div whileHover={{ rotate: 180 }} transition={{ duration: 0.4 }} className="p-2 bg-accent/10 rounded-lg">
              <MemoryStick className="w-4 h-4 text-accent" />
            </motion.div>
            <h3 className="text-sm font-serif text-foreground">Memory</h3>
          </div>
          {memory && (
            <div className="grid grid-cols-2 gap-3">
              <MetricTile icon={Cpu} label="RSS" value={`${memory.rss_mb.toFixed(1)} MB`} delay={0.3} />
              <MetricTile icon={HardDrive} label="Heap" value={`${memory.heap_mb.toFixed(1)} MB`} delay={0.33} />
              <MetricTile icon={Activity} label="GC collections" value={memory.gc_collections} delay={0.36} />
              <MetricTile icon={Zap} label="Optimization" value={memory.optimization_available ? 'Available' : 'N/A'} delay={0.39} />
            </div>
          )}
          <ActionCard
            title="Force GC Cleanup"
            description="Run garbage collection and memory optimization routines."
            icon={RefreshCw}
            mutationFn={api.admin.memoryCleanup}
            queryKeyToInvalidate="admin/memory"
            successKey="freed_mb"
            delay={0.42}
          />
        </motion.div>

        {/* Sessions table */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...springConfig, delay: 0.3 }}
          className="bento-card col-span-12 lg:col-span-7 p-5 space-y-4"
        >
          <div className="flex items-center gap-2.5">
            <motion.div whileHover={{ rotate: 180 }} transition={{ duration: 0.4 }} className="p-2 bg-accent/10 rounded-lg">
              <Users className="w-4 h-4 text-accent" />
            </motion.div>
            <h3 className="text-sm font-serif text-foreground">Sessions</h3>
            {sessions && (
              <span className="ml-auto text-xs font-mono text-muted-foreground">
                {sessions.active} active
              </span>
            )}
          </div>
          {sessions && sessions.sessions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-border/30">
                    <th className="pb-2 text-[11px] font-mono uppercase tracking-wider text-muted-foreground">User</th>
                    <th className="pb-2 text-[11px] font-mono uppercase tracking-wider text-muted-foreground">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.sessions.map((s, i) => (
                    <motion.tr
                      key={`${s.username}-${i}`}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.35 + i * 0.04 }}
                      className="border-b border-border/10 last:border-0"
                    >
                      <td className="py-2 text-sm font-mono text-foreground">{s.username}</td>
                      <td className="py-2 text-xs font-mono text-muted-foreground tabular-nums">
                        {new Date(s.created_at).toLocaleString()}
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs font-mono text-muted-foreground/60">No active sessions</p>
          )}
        </motion.div>

        {/* Tier configuration */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...springConfig, delay: 0.35 }}
          className="bento-card col-span-12 lg:col-span-5 p-5 space-y-4"
        >
          <div className="flex items-center gap-2.5">
            <motion.div whileHover={{ rotate: 180 }} transition={{ duration: 0.4 }} className="p-2 bg-accent/10 rounded-lg">
              <Cpu className="w-4 h-4 text-accent" />
            </motion.div>
            <h3 className="text-sm font-serif text-foreground">Tier Config</h3>
          </div>
          {tiers && (
            <div className="space-y-3">
              {Object.entries(tiers).map(([name, cfg], i) => (
                <motion.div
                  key={name}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.4 + i * 0.06 }}
                  className="p-3 rounded-lg bg-muted/20 border border-border/20"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className={cn(
                      'text-xs font-mono uppercase tracking-wider',
                      name === 'enterprise' ? 'text-accent' : name === 'pro' ? 'text-info' : 'text-muted-foreground'
                    )}>
                      {name}
                    </span>
                    <span className="text-xs font-mono tabular-nums text-foreground">
                      {cfg.rate_limit} rpm
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {cfg.features.map((f) => (
                      <span key={f} className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-muted/40 text-muted-foreground">
                        {f}
                      </span>
                    ))}
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </motion.div>
      </div>
    </motion.div>
  )
}
