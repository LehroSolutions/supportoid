import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import AnimatedCard from '../components/shared/AnimatedCard'
import { CardSkeleton } from '../components/shared/Skeleton'
import { containerVariants, cn } from '../lib/utils'
import { BookOpen, Star, BarChart3, Award, FileText, CheckCircle2, AlertTriangle } from 'lucide-react'
import type { KBQualityReport } from '../types'

export default function KBQuality() {
  const { data: report, isLoading } = useQuery<KBQualityReport>({
    queryKey: ['kb-quality'],
    queryFn: api.kb.quality,
  })

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <div className="skeleton h-7 w-40 rounded" />
          <div className="skeleton h-4 w-80 rounded" />
        </div>
        <CardSkeleton />
        <div className="grid grid-cols-2 gap-4">
          <CardSkeleton />
          <CardSkeleton />
        </div>
      </div>
    )
  }

  const gradeColors: Record<string, string> = {
    A: 'bg-accent/15 text-accent',
    B: 'bg-success/10 text-success',
    C: 'bg-warning/10 text-warning',
    D: 'bg-destructive/10 text-destructive',
    F: 'bg-destructive/15 text-destructive',
  }

  const barColors: Record<string, string> = {
    A: 'bg-accent',
    B: 'bg-success',
    C: 'bg-warning',
    D: 'bg-destructive',
    F: 'bg-destructive',
  }

  const dimensionIcons: Record<string, typeof Star> = {
    completeness: CheckCircle2,
    clarity: FileText,
    freshness: Star,
    usage: BarChart3,
    coverage: Award,
  }

  const needsAttentionCount = report?.needs_attention
    ? Object.keys(report.needs_attention).length
    : 0

  const maxGradeCount = report?.grade_distribution
    ? Math.max(...Object.values(report.grade_distribution), 1)
    : 1

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      <div className="mb-2">
        <h2 className="text-display-sm font-serif text-foreground tracking-tight">KB Quality</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Quality report for knowledge entries across completeness, clarity, freshness, usage, and coverage.
        </p>
      </div>

      <AnimatedCard delay={0.05} className="relative overflow-hidden">
        <div className="flex items-center gap-3 mb-5">
          <motion.div whileHover={{ rotate: 12 }} className="p-2 bg-accent/10 rounded-lg">
            <BookOpen className="w-4 h-4 text-accent" />
          </motion.div>
          <h3 className="text-heading font-serif text-foreground">Overview</h3>
          {needsAttentionCount > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono bg-warning/10 text-warning">
              <AlertTriangle className="w-3 h-3" />
              {needsAttentionCount} need attention
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            whileHover={{ scale: 1.01 }}
            className="p-4 rounded-lg bg-muted/30 border border-border/20"
          >
            <p className="text-xs text-muted-foreground font-mono uppercase tracking-wider mb-1">Total Entries</p>
            <p className="text-title font-serif text-foreground tabular-nums">{report?.total_entries.toLocaleString()}</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            whileHover={{ scale: 1.01 }}
            className="p-4 rounded-lg bg-accent/5 border border-accent/15"
          >
            <p className="text-xs text-muted-foreground font-mono uppercase tracking-wider mb-1">Overall Average</p>
            <div className="flex items-baseline gap-2">
              <p className="text-title font-serif text-accent tabular-nums">{report?.overall_avg.toFixed(3)}</p>
              <span className="text-xs text-muted-foreground">/ 1.0</span>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            whileHover={{ scale: 1.01 }}
            className="p-4 rounded-lg bg-muted/30 border border-border/20"
          >
            <p className="text-xs text-muted-foreground font-mono uppercase tracking-wider mb-1">Report Generated</p>
            <p className="text-sm font-medium text-foreground font-mono">{report?.report_generated || '-'}</p>
          </motion.div>
        </div>
      </AnimatedCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AnimatedCard delay={0.2}>
          <div className="flex items-center gap-3 mb-5">
            <motion.div whileHover={{ rotate: 360 }} transition={{ duration: 0.5 }} className="p-2 bg-accent/10 rounded-lg">
              <Award className="w-4 h-4 text-accent" />
            </motion.div>
            <h3 className="text-heading font-serif text-foreground">Grades</h3>
          </div>

          <div className="space-y-3">
            {report?.grade_distribution && Object.entries(report.grade_distribution)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([grade, count], i) => (
                <motion.div
                  key={grade}
                  initial={{ opacity: 0, x: -16 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.04 }}
                  className="flex items-center gap-3"
                >
                  <span className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs font-mono",
                    gradeColors[grade] || 'bg-muted/50 text-muted-foreground'
                  )}>
                    {grade}
                  </span>
                  <div className="flex-1 h-1.5 bg-muted/50 rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${(count / maxGradeCount) * 100}%` }}
                      transition={{ duration: 0.8, delay: 0.35 + i * 0.04 }}
                      className={cn("h-full rounded-full", barColors[grade] || 'bg-accent')}
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
              <BarChart3 className="w-4 h-4 text-accent" />
            </motion.div>
            <h3 className="text-heading font-serif text-foreground">Dimensions</h3>
          </div>

          <div className="space-y-2">
            {report?.dimension_averages && Object.entries(report.dimension_averages)
              .map(([dimension, score], i) => {
                const Icon = dimensionIcons[dimension] || Star
                return (
                  <motion.div
                    key={dimension}
                    initial={{ opacity: 0, x: -16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.4 + i * 0.04 }}
                    whileHover={{ scale: 1.01, backgroundColor: 'oklch(var(--muted) / 0.3)' }}
                    className="flex items-center gap-3 p-2.5 rounded-lg transition-colors"
                  >
                    <div className="p-1.5 bg-muted/50 rounded-md">
                      <Icon className="w-3.5 h-3.5 text-muted-foreground" />
                    </div>
                    <span className="text-xs text-muted-foreground capitalize flex-1 font-mono">
                      {dimension}
                    </span>
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-1.5 bg-muted/50 rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${score * 100}%` }}
                          transition={{ duration: 0.8, delay: 0.45 + i * 0.04 }}
                          className={cn(
                            "h-full rounded-full",
                            score > 0.8 ? 'bg-accent' : score > 0.6 ? 'bg-warning' : 'bg-destructive'
                          )}
                        />
                      </div>
                      <span className="text-xs font-mono font-medium w-10 text-right tabular-nums">
                        {score.toFixed(3)}
                      </span>
                    </div>
                  </motion.div>
                )
              })}
          </div>
        </AnimatedCard>
      </div>
    </motion.div>
  )
}
