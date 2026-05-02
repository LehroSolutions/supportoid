import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useMutation } from '@tanstack/react-query'
import { api } from '../lib/api'
import { springConfig, cn, formatDuration } from '../lib/utils'
import { Bot, User, AlertCircle, ArrowUp, CircleDot } from 'lucide-react'
import type { ChatResponse } from '../types'

export default function Chat() {
  const [message, setMessage] = useState('')
  const [conversationId, setConversationId] = useState('')
  const [result, setResult] = useState<ChatResponse | null>(null)
  const [history, setHistory] = useState<{ role: 'user' | 'assistant'; content: string }[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)

  const chatMutation = useMutation({
    mutationFn: api.chat.send,
    onSuccess: (data) => {
      setResult(data)
      setHistory(prev => [
        ...prev,
        { role: 'user', content: message },
        { role: 'assistant', content: data.response },
      ])
      setMessage('')
    },
  })

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [history])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!message.trim() || chatMutation.isPending) return
    chatMutation.mutate({
      message: message.trim(),
      conversation_id: conversationId || undefined,
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col h-[calc(100vh-140px)] gap-4"
    >
      <div className="mb-1">
        <h2 className="text-display-sm font-serif text-foreground tracking-tight">Chat</h2>
        <p className="text-sm text-muted-foreground mt-1">Interact with the multi-agent orchestration system.</p>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-3 min-h-0 pr-1">
        {history.length === 0 && !result && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center justify-center h-full text-center gap-4 py-12"
          >
            <div className="w-12 h-12 rounded-full bg-accent/10 flex items-center justify-center">
              <Bot className="w-6 h-6 text-accent" />
            </div>
            <div>
              <p className="text-heading font-serif text-foreground">Start a conversation</p>
              <p className="text-sm text-muted-foreground mt-1">Send a message to begin interacting with SupportOID</p>
            </div>
          </motion.div>
        )}

        <AnimatePresence>
          {history.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ ...springConfig, delay: i * 0.04 }}
              className={cn("flex gap-3", msg.role === 'user' && 'flex-row-reverse')}
            >
              <div className={cn(
                "w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0",
                msg.role === 'user' ? "bg-accent/15 text-accent" : "bg-muted/60 text-muted-foreground"
              )}>
                {msg.role === 'user' ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
              </div>
              <div className={cn(
                "max-w-[75%] px-4 py-2.5 rounded-xl text-sm whitespace-pre-wrap",
                msg.role === 'user'
                  ? "bg-accent/10 text-foreground rounded-tr-sm"
                  : "bg-card liquid-glass-dark rounded-tl-sm"
              )}>
                {msg.content}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {chatMutation.isPending && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex gap-3"
          >
            <div className="w-7 h-7 rounded-lg bg-muted/60 flex items-center justify-center">
              <Bot className="w-3.5 h-3.5 text-muted-foreground" />
            </div>
            <div className="bg-card liquid-glass-dark px-4 py-3 rounded-xl rounded-tl-sm">
              <div className="flex gap-1">
                {[0, 1, 2].map((dot) => (
                  <motion.div
                    key={dot}
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.2, repeat: Infinity, delay: dot * 0.2 }}
                    className="w-1.5 h-1.5 bg-accent rounded-full"
                  />
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </div>

      {result && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-wrap gap-2 py-2 border-t border-border/30"
        >
          <Pill label="Intent" value={result.intent} />
          <Pill label="Confidence" value={`${(result.confidence * 100).toFixed(1)}%`} accent />
          <Pill label="Tone" value={result.tone} />
          <Pill label="Quality" value={result.quality_score.toFixed(3)} />
          <Pill label="Source" value={result.source} />
          <Pill label="KB hits" value={String(result.kb_results_used)} />
          <Pill label="Time" value={formatDuration(result.processing_time_ms)} />
          {result.should_escalate && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono bg-destructive/10 text-destructive">
              <AlertCircle className="w-3 h-3" />
              Escalated: {result.escalation_reason}
            </span>
          )}
        </motion.div>
      )}

      <div className="relative">
        {conversationId && (
          <div className="flex items-center gap-2 mb-2 text-xs text-muted-foreground">
            <CircleDot className="w-3 h-3 text-accent" />
            <span className="font-mono">{conversationId}</span>
            <button
              onClick={() => setConversationId('')}
              className="text-muted-foreground hover:text-foreground transition-colors"
              aria-label="Clear conversation ID"
            >
              &times;
            </button>
          </div>
        )}
        <form onSubmit={handleSubmit} className="relative">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
            className="w-full px-4 py-3 pr-12 rounded-xl border border-input bg-background/50 text-foreground placeholder:text-muted-foreground/50 focus-ring transition-all resize-none text-sm"
            required
            aria-label="Chat message"
          />
          <motion.button
            type="submit"
            disabled={chatMutation.isPending || !message.trim()}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className={cn(
              "absolute bottom-3 right-3 p-2 rounded-lg transition-colors btn-tactile",
              message.trim() && !chatMutation.isPending
                ? "bg-accent text-accent-foreground shadow-glow-amber-sm"
                : "bg-muted text-muted-foreground"
            )}
            aria-label="Send message"
          >
            <ArrowUp className="w-4 h-4" />
          </motion.button>
        </form>
        {!conversationId && (
          <button
            onClick={() => setConversationId(`conv_${Date.now().toString(36)}`)}
            className="mt-2 text-xs text-muted-foreground hover:text-accent transition-colors font-mono"
          >
            + Start new conversation thread
          </button>
        )}
      </div>
    </motion.div>
  )
}

function Pill({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-mono tracking-wide",
      accent ? "bg-accent/10 text-accent" : "bg-muted/40 text-muted-foreground"
    )}>
      <span className="opacity-60">{label}</span>
      <span className="font-semibold">{value}</span>
    </span>
  )
}
