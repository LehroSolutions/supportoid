import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useAuth } from './hooks/useAuth'
import Layout from './components/shared/Layout'
import ErrorBoundary from './components/shared/ErrorBoundary'
import { Skeleton } from './components/shared/Skeleton'

const Login = lazy(() => import('./pages/Login'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Chat = lazy(() => import('./pages/Chat'))
const Traces = lazy(() => import('./pages/Traces'))
const Analytics = lazy(() => import('./pages/Analytics'))
const KBQuality = lazy(() => import('./pages/KBQuality'))
const Ops = lazy(() => import('./pages/Ops'))
const NotFound = lazy(() => import('./pages/NotFound'))

function PageSuspense() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="space-y-4 w-full max-w-md px-8">
        <Skeleton variant="line" className="h-6 w-1/3" />
        <Skeleton variant="card" />
        <Skeleton variant="line" className="h-4 w-2/3" />
      </div>
    </div>
  )
}

function App() {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center noise-overlay gradient-mesh">
        <div className="space-y-3 flex flex-col items-center">
          <div className="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
          <span className="text-xs text-muted-foreground font-mono">loading</span>
        </div>
      </div>
    )
  }

  return (
    <ErrorBoundary>
      <AnimatePresence mode="wait">
        <Routes>
          <Route
            path="/login"
            element={user ? <Navigate to="/dashboard" replace /> : (
              <Suspense fallback={<PageSuspense />}>
                <Login />
              </Suspense>
            )}
          />
          <Route
            path="/*"
            element={
              user ? (
                <Layout>
                  <ErrorBoundary>
                    <Suspense fallback={<PageSuspense />}>
                      <Routes>
                        <Route path="/" element={<Navigate to="/dashboard" replace />} />
                        <Route path="/dashboard" element={<Dashboard />} />
                        <Route path="/chat" element={<Chat />} />
                        <Route path="/traces" element={<Traces />} />
                        <Route path="/analytics" element={<Analytics />} />
                        <Route path="/kb-quality" element={<KBQuality />} />
                        <Route path="/ops" element={<Ops />} />
                        <Route path="*" element={<NotFound />} />
                      </Routes>
                    </Suspense>
                  </ErrorBoundary>
                </Layout>
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
        </Routes>
      </AnimatePresence>
    </ErrorBoundary>
  )
}

export default App
