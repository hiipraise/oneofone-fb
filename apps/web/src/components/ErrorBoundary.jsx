import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('[UI ErrorBoundary]', error, info)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div className="min-h-[60vh] flex items-center justify-center p-4">
        <section className="card w-full max-w-lg p-6 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-brand-red bg-brand-reddark text-brand-redlight">
            !
          </div>
          <h1 className="font-display text-lg tracking-wide text-white">SCHOLARA VIEW RECOVERY</h1>
          <p className="mt-2 font-body text-sm leading-6 text-gray-500">
            This workspace hit an unexpected rendering state. Your data was not changed; reset the view or return to the dashboard.
          </p>
          {this.state.error?.message && (
            <p className="mt-3 rounded-sm border border-brand-midgray bg-brand-black px-3 py-2 font-display text-xs text-gray-600 break-words">
              {this.state.error.message}
            </p>
          )}
          <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:justify-center">
            <button type="button" onClick={this.handleReset} className="btn-primary min-h-12">
              RESET VIEW
            </button>
            <a href="/" className="btn-ghost inline-flex min-h-12 items-center justify-center">
              DASHBOARD
            </a>
          </div>
        </section>
      </div>
    )
  }
}
