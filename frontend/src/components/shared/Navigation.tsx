import { motion } from 'framer-motion'
import { NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, MessageSquare, Activity, BarChart3, BookOpen, LogOut, Shield } from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import { cn } from '../../lib/utils'

const baseNavItems = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/chat', label: 'Chat', icon: MessageSquare },
  { path: '/traces', label: 'Traces', icon: Activity },
  { path: '/kb-quality', label: 'KB Quality', icon: BookOpen },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
]

const adminNavItems = [
  { path: '/ops', label: 'Operations', icon: Shield },
]

export default function Navigation() {
  const { user, logout, isAdmin } = useAuth()
  const location = useLocation()

  if (!user) return null

  const navItems = isAdmin ? [...baseNavItems, ...adminNavItems] : baseNavItems

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ type: 'spring', stiffness: 200, damping: 25 }}
      className="sticky top-0 z-50"
    >
      <div className="container mx-auto px-4 py-3 max-w-7xl">
        <nav className="liquid-glass-dark-elevated rounded-xl px-4 py-3" aria-label="Main navigation">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <motion.div
                whileHover={{ scale: 1.05, rotate: 3 }}
                className="w-8 h-8 bg-accent rounded-lg flex items-center justify-center shadow-glow-amber-sm"
              >
                <span className="text-accent-foreground font-bold text-sm">S</span>
              </motion.div>
              <div>
                <h1 className="font-serif text-heading leading-tight text-foreground">SupportOID</h1>
                <p className="text-[11px] text-muted-foreground tracking-wide uppercase">
                  {user.username}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className={cn(
                "px-2.5 py-0.5 rounded-md text-[11px] font-mono font-medium tracking-wider uppercase",
                user.role === 'admin' && "bg-accent/15 text-accent",
                user.role === 'analyst' && "bg-info/15 text-info",
                user.role === 'support' && "bg-muted text-muted-foreground"
              )}>
                {user.role}
              </span>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={logout}
                className="p-2 hover:bg-muted/50 rounded-lg transition-colors focus-ring"
                aria-label="Sign out"
              >
                <LogOut className="w-4 h-4 text-muted-foreground" />
              </motion.button>
            </div>
          </div>

          <div className="flex flex-wrap gap-1" role="tablist">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path

              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  role="tab"
                  aria-selected={isActive}
                  aria-label={item.label}
                  className={({ isActive }) => cn(
                    "relative px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200",
                    "flex items-center gap-2",
                    "focus-ring",
                    isActive
                      ? "text-accent bg-accent/10"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                  )}
                >
                  <motion.div
                    whileHover={{ rotate: isActive ? 0 : 8 }}
                    transition={{ type: 'spring', stiffness: 300 }}
                  >
                    <Icon className="w-3.5 h-3.5" />
                  </motion.div>
                  {item.label}
                  {isActive && (
                    <motion.div
                      layoutId="activeNav"
                      className="absolute inset-0 bg-accent/10 rounded-lg -z-10"
                      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                    />
                  )}
                </NavLink>
              )
            })}
          </div>
        </nav>
      </div>
    </motion.header>
  )
}
