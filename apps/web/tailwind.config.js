/** @type {import('tailwindcss').Config} */
export default {
    content: ['./index.html', './src/**/*.{js,jsx}'],
    theme: {
      extend: {
        colors: {
          brand: {
            black: '#0a0a0a',
            darkgray: '#111111',
            gray: '#1a1a1a',
            midgray: '#2a2a2a',
            red: '#dc2626',
            redlight: '#ef4444',
            reddark: '#991b1b',
            green: '#16a34a',
            greenlight: '#22c55e',
            greendark: '#14532d',
          },
        },
        fontFamily: {
          display: ['"DM Mono"', 'monospace'],
          body: ['"IBM Plex Sans"', 'sans-serif'],
        },
        animation: {
          'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
          'fade-in': 'fadeIn 0.4s ease-out',
          'slide-up': 'slideUp 0.4s ease-out',
        },
        keyframes: {
          fadeIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
          slideUp: { '0%': { opacity: '0', transform: 'translateY(16px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        },
      },
    },
    plugins: [],
  }
  