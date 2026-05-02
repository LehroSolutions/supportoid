import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Clock,
  FileText,
  Search,
  XCircle,
} from 'lucide-react'

import AnimatedCard from '../components/shared/AnimatedCard'
import { TableSkeleton } from '../components/shared/Skeleton'
import { api } from '../lib/api'
import { cn, containerVariants } from '../lib/utils'
import type { PaginatedResponse, TraceSummary } from '../types'

export default function Traces() {
  const { data: tracePage, isLoading } = useQuery<PaginatedResponse<TraceSummary>>({
    queryKey: ['traces'],
    queryFn: () => api.traces.list(100, 0),
  })
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const traces = tracePage?.items ?? []
    if (!search) return traces
    const q = search.toLowerCase()
    return traces.filter(
      (trace) =>
        trace.session_id.toLowerCase().includes(q) ||
        trace.summary.toLowerCase().includes(q) ||
        (trace.error && trace.error.toLowerCase().includes(q)) ||
        (trace.user_input && trace.user_input.toLowerCase().includes(q))
    )
  }, [tracePage, search])

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <div className="skeleton h-7 w-40 rounded" />
          <div className="skeleton h-4 w-72 rounded" />
        </div>
        <TableSkeleton rows={6} />
      </div>
    )
  }

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      <div className="mb-2">
        <h2 className="text-display-sm font-serif text-foreground tracking-tight">
          Traces
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Session trace records from the canonical store.
        </p>
      </div>

      <AnimatedCard delay={0.05} className="overflow-hidden">
        <div className="mb-4 flex items-center gap-3">
          <motion.div
            whileHover={{ rotate: 180 }}
            transition={{ duration: 0.5 }}
            className="rounded-lg bg-accent/10 p-2"
          >
            <Activity className="h-4 w-4 text-accent" />
          </motion.div>
          <h3 className="text-heading font-serif text-foreground">Session Traces</h3>
          <span className="ml-auto text-xs font-mono text-muted-foreground">
            {filtered.length} / {tracePage?.total || 0}
          </span>
        </div>

        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search traces by ID, summary, or error..."
            className="focus-ring w-full rounded-lg border border-input bg-background/50 py-2 pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground/50"
            aria-label="Search traces"
          />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50">
                <th className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Session
                </th>
                <th className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    Duration
                  </span>
                </th>
                <th className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Steps
                </th>
                <th className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Status
                </th>
                <th className="px-3 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Summary
                </th>
                <th className="w-8 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((trace, index) => {
                const isExpanded = expanded === trace.session_id
                return (
                  <motion.tr
                    key={trace.session_id}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 + index * 0.02 }}
                    className="border-b border-border/30 transition-colors hover:bg-muted/20"
                  >
                    <td className="px-3 py-2.5">
                      <code className="rounded bg-muted/50 px-2 py-0.5 text-xs text-foreground">
                        {trace.session_id.slice(0, 12)}...
                      </code>
                    </td>
                    <td className="px-3 py-2.5 text-xs tabular-nums">
                      {trace.duration_s.toFixed(3)}s
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="inline-flex items-center gap-1 rounded bg-accent/10 px-1.5 py-0.5 text-xs text-accent">
                        {trace.steps}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      {trace.escalated ? (
                        <span className="inline-flex items-center gap-1 rounded bg-destructive/10 px-1.5 py-0.5 text-xs text-destructive">
                          <AlertTriangle className="h-3 w-3" />
                          Escalated
                        </span>
                      ) : trace.error ? (
                        <span className="inline-flex items-center gap-1 rounded bg-warning/10 px-1.5 py-0.5 text-xs text-warning">
                          <XCircle className="h-3 w-3" />
                          Error
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded bg-success/10 px-1.5 py-0.5 text-xs text-success">
                          <CheckCircle2 className="h-3 w-3" />
                          OK
                        </span>
                      )}
                    </td>
                    <td className="max-w-[200px] truncate px-3 py-2.5 text-xs text-muted-foreground">
                      {trace.summary || trace.user_input || '-'}
                    </td>
                    <td className="px-1 py-2.5">
                      <button
                        onClick={() =>
                          setExpanded(isExpanded ? null : trace.session_id)
                        }
                        className="focus-ring rounded p-1 transition-colors hover:bg-muted/50"
                        aria-label={
                          isExpanded ? 'Collapse trace' : 'Expand trace'
                        }
                      >
                        <motion.div
                          animate={{ rotate: isExpanded ? 180 : 0 }}
                          transition={{ duration: 0.2 }}
                        >
                          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        </motion.div>
                      </button>
                    </td>
                  </motion.tr>
                )
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-muted-foreground">
                    <FileText className="mx-auto mb-2 h-8 w-8 opacity-40" />
                    <p className="text-sm">
                      {search ? 'No matching traces' : 'No traces found'}
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <AnimatePresence>
          {expanded &&
            (() => {
              const trace = filtered.find((item) => item.session_id === expanded)
              if (!trace) return null
              return (
                <motion.div
                  key={expanded}
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden border-t border-border/30"
                >
                  <div className="grid grid-cols-2 gap-4 p-4 text-xs md:grid-cols-4">
                    <div>
                      <span className="font-mono uppercase tracking-wider text-muted-foreground">
                        Session ID
                      </span>
                      <p className="mt-1 font-mono text-foreground">
                        {trace.session_id}
                      </p>
                    </div>
                    <div>
                      <span className="font-mono uppercase tracking-wider text-muted-foreground">
                        User Input
                      </span>
                      <p className="mt-1 truncate text-foreground">
                        {trace.user_input || '-'}
                      </p>
                    </div>
                    <div>
                      <span className="font-mono uppercase tracking-wider text-muted-foreground">
                        Error
                      </span>
                      <p
                        className={cn(
                          'mt-1',
                          trace.error
                            ? 'text-destructive'
                            : 'text-muted-foreground'
                        )}
                      >
                        {trace.error || 'None'}
                      </p>
                    </div>
                    <div>
                      <span className="font-mono uppercase tracking-wider text-muted-foreground">
                        Summary
                      </span>
                      <p className="mt-1 text-foreground">
                        {trace.summary || '-'}
                      </p>
                    </div>
                  </div>
                </motion.div>
              )
            })()}
        </AnimatePresence>
      </AnimatedCard>
    </motion.div>
  )
}
