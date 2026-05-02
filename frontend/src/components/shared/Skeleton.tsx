import { cn } from '../../lib/utils'

interface SkeletonProps {
  className?: string
  variant?: 'line' | 'circle' | 'card' | 'stat'
}

export function Skeleton({ className, variant = 'line' }: SkeletonProps) {
  return (
    <div
      className={cn(
        'skeleton',
        variant === 'line' && 'h-4 w-full',
        variant === 'circle' && 'h-10 w-10 rounded-full',
        variant === 'card' && 'h-48 w-full rounded-xl',
        variant === 'stat' && 'h-20 w-full rounded-xl',
        className
      )}
      aria-hidden="true"
    />
  )
}

export function CardSkeleton() {
  return (
    <div className="bento-card space-y-4 p-5">
      <div className="skeleton h-4 w-1/3 rounded" />
      <div className="skeleton h-8 w-1/2 rounded" />
      <div className="skeleton h-3 w-2/3 rounded" />
    </div>
  )
}

export function StatSkeleton() {
  return (
    <div className="bento-card p-5 space-y-3">
      <div className="skeleton h-3 w-24 rounded" />
      <div className="skeleton h-9 w-32 rounded" />
      <div className="skeleton h-3 w-20 rounded" />
    </div>
  )
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      <div className="skeleton h-10 w-full rounded-lg" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton h-12 w-full rounded-lg" style={{ animationDelay: `${i * 100}ms` }} />
      ))}
    </div>
  )
}
