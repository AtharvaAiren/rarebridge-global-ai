import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { Contact } from '../api/types.ts'

export type ViewMode = 'patient' | 'expert'
export type ProductPanelName = 'settings' | 'account' | 'contacts' | 'guide'
export type LocalProfile = { displayName: string; organization: string; role: 'patient' | 'caregiver' | 'clinician' | 'researcher' }
type Preferences = { viewMode: ViewMode; textSize: 'standard' | 'large'; reducedMotion: boolean }

const PREFERENCES_KEY = 'rarebridge.preferences.v1'
const PROFILE_KEY = 'rarebridge.local-profile.v1'
const defaults: Preferences = { viewMode: 'patient', textSize: 'standard', reducedMotion: false }

function readPreferences(): Preferences {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(PREFERENCES_KEY) ?? 'null')
    if (!value || typeof value !== 'object') return defaults
    const stored = value as Record<string, unknown>
    return {
      viewMode: stored.viewMode === 'expert' ? 'expert' : 'patient',
      textSize: stored.textSize === 'large' ? 'large' : 'standard',
      reducedMotion: stored.reducedMotion === true,
    }
  } catch { return defaults }
}

function readProfile(): LocalProfile | null {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(PROFILE_KEY) ?? 'null')
    if (!value || typeof value !== 'object') return null
    const profile = value as Record<string, unknown>
    if (typeof profile.displayName !== 'string' || !profile.displayName.trim()) return null
    if (!['patient', 'caregiver', 'clinician', 'researcher'].includes(String(profile.role))) return null
    return {
      displayName: profile.displayName.slice(0, 80),
      organization: typeof profile.organization === 'string' ? profile.organization.slice(0, 120) : '',
      role: profile.role as LocalProfile['role'],
    }
  } catch { return null }
}

type PreferencesValue = Preferences & {
  isExpert: boolean
  setViewMode: (mode: ViewMode) => void
  setTextSize: (size: Preferences['textSize']) => void
  setReducedMotion: (value: boolean) => void
  panel: ProductPanelName | null
  selectedContact: Contact | null
  openPanel: (panel: ProductPanelName, contact?: Contact) => void
  closePanel: () => void
  researchContacts: readonly Contact[]
  setResearchContacts: (contacts: readonly Contact[]) => void
  profile: LocalProfile | null
  saveProfile: (profile: LocalProfile) => void
  clearProfile: () => void
}

const PreferencesContext = createContext<PreferencesValue | null>(null)

/** Presentation choices and an explicitly local demo profile; no authentication or outreach. */
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState(readPreferences)
  const [profile, setProfile] = useState<LocalProfile | null>(readProfile)
  const [panel, setPanel] = useState<ProductPanelName | null>(null)
  const [selectedContact, setSelectedContact] = useState<Contact | null>(null)
  const [researchContacts, setResearchContacts] = useState<readonly Contact[]>([])

  useEffect(() => {
    document.documentElement.dataset.rbViewMode = preferences.viewMode
    document.documentElement.dataset.rbTextSize = preferences.textSize
    document.documentElement.dataset.rbReducedMotion = String(preferences.reducedMotion)
    try { localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences)) } catch { /* preferences still work for this visit */ }
  }, [preferences])
  useEffect(() => {
    try {
      if (profile) localStorage.setItem(PROFILE_KEY, JSON.stringify(profile))
      else localStorage.removeItem(PROFILE_KEY)
    } catch { /* the local preview remains usable without browser storage */ }
  }, [profile])

  const openPanel = useCallback((next: ProductPanelName, contact?: Contact) => {
    setSelectedContact(contact ?? null)
    setPanel(next)
  }, [])
  const closePanel = useCallback(() => setPanel(null), [])
  const setViewMode = useCallback((viewMode: ViewMode) => setPreferences((current) => ({ ...current, viewMode })), [])
  const setTextSize = useCallback((textSize: Preferences['textSize']) => setPreferences((current) => ({ ...current, textSize })), [])
  const setReducedMotion = useCallback((reducedMotion: boolean) => setPreferences((current) => ({ ...current, reducedMotion })), [])
  const saveProfile = useCallback((next: LocalProfile) => setProfile({
    displayName: next.displayName.trim().slice(0, 80),
    organization: next.organization.trim().slice(0, 120),
    role: next.role,
  }), [])
  const clearProfile = useCallback(() => setProfile(null), [])
  const value = useMemo(() => ({
    ...preferences, isExpert: preferences.viewMode === 'expert', setViewMode, setTextSize, setReducedMotion,
    panel, selectedContact, openPanel, closePanel, researchContacts, setResearchContacts,
    profile, saveProfile, clearProfile,
  }), [preferences, panel, selectedContact, researchContacts, profile, setViewMode, setTextSize, setReducedMotion, openPanel, closePanel, saveProfile, clearProfile])
  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>
}

export function usePreferences(): PreferencesValue {
  const value = useContext(PreferencesContext)
  if (!value) throw new Error('usePreferences must be used inside <PreferencesProvider>.')
  return value
}
