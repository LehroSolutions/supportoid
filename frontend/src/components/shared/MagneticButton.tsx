import { useRef, type ReactNode, type MouseEvent } from 'react'
import { motion, useMotionValue, useSpring } from 'framer-motion'
import { cn } from '../../lib/utils'

interface MagneticButtonProps {
  children: ReactNode
  className?: string
  onClick?: () => void
  disabled?: boolean
  as?: 'button' | 'a'
  href?: string
  strength?: number
}

export default function MagneticButton({
  children,
  className,
  onClick,
  disabled = false,
  as = 'button',
  href,
  strength = 0.3,
}: MagneticButtonProps) {
  const ref = useRef<HTMLElement>(null)
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const springX = useSpring(x, { stiffness: 300, damping: 20 })
  const springY = useSpring(y, { stiffness: 300, damping: 20 })

  const handleMouse = (e: MouseEvent) => {
    if (!ref.current || disabled) return
    const rect = ref.current.getBoundingClientRect()
    const centerX = rect.left + rect.width / 2
    const centerY = rect.top + rect.height / 2
    x.set((e.clientX - centerX) * strength)
    y.set((e.clientY - centerY) * strength)
  }

  const handleLeave = () => {
    x.set(0)
    y.set(0)
  }

  const Component = as === 'a' ? motion.a : motion.button

  return (
    <Component
      ref={ref as React.Ref<HTMLButtonElement & HTMLAnchorElement>}
      onMouseMove={handleMouse}
      onMouseLeave={handleLeave}
      onClick={onClick}
      disabled={disabled}
      href={href}
      style={{ x: springX, y: springY }}
      whileTap={disabled ? undefined : { scale: 0.97 }}
      className={cn(
        'btn-tactile focus-ring inline-flex items-center justify-center',
        disabled && 'opacity-50 cursor-not-allowed',
        className
      )}
    >
      {children}
    </Component>
  )
}
