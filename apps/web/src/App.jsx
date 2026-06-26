// src/App.jsx
import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import PredictPage from './pages/PredictPage'
import HistoryPage from './pages/HistoryPage'
import MetricsPage from './pages/MetricsPage'
import ChatPage from './pages/ChatPage'
import ChatHistoryPage from './pages/ChatHistoryPage'
import SchedulerPage from './pages/SchedulerPage'
import ReportsPage from './pages/ReportsPage'
import ErrorBoundary from './components/ErrorBoundary'

export default function App() {
  return (
    <ErrorBoundary>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/predict" element={<PredictPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/metrics" element={<MetricsPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/history" element={<ChatHistoryPage />} />
          <Route path="/scheduler" element={<SchedulerPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </ErrorBoundary>
  )
}
