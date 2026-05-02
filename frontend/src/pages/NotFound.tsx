import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import MagneticButton from '../components/shared/MagneticButton'

export default function NotFound() {
  const navigate = useNavigate()

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center min-h-screen gap-6 p-8"
    >
      <div className="w-16 h-16 rounded-full bg-accent/10 flex items-center justify-center">
        <AlertTriangle className="w-8 h-8 text-accent" />
      </div>
      <div className="text-center space-y-2">
        <h1 className="text-display-lg font-serif text-foreground">404</h1>
        <p className="text-muted-foreground">This page doesn't exist</p>
      </div>
      <MagneticButton
        onClick={() => navigate('/dashboard')}
        className="px-5 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90"
      >
        Go to Dashboard
      </MagneticButton>
    </motion.div>
  )
}
