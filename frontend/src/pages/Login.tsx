import { useState } from 'react'
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion'
import { useAuth } from '../hooks/useAuth'
import { cn, springConfig, easing } from '../lib/utils'
import { Shield, AlertCircle, ArrowRight } from 'lucide-react'

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [shake, setShake] = useState(false)

  const mouseX = useMotionValue(0)
  const mouseY = useMotionValue(0)
  const springX = useSpring(mouseX, { stiffness: 50, damping: 20 })
  const springY = useSpring(mouseY, { stiffness: 50, damping: 20 })
  const bgX = useTransform(springX, [0, 1], [0, 15])
  const bgY = useTransform(springY, [0, 1], [0, 15])

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect()
    mouseX.set((e.clientX - rect.left) / rect.width)
    mouseY.set((e.clientY - rect.top) / rect.height)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError('')

    const success = await login(username, password)

    if (!success) {
      setError('Invalid credentials')
      setShake(true)
      setTimeout(() => setShake(false), 500)
    }

    setIsLoading(false)
  }

  return (
    <div
      className="min-h-screen flex relative overflow-hidden noise-overlay"
      onMouseMove={handleMouseMove}
    >
      <motion.div
        style={{ x: bgX, y: bgY }}
        className="absolute inset-0 gradient-mesh opacity-60"
      />

      <div className="hidden lg:flex lg:w-1/2 relative items-center justify-center p-12">
        <motion.div
          initial={{ opacity: 0, x: -40 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8, ease: easing.outExpo }}
          className="relative z-10 max-w-md space-y-8"
        >
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...springConfig, delay: 0.1 }}
          >
            <div className="w-12 h-12 bg-accent/20 rounded-xl flex items-center justify-center mb-6 shadow-glow-amber-sm">
              <Shield className="w-6 h-6 text-accent" />
            </div>
            <h1 className="text-display-lg font-serif text-foreground leading-[1.05]">
              Support<br />OID
            </h1>
          </motion.div>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...springConfig, delay: 0.2 }}
            className="text-muted-foreground text-lg leading-relaxed"
          >
            AI-powered customer support orchestration. Classify, route, and resolve with precision.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...springConfig, delay: 0.3 }}
            className="flex gap-6"
          >
            {[
              { value: '99.2%', label: 'Accuracy' },
              { value: '<2s', label: 'Response' },
              { value: '24/7', label: 'Uptime' },
            ].map((stat) => (
              <div key={stat.label} className="space-y-1">
                <div className="text-heading font-serif text-foreground tabular-nums">{stat.value}</div>
                <div className="text-xs text-muted-foreground uppercase tracking-wider font-mono">{stat.label}</div>
              </div>
            ))}
          </motion.div>

          <motion.div
            animate={{ y: [0, -8, 0] }}
            transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
            className="absolute -bottom-4 left-0 w-64 h-64 rounded-full bg-accent/5 blur-3xl"
          />
        </motion.div>

        <div className="absolute top-0 right-0 w-px h-full bg-gradient-to-b from-transparent via-accent/20 to-transparent" />
      </div>

      <div className="w-full lg:w-1/2 flex items-center justify-center p-6 sm:p-12 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={springConfig}
          className={cn("w-full max-w-sm", shake && "animate-shake")}
        >
          <div className="liquid-glass-dark-elevated rounded-2xl p-8">
            <motion.div
              className="mb-8"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ ...springConfig, delay: 0.1 }}
            >
              <h2 className="text-title font-serif text-foreground">Sign in</h2>
              <p className="text-sm text-muted-foreground mt-1.5">
                Enter your credentials to continue
              </p>
            </motion.div>

            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-5 p-3 rounded-lg bg-destructive/10 border border-destructive/20 flex items-center gap-2.5 text-sm text-destructive"
              >
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                {error}
              </motion.div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              <motion.div
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ ...springConfig, delay: 0.15 }}
              >
                <label htmlFor="username" className="block text-xs font-mono font-medium text-muted-foreground uppercase tracking-wider mb-2">
                  Username
                </label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-lg border border-input bg-background/50 text-foreground placeholder:text-muted-foreground/50 focus-ring transition-all text-sm"
                  placeholder="Enter username"
                  required
                  autoComplete="username"
                />
              </motion.div>

              <motion.div
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ ...springConfig, delay: 0.25 }}
              >
                <label htmlFor="password" className="block text-xs font-mono font-medium text-muted-foreground uppercase tracking-wider mb-2">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-lg border border-input bg-background/50 text-foreground placeholder:text-muted-foreground/50 focus-ring transition-all text-sm"
                  placeholder="Enter password"
                  required
                  autoComplete="current-password"
                />
              </motion.div>

              <motion.button
                type="submit"
                disabled={isLoading}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...springConfig, delay: 0.35 }}
                whileHover={{ scale: 1.01, y: -1 }}
                whileTap={{ scale: 0.98, y: 0.5 }}
                className="w-full py-2.5 px-4 bg-accent text-accent-foreground rounded-lg font-medium shadow-glow-amber-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 btn-tactile text-sm"
              >
                {isLoading ? (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                    className="w-4 h-4 border-2 border-accent-foreground/30 border-t-accent-foreground rounded-full"
                  />
                ) : (
                  <>
                    Sign In
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </motion.button>
            </form>
          </div>
        </motion.div>
      </div>

      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          25% { transform: translateX(-8px); }
          75% { transform: translateX(8px); }
        }
        .animate-shake { animation: shake 0.4s ease-in-out; }
      `}</style>
    </div>
  )
}
