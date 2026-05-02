import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import Navigation from './Navigation'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-background noise-overlay gradient-mesh">
      <Navigation />
      <motion.main
        id="main-content"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        className="container mx-auto px-4 py-6 max-w-7xl"
      >
        {children}
      </motion.main>
    </div>
  )
}
