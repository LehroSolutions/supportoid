import { memo, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { cn, springConfig } from '../../lib/utils'

interface AnimatedCardProps {
  children: ReactNode
  className?: string
  delay?: number
  hover?: boolean
}

const AnimatedCard = memo(function AnimatedCard({
  children,
  className,
  delay = 0,
  hover = true
}: AnimatedCardProps) {
  return (
    <motion.div
      initial={{ y: 16, opacity: 0, scale: 0.98 }}
      animate={{ y: 0, opacity: 1, scale: 1 }}
      transition={{ ...springConfig, delay }}
      whileHover={hover ? {
        y: -2,
        scale: 1.005,
        transition: { type: "spring", stiffness: 400, damping: 25 }
      } : undefined}
      whileTap={hover ? { scale: 0.995 } : undefined}
      className={cn(
        "rounded-xl p-5 liquid-glass-dark cursor-default",
        className
      )}
    >
      {children}
    </motion.div>
  )
})

export default AnimatedCard
