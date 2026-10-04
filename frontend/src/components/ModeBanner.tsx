import { useApiClient, useServiceStatus } from '../api/ApiContext.tsx'
import { Icon, type IconName } from './Icon.tsx'

type Tone = 'demo' | 'live' | 'error'

const BANNERS: Readonly<Record<Tone, { icon: IconName; text: string }>> = {
  demo: { icon: 'archive', text: 'Demo data: showing saved example responses, not the live service.' },
  live: { icon: 'live', text: 'Connected to RareBridge · source-linked research records.' },
  error: {
    icon: 'alert',
    text: 'Could not reach RareBridge. Sections that failed show an error and a retry button; no example data is shown in their place.',
  },
}

/** Shown on every screen so nobody mistakes saved examples for live data. */
export function ModeBanner() {
  const client = useApiClient()
  const serviceStatus = useServiceStatus()
  const tone: Tone = client.mode === 'demo' ? 'demo' : serviceStatus === 'unreachable' ? 'error' : 'live'
  const { icon, text } = BANNERS[tone]

  return (
    <div className={`mode-banner mode-banner--${tone}`} role={tone === 'error' ? 'alert' : undefined}>
      <p className="rb-container mode-banner__inner">
        <Icon name={icon} />
        <span>{text}</span>
      </p>
    </div>
  )
}
