import { useHealth } from '../app/HealthContext.tsx'
import { Icon } from './Icon.tsx'

const SNAPSHOT_DISPLAY_LENGTH = 7

function ServiceLine() {
  const { state, retry } = useHealth()
  switch (state.status) {
    case 'idle':
    case 'loading':
      return <p>Checking the data service…</p>
    case 'error':
      return (
        <p className="app-footer__service">
          Service check failed: {state.error.message}{' '}
          <button type="button" className="rb-btn rb-btn--quiet" onClick={retry}>
            <Icon name="retry" />
            Check again
          </button>
        </p>
      )
    case 'success':
      return <p>Data snapshot {state.data.data_snapshot.slice(0, SNAPSHOT_DISPLAY_LENGTH)}.</p>
  }
}

export function AppFooter() {
  return (
    <footer className="app-footer">
      <div className="rb-container app-footer__inner">
        <p>
          Disease records from DisMech (Monarch Initiative), CC BY 4.0. DisMech is AI-curated and incomplete; a
          missing record here does not mean nothing exists.
        </p>
        <p>Not medical advice. Statuses describe what cited sources say, not clinical validation.</p>
        <ServiceLine />
      </div>
    </footer>
  )
}
