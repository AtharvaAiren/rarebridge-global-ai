import type { ApiError } from '../api/errors.ts'
import { Icon } from './Icon.tsx'

type LoadingStateProps = {
  label: string
}

export function LoadingState({ label }: LoadingStateProps) {
  return (
    <p className="state state--loading" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </p>
  )
}

type ErrorCopy = { title: string; body: string; canRetry: boolean }

function errorCopy(error: ApiError): ErrorCopy {
  switch (error.kind) {
    case 'demo_missing':
      return {
        title: 'Not available in demo data',
        body: 'There is no saved example response for this request. Start the local RareBridge service for live data, or open one of the demonstration diseases.',
        canRetry: false,
      }
    case 'network':
      return {
        title: 'Could not reach the RareBridge service',
        body: 'Nothing is shown in place of the missing data. Check that the local service is running, then try again.',
        canRetry: true,
      }
    case 'invalid_response':
      return { title: 'The service sent an unexpected response', body: error.message, canRetry: true }
    case 'http':
      return error.status === 404
        ? { title: 'Not found in this collection', body: error.message, canRetry: true }
        : { title: 'The service could not complete this request', body: error.message, canRetry: true }
  }
}

type ErrorStateProps = {
  error: ApiError
  onRetry: () => void
}

/** In-place error: says what failed, never substitutes example data. */
export function ErrorState({ error, onRetry }: ErrorStateProps) {
  const { title, body, canRetry } = errorCopy(error)
  const isNeutral = error.kind === 'demo_missing'

  return (
    <div className={`state ${isNeutral ? 'state--neutral' : 'state--error'}`} role="alert">
      <Icon name={isNeutral ? 'info' : 'alert'} className="state__icon" />
      <div className="state__body">
        <p className="state__title">{title}</p>
        <p>{body}</p>
        {error.kind === 'http' && <p className="rb-meta">Error code: {error.code}</p>}
        {canRetry && (
          <button type="button" className="rb-btn rb-btn--quiet state__retry" onClick={onRetry}>
            <Icon name="retry" />
            Try again
          </button>
        )}
      </div>
    </div>
  )
}
