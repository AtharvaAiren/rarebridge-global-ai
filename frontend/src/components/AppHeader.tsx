import wordmarkDark from '../assets/brand/wordmark-dark.png'
import wordmarkLight from '../assets/brand/wordmark-light.png'
import { usePreferences } from '../app/PreferencesContext.tsx'
import { routeHash } from '../routing.ts'
import { Icon } from './Icon.tsx'

const WORDMARK_WIDTH = 345
const WORDMARK_HEIGHT = 139

export function AppHeader() {
  const { viewMode, setViewMode, openPanel, profile } = usePreferences()
  return (
    <header className="app-header">
      <div className="rb-container app-header__inner">
        <a className="app-header__brand" href={routeHash({ name: 'home' })}>
          <picture>
            <source srcSet={wordmarkDark} media="(prefers-color-scheme: dark)" />
            <img src={wordmarkLight} alt="RareBridge home" width={WORDMARK_WIDTH} height={WORDMARK_HEIGHT} />
          </picture>
        </a>
        <nav className="product-nav" aria-label="Main navigation">
          <a href={routeHash({ name: 'home' })}>Explore</a>
          <button type="button" onClick={() => openPanel('guide')}>How it works</button>
          <button type="button" onClick={() => openPanel('contacts')}>Doctor & contacts</button>
        </nav>
        <div className="product-header-tools">
          <div className="product-mode" role="group" aria-label="Reading mode">
            <button type="button" aria-pressed={viewMode === 'patient'} onClick={() => setViewMode('patient')}>Patient / simple</button>
            <button type="button" aria-pressed={viewMode === 'expert'} onClick={() => setViewMode('expert')}>Doctor / expert</button>
          </div>
          <button className="product-icon-button" type="button" onClick={() => openPanel('settings')} aria-label="Open settings" title="Settings">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /><circle cx="9" cy="6" r="2" /><circle cx="15" cy="12" r="2" /><circle cx="9" cy="18" r="2" /></svg>
          </button>
          <button className="product-account-button" type="button" onClick={() => openPanel('account')} aria-label={profile?.displayName ?? 'Account'}>
            <Icon name="person" /><span>{profile ? profile.displayName : 'Account'}</span>
          </button>
        </div>
      </div>
    </header>
  )
}
