import { memo, useEffect, useState, useRef } from 'react'
import { motion, useInView } from 'framer-motion'
import { cn } from '../../lib/utils'

interface StatCounterProps {
  value: number
  label: string
  decimals?: number
  prefix?: string
  suffix?: string
  delay?: number
  className?: string
}

export default memo(function StatCounter({
  value,
  label,
  decimals = 0,
  prefix = '',
  suffix = '',
  delay = 0,
  className,
}: StatCounterProps) {
  const [displayValue, setDisplayValue] = useState(0)
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref, { once: true })

  useEffect(() => {
    if (!isInView) return

    const duration = 1500
    const startTime = performance.now()

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime - delay * 1000
      if (elapsed < 0) {
        requestAnimationFrame(animate)
        return
      }

      const progress = Math.min(elapsed / duration, 1)
      const easeOutQuart = 1 - Math.pow(1 - progress, 4)
      const currentValue = value * easeOutQuart

      setDisplayValue(currentValue)

      if (progress < 1) {
        requestAnimationFrame(animate)
      }
    }

    requestAnimationFrame(animate)
  }, [isInView, value, delay])

  const formattedValue = decimals > 0
    ? displayValue.toFixed(decimals)
    : Math.round(displayValue).toLocaleString()

  return (
    <motion.div
      ref={ref}
      initial={{ scale: 0.95, opacity: 0 }}
      animate={isInView ? { scale: 1, opacity: 1 } : {}}
      transition={{ type: 'spring', stiffness: 200, damping: 20, delay }}
      className={cn("text-center", className)}
    >
      <div className="text-display-sm font-serif text-foreground tabular-nums tracking-tight">
        {prefix}{formattedValue}{suffix}
      </div>
      <div className="text-xs text-muted-foreground mt-1.5 uppercase tracking-wider font-mono">{label}</div>
    </motion.div>
  )
})
