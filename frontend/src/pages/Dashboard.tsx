import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import StatCounter from '../components/shared/StatCounter'
import { StatSkeleton } from '../components/shared/Skeleton'
import { containerVariants, springConfig, formatPercent, cn } from '../lib/utils'
import { Zap, AlertTriangle, Users, Activity, Cpu, Target, Gauge, Database, TrendingUp } from 'lucide-react'
import type { StatsReport } from '../types'

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-mono tracking-wide",
      ok ? "text-success bg-success/10" : "text-warning bg-warning/10"
    )}>
      <span className={cn("status-dot", ok ? "status-dot-healthy" : "status-dot-warning")} />
      {label}
    </span>
  )
}

export default function Dashboard() {
  const { data: stats, isLoading } = useQuery<StatsReport>({
    queryKey: ['stats'],
    queryFn: api.stats.get,
  })

  if (isLoading || !stats) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <div className="skeleton h-7 w-48 rounded" />
          <div className="skeleton h-4 w-80 rounded" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <StatSkeleton key={i} />)}
        </div>
        <StatSkeleton />
      </div>
    )
  }

  const primaryStats = [
    { value: stats.total_processed, label: 'Processed', icon: Zap, accent: false },
    { value: stats.escalations, label: 'Escalations', icon: AlertTriangle, accent: true },
    { value: stats.active_sessions, label: 'Sessions', icon: Users, accent: false },
    { value: stats.traces, label: 'Traces', icon: Activity, accent: false },
  ]

  const modelMetrics = [
    { label: 'Version', value: stats.version, icon: Cpu },
    { label: 'Classifier v', value: String(stats.model_version), icon: Target },
    { label: 'Accuracy', value: formatPercent(stats.model_accuracy), icon: Gauge, highlight: true },
    { label: 'Confidence', value: formatPercent(stats.avg_confidence), icon: TrendingUp },
    { label: 'Quality', value: stats.avg_quality.toFixed(3), icon: Database },
    { label: 'KB entries', value: stats.knowledge_entries.toLocaleString(), icon: Database },
  ]

  const cacheHitPct = stats.cache_hit_rate
  const errorRate = stats.total_processed > 0
    ? ((stats.errors / stats.total_processed) * 100)
    : 0

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      <motion.div variants={containerVariants} className="mb-2">
        <h2 className="text-display-sm font-serif text-foreground tracking-tight">Dashboard</h2>
        <p className="text-sm text-muted-foreground mt-1">Core platform status — API, CLI, and web runtime.</p>
      </motion.div>

      <div className="bento-grid">
        {primaryStats.map((stat, i) => {
          const Icon = stat.icon
          const isFeatured = i === 0
          return (
            <motion.div
              key={stat.label}
              initial={{ y: 16, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ ...springConfig, delay: i * 0.06 }}
              className={cn(
                "bento-card group",
                isFeatured ? "col-span-12 md:col-span-6 lg:col-span-8" : "col-span-6 md:col-span-3 lg:col-span-2"
              )}
            >
              <div className="flex items-start justify-between">
                <div className={cn(isFeatured && "flex-1")}>
                  <StatCounter
                    value={stat.value}
                    label={stat.label}
                    delay={i * 0.08}
                    className={isFeatured ? "text-left" : undefined}
                  />
                </div>
                <motion.div
                  whileHover={{ rotate: 12, scale: 1.1 }}
                  className={cn(
                    "p-2.5 rounded-lg",
                    stat.accent ? "bg-accent/10 text-accent" : "bg-muted/50 text-muted-foreground"
                  )}
                >
                  <Icon className="w-4 h-4" />
                </motion.div>
              </div>
              {isFeatured && (
                <div className="flex gap-3 mt-4 pt-4 border-t border-border/30">
                  <StatusPill ok={errorRate < 5} label={errorRate < 5 ? 'Low errors' : 'Elevated errors'} />
                  <StatusPill ok={cacheHitPct > 30} label={`Cache ${cacheHitPct.toFixed(0)}%`} />
                </div>
              )}
            </motion.div>
          )
        })}

        <motion.div
          initial={{ y: 16, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ ...springConfig, delay: 0.3 }}
          className="bento-card col-span-12"
        >
          <div className="flex items-center gap-3 mb-5">
            <motion.div
              whileHover={{ rotate: 180 }}
              transition={{ duration: 0.5 }}
              className="p-2 bg-accent/10 rounded-lg"
            >
              <Cpu className="w-4 h-4 text-accent" />
            </motion.div>
            <h3 className="text-heading font-serif text-foreground">Model Health</h3>
            <StatusPill ok={stats.model_accuracy > 0.8} label={formatPercent(stats.model_accuracy, 0)} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {modelMetrics.map((item, i) => {
              const Icon = item.icon
              return (
                <motion.div
                  key={item.label}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.35 + i * 0.04 }}
                  whileHover={{ scale: 1.02, backgroundColor: 'oklch(var(--muted) / 0.5)' }}
                  className={cn(
                    "flex items-center justify-between p-3 rounded-lg border transition-all duration-200",
                    item.highlight
                      ? "bg-accent/5 border-accent/15"
                      : "bg-muted/20 border-border/30"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <Icon className={cn("w-3.5 h-3.5", item.highlight ? "text-accent" : "text-muted-foreground")} />
                    <span className="text-xs text-muted-foreground">{item.label}</span>
                  </div>
                  <span className={cn("text-sm font-semibold tabular-nums", item.highlight && "text-accent")}>
                    {item.value}
                  </span>
                </motion.div>
              )
            })}
          </div>
        </motion.div>
      </div>
    </motion.div>
  )
}
