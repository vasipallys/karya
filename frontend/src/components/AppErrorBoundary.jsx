import { Component } from 'react'

export default class AppErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Keep diagnostics available to desktop/browser logs without exposing a
    // stack trace in the UI.
    console.error('Uncaught application render error', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children
    return <main className="fatal-error" role="alert">
      <div>
        <h1>Karya couldn’t render this screen</h1>
        <p>Your saved data is unaffected. Reload the application; if the issue continues, share the browser or desktop logs with support.</p>
        <button className="m3-btn filled" onClick={() => window.location.reload()}>Reload application</button>
      </div>
    </main>
  }
}
