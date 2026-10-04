import { Component, type ErrorInfo, type ReactNode } from 'react'

type ErrorBoundaryProps = {
  children: ReactNode
  /** Changing this key (for example the route) clears a caught error. */
  resetKey: string
}

type ErrorBoundaryState = { error: Error | null; resetKey: string }

/**
 * Keeps an unexpected rendering error from blanking the whole app. React has
 * no function-component equivalent, so this one class is deliberate.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null, resetKey: this.props.resetKey }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { error }
  }

  static getDerivedStateFromProps(props: ErrorBoundaryProps, state: ErrorBoundaryState): Partial<ErrorBoundaryState> | null {
    return props.resetKey !== state.resetKey ? { error: null, resetKey: props.resetKey } : null
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('RareBridge view failed to render', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <main id="main" className="rb-container view" tabIndex={-1}>
        <div className="state state--error" role="alert">
          <div className="state__body">
            <p className="state__title">This view could not be shown</p>
            <p>Something unexpected went wrong while drawing this page. No data was changed.</p>
            <p className="rb-meta">{this.state.error.message}</p>
            <button type="button" className="rb-btn rb-btn--quiet state__retry" onClick={() => this.setState({ error: null })}>
              Try again
            </button>
          </div>
        </div>
      </main>
    )
  }
}
