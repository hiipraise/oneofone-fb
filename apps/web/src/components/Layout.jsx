// src/components/Layout.jsx
import React from 'react'
import FloatingBentoNav from './FloatingBentoNav'

export default function Layout({ children }) {
  return (
    <div className="h-screen bg-brand-black overflow-hidden">
      <main className="h-full overflow-y-auto">
        <div className="p-4 pb-28 md:p-6 md:pb-28 animate-fade-in">
          {children}
        </div>
      </main>
      <FloatingBentoNav />
    </div>
  )
}
