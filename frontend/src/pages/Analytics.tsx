import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import AnimatedCard from '../components/shared/AnimatedCard'
import { CardSkeleton } from '../components/shared/Skeleton'
import { containerVariants, formatCurrency } from '../lib/utils'
import { BarChart3, DollarSign, Phone, Coins, Layers, Cpu, TrendingUp, Zap } from 'lucide-react'
import type { StatsReport } from '../types'

export default function Analytics() {
  const { data: costs, isLoading: costsLoading } = useQuery({
    queryKey: ['costs'],
    queryFn: () => api.stats.costs(),
  })

  const { data: stats, isLoading: statsLoading } = useQuery<StatsReport>({
    queryKey: ['stats'],
    queryFn: api.stats.get,
  })

  const isLoading = costsLoading || statsLoading

  if (isLoading || !costs || !stats) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <div className="skeleton h-7 w-48 rounded" />
          <div className="skeleton h-4 w-72 rounded" />
        </div>
        <CardSkeleton />
        <div className="grid grid-cols-2 gap-4">
          <CardSkeleton />
          <CardSkeleton />
        </div>
      </div>
    )
  }

  const costItems = [
    { value: costs.total_conversations, label: 'Conversations', icon: Phone },
    { value: costs.total_calls, label: 'Total Calls', icon: Layers },
    { value: costs.total_input_tokens, label: 'Input Tokens', icon: Cpu },
    { value: costs.total_output_tokens, label: 'Output Tokens', icon: Cpu },
  ]

  const maxCalls = Math.max(...Object.values(costs.calls_by_model) as number[], 1)
  const maxCost = Math.max(...Object.values(costs.cost_by_model) as number[], 0.0001)

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      <div className="mb-2">
        <h2 className="text-display-sm font-serif text-foreground tracking-tight">Analytics</h2>
        <p className="text-sm text-muted-foreground mt-1">Cross-model usage and operating cost signals.</p>
      </div>

      <AnimatedCard delay={0.05} className="relative overflow-hidden">
        <div className="flex items-center gap-3 mb-4">
          <motion.div
            whileHover={{ scale: 1.1, rotate: -8 }}
            className="p-2.5 bg-accent/15 rounded-lg shadow-glow-amber-sm"
          >
            <DollarSign className="w-5 h-5 text-accent" />
          </motion.div>
          <div>
            <p className="text-xs text-muted-foreground font-mono uppercase tracking-wider">Total Cost</p>
            <p className="text-title font-serif text-foreground tabular-nums">{formatCurrency(costs.total_cost_usd)}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {costItems.map((item, i) => {
            const Icon = item.icon
            return (
              <motion.div
                key={item.label}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + i * 0.04 }}
                whileHover={{ scale: 1.02 }}
                className="p-3 rounded-lg bg-muted/30 border border-border/20"
              >
                <Icon className="w-3.5 h-3.5 text-muted-foreground mb-2" />
                <p className="text-lg font-semibold text-foreground tabular-nums">{item.value.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground font-mono">{item.label}</p>
              </motion.div>
            )
          })}
        </div>
      </AnimatedCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AnimatedCard delay={0.2}>
          <div className="flex items-center gap-3 mb-5">
            <motion.div whileHover={{ rotate: 360 }} transition={{ duration: 0.5 }} className="p-2 bg-accent/10 rounded-lg">
              <Phone className="w-4 h-4 text-accent" />
            </motion.div>
            <h3 className="text-heading font-serif text-foreground">Calls by Model</h3>
          </div>
          <div className="space-y-3">
            {Object.entries(costs.calls_by_model).map(([model, count], i) => (
              <motion.div
                key={model}
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 + i * 0.04 }}
                className="flex items-center gap-3"
              >
                <span className="text-xs text-muted-foreground w-28 truncate font-mono">{model}</span>
                <div className="flex-1 h-1.5 bg-muted/50 rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${(count / maxCalls) * 100}%` }}
                    transition={{ duration: 0.8, delay: 0.35 + i * 0.04 }}
                    className="h-full bg-accent rounded-full"
                  />
                </div>
                <span className="text-xs font-mono font-medium w-10 text-right tabular-nums">{count}</span>
              </motion.div>
            ))}
          </div>
        </AnimatedCard>

        <AnimatedCard delay={0.3}>
          <div className="flex items-center gap-3 mb-5">
            <motion.div whileHover={{ rotate: -15 }} transition={{ duration: 0.3 }} className="p-2 bg-accent/10 rounded-lg">
              <Coins className="w-4 h-4 text-accent" />
            </motion.div>
            <h3 className="text-heading font-serif text-foreground">Cost by Model</h3>
          </div>
          <div className="space-y-3">
            {Object.entries(costs.cost_by_model).map(([model, cost], i) => (
              <motion.div
                key={model}
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.4 + i * 0.04 }}
                className="flex items-center gap-3"
              >
                <span className="text-xs text-muted-foreground w-28 truncate font-mono">{model}</span>
                <div className="flex-1 h-1.5 bg-muted/50 rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${(cost / maxCost) * 100}%` }}
                    transition={{ duration: 0.8, delay: 0.45 + i * 0.04 }}
                    className="h-full bg-accent/70 rounded-full"
                  />
                </div>
                <span className="text-xs font-mono font-medium w-16 text-right tabular-nums">${cost.toFixed(4)}</span>
              </motion.div>
            ))}
          </div>
        </AnimatedCard>
      </div>

      <AnimatedCard delay={0.4}>
        <div className="flex items-center gap-3 mb-5">
          <motion.div whileHover={{ rotate: 180 }} transition={{ duration: 0.5 }} className="p-2 bg-accent/10 rounded-lg">
            <TrendingUp className="w-4 h-4 text-accent" />
          </motion.div>
          <h3 className="text-heading font-serif text-foreground">Runtime</h3>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Version', value: stats.version, icon: Zap },
            { label: 'Processed', value: stats.total_processed.toLocaleString(), icon: BarChart3 },
            { label: 'Escalations', value: stats.escalations.toString(), icon: TrendingUp },
            { label: 'Cache Hit', value: `${stats.cache_hit_rate.toFixed(2)}%`, icon: Zap },
          ].map((stat, i) => {
            const Icon = stat.icon
            return (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.5 + i * 0.04 }}
                whileHover={{ y: -1 }}
                className="p-3 rounded-lg bg-muted/30 border border-border/20 text-center"
              >
                <Icon className="w-3.5 h-3.5 text-muted-foreground mx-auto mb-2" />
                <p className="text-lg font-semibold text-foreground tabular-nums">{stat.value}</p>
                <p className="text-xs text-muted-foreground font-mono">{stat.label}</p>
              </motion.div>
            )
          })}
        </div>
      </AnimatedCard>
    </motion.div>
  )
}
