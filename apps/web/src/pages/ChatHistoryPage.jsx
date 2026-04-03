// src/pages/ChatHistoryPage.jsx
import React, { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { getSessionHistory, deleteSession, restoreSession } from '../services/api'
import PaginationControls from '../components/PaginationControls'
import { formatWatTime } from '../utils/wat'

async function fetchAllSessions(includeDeleted = false) {
  const { default: api } = await import('../services/api')
  return api.get('/chat/sessions', { params: { limit: 200, include_deleted: includeDeleted } })
}

function timeAgo(ts) {
  if (!ts) return ''
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function DeleteSessionButton({ sessionId, isDeleted, onAction }) {
  const [confirming, setConfirming] = useState(false)
  const [loading, setLoading]       = useState(false)

  const handleClick = async (e) => {
    e.stopPropagation()
    if (isDeleted) {
      setLoading(true)
      try { await restoreSession(sessionId); onAction('restored') }
      finally { setLoading(false) }
      return
    }
    if (!confirming) { setConfirming(true); return }
    setLoading(true)
    try { await deleteSession(sessionId); onAction('deleted') }
    finally { setLoading(false); setConfirming(false) }
  }

  if (isDeleted) {
    return (
      <button
        onClick={handleClick}
        disabled={loading}
        className="font-display text-xs px-2 py-0.5 rounded-sm border border-brand-midgray text-gray-500 hover:text-brand-greenlight hover:border-brand-green transition-colors"
      >
        {loading ? '...' : 'RESTORE'}
      </button>
    )
  }

  return (
    <button
      onClick={handleClick}
      onBlur={() => setTimeout(() => setConfirming(false), 200)}
      disabled={loading}
      className={`font-display text-xs px-2 py-0.5 rounded-sm border transition-colors ${
        confirming
          ? 'border-brand-red text-brand-redlight bg-brand-reddark'
          : 'border-brand-midgray text-gray-600 hover:border-brand-red hover:text-brand-redlight'
      }`}
    >
      {loading ? '...' : confirming ? 'CONFIRM?' : '✕'}
    </button>
  )
}

function SessionCard({ session, onResume, onPreview, active, onAction }) {
  const navigate  = useNavigate()
  const teams     = [...new Set((session.teams_discussed || []).filter(Boolean))].slice(0, 4)
  const sports    = [...new Set((session.sports_discussed || []).filter(Boolean))].slice(0, 3)
  const preds     = (session.predictions_made || []).length
  const msgs      = session.message_count || 0
  const isDeleted = !!session.deleted_at

  return (
    <div
      className={`card border transition-all duration-150 ${
        isDeleted
          ? 'opacity-50 border-brand-midgray'
          : active
          ? 'border-brand-red bg-brand-reddark'
          : 'border-brand-midgray hover:border-gray-500'
      }`}
    >
      {/* ── Clickable summary row ── */}
      <div
        className={`p-3 ${!isDeleted ? 'cursor-pointer' : ''}`}
        onClick={() => !isDeleted && onPreview(session.session_id)}
      >
        {/* Top row: ID + time + delete */}
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-2 min-w-0">
            <div className={`w-2 h-2 rounded-full shrink-0 ${
              isDeleted ? 'bg-brand-midgray' : msgs > 0 ? 'bg-brand-green' : 'bg-brand-midgray'
            }`} />
            <span className="font-display text-xs text-gray-400 truncate">
              {session.session_id.slice(0, 8).toUpperCase()}...
            </span>
            {isDeleted && (
              <span className="font-display text-xs text-gray-700 border border-brand-midgray px-1 rounded-sm shrink-0">
                DEL
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="font-display text-xs text-gray-700">{timeAgo(session.updated_at)}</span>
            <DeleteSessionButton
              sessionId={session.session_id}
              isDeleted={isDeleted}
              onAction={onAction}
            />
          </div>
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-3 mb-2">
          <span className="font-display text-xs text-gray-600">
            MSGS <span className="text-white">{msgs}</span>
          </span>
          {preds > 0 && (
            <span className="font-display text-xs text-gray-600">
              PREDS <span className="text-brand-greenlight">{preds}</span>
            </span>
          )}
          {sports.length > 0 && (
            <span className="font-display text-xs text-gray-700 uppercase ml-auto">
              {sports.join(' · ')}
            </span>
          )}
        </div>

        {/* Teams */}
        {teams.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {teams.map(t => <span key={t} className="tag-gray text-xs">{t}</span>)}
          </div>
        )}
      </div>

      {/* ── Resume button — always visible, full-width, outside click area ── */}
      {!isDeleted && (
        <div className="px-3 pb-3">
          <button
            onClick={(e) => { e.stopPropagation(); onResume(session.session_id) }}
            className="w-full font-display text-xs py-2 rounded-sm border border-brand-midgray text-gray-400
                       hover:border-brand-red hover:text-white hover:bg-brand-reddark
                       active:scale-[0.98] transition-all duration-150 flex items-center justify-center gap-2"
          >
            <span>▶</span> RESUME SESSION
          </button>
        </div>
      )}
    </div>
  )
}

function MessagePreview({ messages }) {
  if (!messages.length) return (
    <div className="flex items-center justify-center h-40">
      <span className="font-display text-xs text-gray-700">NO MESSAGES</span>
    </div>
  )
  return (
    <div className="flex flex-col gap-3 overflow-y-auto pr-1" style={{ maxHeight: 480 }}>
      {messages.map((msg, i) => {
        const isUser = msg.role === 'user'
        return (
          <div key={i} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
            <div className="max-w-[85%]">
              <div className={`flex items-center gap-2 mb-1 ${isUser ? 'justify-end' : ''}`}>
                <span className={`font-display text-xs ${isUser ? 'text-gray-600' : 'text-brand-red'}`}>
                  {isUser ? 'YOU' : '1/1 AI'}
                </span>
                <span className="font-display text-xs text-gray-700">
                  {msg.timestamp
                    ? formatWatTime(msg.timestamp)
                    : ''}
                </span>
              </div>
              <div className={`rounded-sm p-3 text-sm font-body leading-relaxed ${
                isUser
                  ? 'bg-brand-midgray text-white'
                  : 'bg-brand-darkgray border border-brand-midgray text-gray-300'
              }`}>
                {msg.content.length > 300 ? msg.content.slice(0, 300) + '...' : msg.content}
              </div>
              {msg.metadata?.match_id && (
                <div className="mt-1"><span className="tag-green text-xs">PREDICTION ATTACHED</span></div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function ChatHistoryPage() {
  const navigate = useNavigate()
  const [sessions, setSessions]               = useState([])
  const [loading, setLoading]                 = useState(true)
  const [selectedId, setSelectedId]           = useState(null)
  const [previewMessages, setPreviewMessages] = useState([])
  const [previewLoading, setPreviewLoading]   = useState(false)
  const [searchQuery, setSearchQuery]         = useState('')
  const [showDeleted, setShowDeleted]         = useState(false)
  const [showPreviewMobile, setShowPreviewMobile] = useState(false)
  const PAGE_SIZE = 12
  const [page, setPage] = useState(1)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchAllSessions(showDeleted)
      setSessions(res.data || [])
    } catch {
      setSessions([])
    } finally {
      setLoading(false)
    }
  }, [showDeleted])

  useEffect(() => { load() }, [load])

  const handlePreview = async (sessionId) => {
    if (selectedId === sessionId) {
      setSelectedId(null)
      setPreviewMessages([])
      setShowPreviewMobile(false)
      return
    }
    setSelectedId(sessionId)
    setShowPreviewMobile(true)
    setPreviewLoading(true)
    try {
      const res = await getSessionHistory(sessionId, 50)
      setPreviewMessages(res.data.messages || [])
    } catch {
      setPreviewMessages([])
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleAction = () => load()

  useEffect(() => {
    setPage(1)
  }, [searchQuery, showDeleted])

  const filtered = sessions.filter(s => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return (
      (s.teams_discussed || []).join(' ').toLowerCase().includes(q) ||
      (s.sports_discussed || []).join(' ').toLowerCase().includes(q) ||
      s.session_id.includes(q)
    )
  })

  const totalPredictions = sessions.filter(s => !s.deleted_at)
    .reduce((sum, s) => sum + (s.predictions_made?.length || 0), 0)
  const totalMessages = sessions.filter(s => !s.deleted_at)
    .reduce((sum, s) => sum + (s.message_count || 0), 0)
  const deletedCount = sessions.filter(s => s.deleted_at).length

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const pagedSessions = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-xl text-white tracking-wide">CHAT HISTORY</h1>
          <p className="font-body text-xs text-gray-600 mt-1">
            Click to preview · ✕ to soft-delete · RESTORE to recover
          </p>
        </div>
        <button onClick={() => navigate('/chat')} className="btn-primary">NEW CHAT</button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[
          { label: 'SESSIONS',    value: sessions.filter(s => !s.deleted_at).length },
          { label: 'MESSAGES',    value: totalMessages },
          { label: 'PREDICTIONS', value: totalPredictions },
          { label: 'DELETED',     value: deletedCount },
        ].map(({ label, value }) => (
          <div key={label} className="card p-3 text-center">
            <p className="label mb-1">{label}</p>
            <p className="font-display text-2xl text-white">{value}</p>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="flex gap-3 mb-4 items-center">
        <input
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder="Search by team, sport, or session ID..."
          className="flex-1 bg-brand-gray border border-brand-midgray focus:border-brand-red outline-none
                     text-white font-body text-sm px-4 py-2 rounded-sm placeholder-gray-700 transition-colors"
        />
        <button
          onClick={() => setShowDeleted(v => !v)}
          className={`font-display text-xs px-3 py-2 rounded-sm border transition-colors whitespace-nowrap ${
            showDeleted
              ? 'bg-brand-midgray border-gray-500 text-white'
              : 'border-brand-midgray text-gray-500 hover:text-white'
          }`}
        >
          {showDeleted ? 'HIDE DELETED' : 'SHOW DELETED'}
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-40 gap-2">
          <div className="w-4 h-4 border-2 border-brand-red border-t-transparent rounded-full animate-spin" />
          <span className="font-display text-xs text-gray-500">LOADING SESSIONS...</span>
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-8 text-center">
          <p className="font-display text-sm text-gray-600">
            {searchQuery ? 'NO SESSIONS MATCH YOUR SEARCH' : 'NO CHAT HISTORY YET'}
          </p>
          {!searchQuery && (
            <button onClick={() => navigate('/chat')} className="btn-primary mt-4">
              START CHATTING
            </button>
          )}
        </div>
      ) : (
        /* ── Responsive two-panel layout ── */
        <div className="flex flex-col lg:flex-row gap-4">

          {/* Session list — full width on mobile, fixed 280px on desktop */}
          <div className={`
            flex flex-col gap-2
            lg:w-72 lg:shrink-0
            ${showPreviewMobile && selectedId ? 'hidden lg:flex' : 'flex'}
          `}>
            <div className="flex flex-col gap-2 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 360px)' }}>
              {pagedSessions.map(session => (
                <SessionCard
                  key={session.session_id}
                  session={session}
                  onResume={(id) => navigate(`/chat?session=${id}`)}
                  onPreview={handlePreview}
                  active={selectedId === session.session_id}
                  onAction={handleAction}
                />
              ))}
            </div>
            <div className="card overflow-hidden">
              <PaginationControls
                currentPage={safePage}
                totalItems={filtered.length}
                pageSize={PAGE_SIZE}
                onPageChange={setPage}
                itemLabel="SESSIONS"
              />
            </div>
          </div>

          {/* Preview panel — always visible on desktop, overlay on mobile when session selected */}
          <div className={`
            flex-1 card p-4
            ${selectedId && showPreviewMobile ? 'flex flex-col' : selectedId ? 'hidden lg:flex lg:flex-col' : 'hidden lg:flex lg:flex-col'}
          `}>
              {/* Panel header */}
              <div className="flex items-center justify-between mb-4 gap-2">
                <div className="min-w-0">
                  <p className="label">SESSION PREVIEW</p>
                  <p className="font-display text-xs text-gray-700 mt-0.5 truncate">
                    {selectedId?.slice(0, 8).toUpperCase()}... · {previewMessages.length} messages
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {/* Back button — mobile only */}
                  <button
                    onClick={() => {
                      setShowPreviewMobile(false)
                      setSelectedId(null)
                      setPreviewMessages([])
                    }}
                    className="lg:hidden font-display text-xs px-3 py-1.5 rounded-sm border
                               border-brand-midgray text-gray-500 hover:text-white transition-colors"
                  >
                    ← BACK
                  </button>
                  <button
                    onClick={() => selectedId && navigate(`/chat?session=${selectedId}`)}
                    className="btn-primary text-xs px-4 py-1.5"
                  >
                    RESUME →
                  </button>
                </div>
              </div>

              {previewLoading ? (
                <div className="flex items-center justify-center h-40 gap-2">
                  <div className="w-4 h-4 border-2 border-brand-red border-t-transparent rounded-full animate-spin" />
                  <span className="font-display text-xs text-gray-500">LOADING MESSAGES...</span>
                </div>
              ) : (
                <MessagePreview messages={previewMessages} />
              )}
            </div>
        </div>
      )}
    </div>
  )
}