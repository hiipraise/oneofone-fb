// src/components/Layout.jsx
import React from 'react'
import AppNav from './AppNav'

export default function Layout({ children }) {
  return (
    <div className="h-screen bg-brand-black overflow-hidden">
      <main className="h-full overflow-y-auto">
        {/* lg:pl-20 clears the desktop rail; pb-28 clears the mobile tab bar */}
        <div className="p-4 pb-28 md:p-6 md:pb-28 lg:pl-20 lg:pr-6 animate-fade-in">
          {children}
        </div>
      </main>
      <AppNav />
    </div>
  )
}
