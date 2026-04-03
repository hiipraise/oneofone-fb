// src/pages/ChatPage.jsx
import React, { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { sendChat, getSessionHistory, createSession, deleteSession } from '../services/api'
import PredictionCard from '../components/PredictionCard'
import { useApiContract } from '../hooks/useApiContract'
import { SPORT_LABELS } from '../config/apiContract'
import { formatWatTime } from '../utils/wat'

const SESSION_KEY = 'oneofone_session_id'

const PROMPT_SUGGESTIONS = {
  soccer:     ['Predict Man City vs Arsenal', 'Real Madrid vs Barcelona prediction', 'Liverpool vs Chelsea odds'],
  basketball: ['Predict Lakers vs Celtics', 'Warriors vs Nuggets prediction', 'Bulls vs Heat odds'],
}

// ─── Single message bubble ────────────────────────────────────────────────────
function Message({ msg }) {
  const isUser = msg.role === 'user'
  const normalizedSources = (msg.sources || []).filter(Boolean).slice(0, 3).map((src) => {
    if (typeof src === 'string') {
      return { title: src, link: src, source: null }
    }
    return {
      title: src.title || src.link || 'Source',
      link: src.link || '',
      source: src.source || null,
    }
  })

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4 animate-slide-up`}>
      <div className={`max-w-[82%] ${isUser ? 'order-2' : 'order-1'}`}>
        <div className={`flex items-center gap-2 mb-1 ${isUser ? 'justify-end' : ''}`}>
          <span className={`font-display text-xs ${isUser ? 'text-gray-600' : 'text-brand-red'}`}>
            {isUser ? 'YOU' : '1/1 AI'}
          </span>
          {msg.timestamp && (
            <span className="font-display text-xs text-gray-700">
              {formatWatTime(msg.timestamp)}
            </span>
          )}
        </div>

        <div className={`rounded-sm p-3 ${
          isUser
            ? 'bg-brand-midgray text-white'
            : 'bg-brand-darkgray border border-brand-midgray text-gray-300'
        }`}>
          <p className="font-body text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
        </div>

        {msg.prediction && (
          <div className="mt-3">
            <PredictionCard prediction={msg.prediction} />
          </div>
        )}

        {normalizedSources.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {normalizedSources.map((src, i) => {
              const safeLink = src.link.startsWith('http') ? src.link : `https://${src.link}`
              return (
                <div key={`${src.link}-${i}`} className="inline-flex items-center gap-1">
                  <a
                    href={safeLink}
                    target="_blank" rel="noopener noreferrer"
                    className="font-display text-xs text-gray-700 hover:text-brand-red transition-colors"
                    title={src.title}
                  >
                    [src {i + 1}]
                  </a>
                  {src.source && (
                    <span className="font-display text-[10px] uppercase tracking-wide text-gray-600 border border-brand-midgray px-1 py-0.5 rounded-sm">
                      Source: {src.source}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Typing indicator ─────────────────────────────────────────────────────────
function TypingIndicator({ sport }) {
  const label = sport
    ? `Searching ${SPORT_LABELS[sport] || sport} data and computing prediction...`
    : 'Searching live data and computing prediction...'
  return (
    <div className="flex justify-start mb-4">
      <div className="bg-brand-darkgray border border-brand-midgray rounded-sm p-3 max-w-xs">
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {[0, 1, 2].map(i => (
              <div
                key={i}
                className="w-1.5 h-1.5 rounded-full bg-brand-red animate-bounce"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </div>
          <span className="font-display text-xs text-gray-600">{label}</span>
        </div>
      </div>
    </div>
  )
}

// ─── Memory / session bar ─────────────────────────────────────────────────────
function SessionBar({ summary, sessionId, onNew, onHistory, onDelete }) {
  const [confirmDelete, setConfirmDelete] = useState(false)

  if (!summary) {
    return (
      <div className="card px-3 py-2 flex items-center justify-between">
        <span className="font-display text-xs text-gray-700">NEW SESSION — NO MEMORY YET</span>
        <div className="flex items-center gap-3">
          <button onClick={onHistory} className="font-display text-xs text-gray-600 hover:text-brand-red transition-colors">
            HISTORY
          </button>
        </div>
      </div>
    )
  }

  const teams = [...new Set((summary.teams_discussed || []).filter(Boolean))].slice(0, 4)
  const preds = summary.predictions_made?.length || 0
  const msgs  = summary.message_count || 0

  const handleDelete = async () => {
    if (!confirmDelete) { setConfirmDelete(true); return }
    try {
      await onDelete()
    } finally {
      setConfirmDelete(false)
    }
  }

  return (
    <div className="card px-3 py-2 flex items-center justify-between gap-2 flex-wrap">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-display text-xs text-gray-600">SESSION:</span>
        <span className="font-display text-xs text-gray-500">{msgs} msg{msgs !== 1 ? 's' : ''}</span>
        {preds > 0 && <span className="tag-green">{preds} pred{preds !== 1 ? 's' : ''}</span>}
        {teams.map(t => <span key={t} className="tag-gray">{t}</span>)}
        <span className="font-display text-xs text-gray-700">
          · {sessionId?.slice(0, 8).toUpperCase()}
        </span>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={onHistory}
          className="font-display text-xs text-gray-600 hover:text-white transition-colors"
        >
          HISTORY
        </button>
        <button
          onClick={handleDelete}
          onBlur={() => setTimeout(() => setConfirmDelete(false), 200)}
          className={`font-display text-xs transition-colors ${
            confirmDelete
              ? 'text-brand-redlight'
              : 'text-gray-600 hover:text-brand-redlight'
          }`}
          title="Delete this session"
        >
          {confirmDelete ? 'CONFIRM DELETE?' : 'DELETE'}
        </button>
        <button
          onClick={onNew}
          className="font-display text-xs text-gray-600 hover:text-brand-red transition-colors"
        >
          NEW SESSION
        </button>
      </div>
    </div>
  )
}

// ─── Prompt suggestions ───────────────────────────────────────────────────────
function Suggestions({ sport, onPick }) {
  const suggestions = PROMPT_SUGGESTIONS[sport] || PROMPT_SUGGESTIONS.soccer
  return (
    <div className="flex gap-2 flex-wrap mb-3">
      {suggestions.map(s => (
        <button
          key={s}
          onClick={() => onPick(s)}
          className="font-display text-xs px-3 py-1.5 rounded-sm border border-brand-midgray text-gray-500 hover:text-white hover:border-gray-500 transition-colors"
        >
          {s}
        </button>
      ))}
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function ChatPage() {
  const { contract } = useApiContract()
  const sports = contract.supported_sports
  const chatMessageMax = contract.field_limits.chat_message.max

  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [messages, setMessages]         = useState([])
  const [input, setInput]               = useState('')
  const [loading, setLoading]           = useState(false)
  const [sport, setSport]               = useState('')
  const [sessionId, setSessionId]       = useState(null)
  const [sessionSummary, setSessionSummary] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [showSuggestions, setShowSuggestions] = useState(true)

  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  // ── Session init ────────────────────────────────────────────────────────────
  useEffect(() => {
    const urlSession    = searchParams.get('session')
    const storedSession = localStorage.getItem(SESSION_KEY)
    const target        = urlSession || storedSession

    if (target) {
      setSessionId(target)
      localStorage.setItem(SESSION_KEY, target)
      loadSession(target)
    } else {
      initNewSession()
    }
  }, [])

  // ── Auto-scroll ─────────────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Load existing session ───────────────────────────────────────────────────
  const loadSession = async (sid) => {
    setHistoryLoading(true)
    try {
      const [histRes, sumRes] = await Promise.all([
        getSessionHistory(sid, 100),
        import('../services/api').then(m => m.getSessionSummary(sid)).catch(() => ({ data: null })),
      ])
      const hist = histRes.data.messages || []
      setSessionSummary(sumRes.data || null)

      if (hist.length === 0) {
        setMessages([{
          role: 'assistant',
          content: 'Session loaded. No messages yet — ask me anything about Football or Basketball.',
          timestamp: new Date().toISOString(),
        }])
      } else {
        setShowSuggestions(false)
        setMessages(hist.map(m => ({
          role: m.role, content: m.content,
          timestamp: m.timestamp,
          prediction: m.metadata?.prediction || null,
          sources: [],
        })))
      }
    } catch {
      initNewSession()
    } finally {
      setHistoryLoading(false)
    }
  }

  // ── Create new session ──────────────────────────────────────────────────────
  const initNewSession = async () => {
    setHistoryLoading(false)
    try {
      const res = await createSession()
      const sid = res.data.session_id
      setSessionId(sid)
      localStorage.setItem(SESSION_KEY, sid)
      setSessionSummary(null)
    } catch {}
    setMessages([{
      role: 'assistant',
      content: 'Welcome to 1/1 Sports Prediction AI.\n\nI run real-time web searches and quantitative models to generate calibrated probabilistic predictions.\n\nSupported sports: Football / Soccer · Basketball\n\nAsk me about any upcoming match.',
      timestamp: new Date().toISOString(),
    }])
    setShowSuggestions(true)
  }

  // ── Delete current session and start fresh ──────────────────────────────────
  const handleDeleteSession = async () => {
    if (sessionId) {
      try { await deleteSession(sessionId) } catch {}
    }
    localStorage.removeItem(SESSION_KEY)
    setSessionSummary(null)
    setMessages([])
    setSessionId(null)
    navigate('/chat', { replace: true })
    await initNewSession()
  }

  // ── New session (no delete) ─────────────────────────────────────────────────
  const handleNewSession = async () => {
    localStorage.removeItem(SESSION_KEY)
    setSessionSummary(null)
    setMessages([])
    setSessionId(null)
    navigate('/chat', { replace: true })
    await initNewSession()
  }

  // ── Refresh summary ─────────────────────────────────────────────────────────
  const refreshSummary = useCallback(async (sid) => {
    try {
      const { getSessionSummary } = await import('../services/api')
      const res = await getSessionSummary(sid)
      setSessionSummary(res.data)
    } catch {}
  }, [])

  // ── Submit message ──────────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e?.preventDefault()
    const msg = input.trim()
    if (!msg || loading) return

    setShowSuggestions(false)
    setMessages(prev => [...prev, {
      role: 'user', content: msg, timestamp: new Date().toISOString(),
    }])
    setInput('')
    setLoading(true)

    try {
      const res = await sendChat({
        message: msg,
        sport: sport || undefined,
        session_id: sessionId,
      })
      const data = res.data

      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id)
        localStorage.setItem(SESSION_KEY, data.session_id)
      }

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response,
        prediction: data.prediction || null,
        sources: data.sources || [],
        timestamp: data.timestamp || new Date().toISOString(),
      }])

      await refreshSummary(data.session_id || sessionId)
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err.response?.data?.detail || 'Failed to reach prediction engine. Please try again.'}`,
        timestamp: new Date().toISOString(),
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const handleSuggestion = (text) => {
    setInput(text)
    inputRef.current?.focus()
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="flex flex-col h-full max-h-[calc(100vh-120px)] animate-fade-in">

      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div>
          <h1 className="font-display text-xl text-white tracking-wide">AI PREDICTION CHAT</h1>
          <p className="font-body text-xs text-gray-600 mt-0.5">
            Groq LLM · live web search · persistent memory · {sports.map((s) => SPORT_LABELS[s] || s).join(', ')}
          </p>
        </div>

        {/* Sport selector */}
        <select
          value={sport}
          onChange={e => setSport(e.target.value)}
          className="bg-brand-gray border border-brand-midgray text-gray-400 font-display text-xs px-3 py-2 rounded-sm outline-none focus:border-brand-red transition-colors"
        >
          <option value="">All Sports</option>
          {sports.map(s => (
            <option key={s} value={s}>{SPORT_LABELS[s] || s}</option>
          ))}
        </select>
      </div>

      {/* ── Session bar ── */}
      <div className="shrink-0 mb-3">
        {historyLoading ? (
          <div className="card px-3 py-2 flex items-center gap-2">
            <div className="w-3 h-3 border border-brand-red border-t-transparent rounded-full animate-spin" />
            <span className="font-display text-xs text-gray-700">LOADING SESSION...</span>
          </div>
        ) : (
          <SessionBar
            summary={sessionSummary}
            sessionId={sessionId}
            onNew={handleNewSession}
            onHistory={() => navigate('/chat/history')}
            onDelete={handleDeleteSession}
          />
        )}
      </div>

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto card p-4 mb-4">
        {messages.map((msg, i) => <Message key={i} msg={msg} />)}
        {loading && <TypingIndicator sport={sport || undefined} />}
        <div ref={bottomRef} />
      </div>

      {/* ── Suggestions (only when fresh session) ── */}
      {showSuggestions && !loading && messages.length <= 1 && (
        <div className="shrink-0 mb-2">
          <Suggestions
            sport={sport || 'soccer'}
            onPick={handleSuggestion}
          />
        </div>
      )}

      {/* ── Input ── */}
      <form onSubmit={handleSubmit} className="flex gap-2 shrink-0">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          maxLength={chatMessageMax}
          placeholder={
            sport
              ? `Ask about ${SPORT_LABELS[sport]} — e.g. "${PROMPT_SUGGESTIONS[sport]?.[0] || 'Predict a match'}"`
              : 'Ask for a prediction, e.g. "Predict Chelsea vs Liverpool"'
          }
          disabled={loading}
          className="flex-1 bg-brand-gray border border-brand-midgray focus:border-brand-red outline-none text-white font-body text-sm px-4 py-2.5 rounded-sm placeholder-gray-700 transition-colors disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="btn-primary px-6 shrink-0"
        >
          {loading
            ? <span className="w-4 h-4 border border-white border-t-transparent rounded-full animate-spin block" />
            : 'SEND'}
        </button>
      </form>

      {/* Character hint */}
      {input.length > 0 && (
        <p className="font-display text-xs text-gray-700 mt-1 text-right">
          {input.length}/{chatMessageMax} · Enter to send · Shift+Enter for new line
        </p>
      )}
    </div>
  )
}
