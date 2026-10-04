import { useEffect, useRef, useState, type FormEvent } from 'react'
import { usePreferences, type LocalProfile } from '../app/PreferencesContext.tsx'
import { safeExternalUrl, urlHost } from '../domain/urls.ts'
import { routeHash } from '../routing.ts'
import { Icon } from './Icon.tsx'
import { ReviewBadge } from './StatusChip.tsx'

const panelTitles = { settings: 'Make RareBridge yours', account: 'Your account', contacts: 'People to approach', guide: 'From a question to a next step' }

export function ProductPanel() {
  const { panel, closePanel } = usePreferences()
  if (!panel) return null
  return <PanelDialog key={panel} panel={panel} closePanel={closePanel} />
}

function PanelDialog({ panel, closePanel }: { panel: keyof typeof panelTitles; closePanel: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const element = dialog.current
    element?.showModal()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      element?.close()
      document.body.style.overflow = previousOverflow
      previouslyFocused?.focus({ preventScroll: true })
    }
  }, [])
  return (
    <dialog ref={dialog} className="product-panel" aria-labelledby="product-panel-title" onCancel={(event) => { event.preventDefault(); closePanel() }} onClick={(event) => {
      if (event.target !== event.currentTarget) return
      const bounds = event.currentTarget.getBoundingClientRect()
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) closePanel()
    }}>
      <div className="product-panel__heading">
        <div><p className="rb-label">RareBridge</p><h2 id="product-panel-title">{panelTitles[panel]}</h2></div>
        <button type="button" className="product-icon-button" onClick={closePanel} aria-label="Close window" autoFocus><Icon name="x" /></button>
      </div>
      <div className="product-panel__body">
        {panel === 'settings' && <Settings />}
        {panel === 'account' && <Account />}
        {panel === 'contacts' && <Contacts />}
        {panel === 'guide' && <Guide />}
      </div>
    </dialog>
  )
}

function Settings() {
  const { viewMode, setViewMode, textSize, setTextSize, reducedMotion, setReducedMotion } = usePreferences()
  return (
    <div className="product-settings">
      <p className="product-panel__intro">Choose how much detail you see. Sources and unanswered questions stay available in both views.</p>
      <fieldset className="product-fieldset"><legend>Reading mode</legend>
        <label className="product-choice"><input type="radio" name="reading-mode" checked={viewMode === 'patient'} onChange={() => setViewMode('patient')} /><span><strong>Patient / simple</strong><small>Plain explanations, practical questions, and the next step.</small></span></label>
        <label className="product-choice"><input type="radio" name="reading-mode" checked={viewMode === 'expert'} onChange={() => setViewMode('expert')} /><span><strong>Doctor / expert</strong><small>More identifiers, research terminology, and provenance.</small></span></label>
      </fieldset>
      <fieldset className="product-fieldset"><legend>Text size</legend>
        <div className="product-mode" role="group" aria-label="Text size"><button type="button" aria-pressed={textSize === 'standard'} onClick={() => setTextSize('standard')}>Standard</button><button type="button" aria-pressed={textSize === 'large'} onClick={() => setTextSize('large')}>Larger</button></div>
      </fieldset>
      <label className="product-choice product-choice--standalone"><input type="checkbox" checked={reducedMotion} onChange={(event) => setReducedMotion(event.target.checked)} /><span><strong>Reduce motion</strong><small>Keep transitions and the research map calmer. Your device’s motion setting is also respected.</small></span></label>
      <p className="rb-meta">Preferences apply on this browser. Switching modes changes the presentation of the same research records.</p>
    </div>
  )
}

function Account() {
  const { profile, saveProfile, clearProfile } = usePreferences()
  const [tab, setTab] = useState<'login' | 'signup' | 'manage'>(profile ? 'manage' : 'login')
  const [displayName, setDisplayName] = useState(profile?.displayName ?? '')
  const [organization, setOrganization] = useState(profile?.organization ?? '')
  const [role, setRole] = useState<LocalProfile['role']>(profile?.role ?? 'caregiver')
  const [notice, setNotice] = useState('')
  const save = (event: FormEvent) => {
    event.preventDefault()
    if (!displayName.trim()) return
    saveProfile({ displayName, organization, role })
    setTab('manage')
    setNotice('Your local profile is ready for this visit. When browser storage is available, it also stays on this device.')
  }
  return (
    <>
      <p className="product-preview-label"><Icon name="info" /> Account preview · local profile</p>
      <p className="product-panel__intro">Try an account experience using a display name and role. This prototype stores a local profile on this browser; it has no authentication or cloud account.</p>
      <div className="product-tabs" role="group" aria-label="Account options">
        <button type="button" aria-pressed={tab === 'login'} onClick={() => { setTab('login'); setNotice('') }}>Log in · preview</button>
        <button type="button" aria-pressed={tab === 'signup'} onClick={() => { setTab('signup'); setNotice('') }}>Sign up · preview</button>
        {profile && <button type="button" aria-pressed={tab === 'manage'} onClick={() => { setTab('manage'); setDisplayName(profile.displayName); setOrganization(profile.organization); setRole(profile.role); setNotice('') }}>Manage profile</button>}
      </div>
      {tab === 'login' ? (
        <div className="product-account-preview">
          <h3>{profile ? `Welcome back, ${profile.displayName}` : 'Explore with a demo profile'}</h3>
          <p>{profile ? 'Your saved local profile is available in this browser.' : 'Open a sample caregiver profile, or create your own local display profile.'}</p>
          <button type="button" className="rb-btn rb-btn--primary" onClick={() => {
            const next: LocalProfile = profile ?? { displayName: 'Alex', organization: 'Demo patient organization', role: 'caregiver' }
            saveProfile(next); setDisplayName(next.displayName); setOrganization(next.organization); setRole(next.role); setTab('manage'); setNotice('Demo profile opened. No authentication was performed.')
          }}>{profile ? 'Open local profile' : 'Try demo account'}</button>
        </div>
      ) : (
        <form className="product-form" onSubmit={save}>
          <label>Display name<input required maxLength={80} autoComplete="off" value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="For example, Alex" /></label>
          <label>Organization <span className="rb-meta">(optional)</span><input maxLength={120} autoComplete="off" value={organization} onChange={(event) => setOrganization(event.target.value)} placeholder="Patient group or research team" /></label>
          <label>My role<select value={role} onChange={(event) => setRole(event.target.value as LocalProfile['role'])}><option value="patient">Patient</option><option value="caregiver">Family member / caregiver</option><option value="clinician">Doctor / clinician</option><option value="researcher">Researcher</option></select></label>
          <div className="rb-cluster"><button className="rb-btn rb-btn--primary" type="submit">{tab === 'signup' ? 'Create local profile' : 'Save local profile'}</button>
            {tab === 'manage' && <button type="button" className="rb-btn rb-btn--quiet" onClick={() => { clearProfile(); setDisplayName(''); setOrganization(''); setRole('caregiver'); setTab('login'); setNotice('Local profile removed from this visit and browser storage where available.') }}>Remove local profile</button>}
          </div>
        </form>
      )}
      {notice && <p className="product-notice" role="status"><Icon name="check" />{notice}</p>}
      <p className="rb-meta">Use a display name. This preview does not need passwords, medical details, or identity documents.</p>
    </>
  )
}

function Contacts() {
  const { researchContacts, selectedContact, closePanel, isExpert } = usePreferences()
  const [selectedId, setSelectedId] = useState<string | null>(selectedContact?.id ?? null)
  const [topic, setTopic] = useState('Discuss the open questions about using a research resource')
  const [format, setFormat] = useState('Research conversation')
  const [draft, setDraft] = useState('')
  // Current assessment contacts take precedence over an overview contact opened from a row.
  const contacts = [...researchContacts, ...(selectedContact ? [selectedContact] : [])].filter((contact, index, all) => all.findIndex((item) => item.id === contact.id) === index)
  const selected = contacts.find((contact) => contact.id === selectedId) ?? null
  const saveDraft = (event: FormEvent) => {
    event.preventDefault()
    if (!selected) return
    setDraft(`${format} — local preview\nPublic contact: ${selected.label}\nProposed topic: ${topic.trim()}\nNext step: visit the public page to ask whether this is the right team and how to arrange a discussion.\nNo appointment has been booked and no message has been sent.`)
  }
  return (
    <>
      <p className="product-panel__intro">Start with a public patient organization, researcher, or study team. The recorded role and source review help you decide whom to approach.</p>
      {contacts.length === 0 ? <div className="product-empty"><Icon name="person" /><h3>First, choose a condition</h3><p>Open a demonstration condition to see its recorded public contacts alongside the research resources.</p><a className="rb-btn rb-btn--primary" href={routeHash({ name: 'home' })} onClick={closePanel}>Explore conditions<Icon name="arrowRight" /></a></div> :
        <ul className="product-contact-list">{contacts.map((contact) => {
          const url = safeExternalUrl(contact.url)
          return <li key={contact.id}><p className="rb-label">{contact.kind.replace(/_/g, ' ')}</p><h3>{contact.label}</h3><p>{contact.role}</p><ReviewBadge status={contact.review_status} /><p className="rb-meta">{contact.last_checked ? `Last source review: ${contact.last_checked}` : 'Source review is pending'}</p>
            {contact.all_sources_withdrawn && <p className="product-contact-warning"><Icon name="info" />Every supporting source for this contact is hidden in the current assessment. The recorded review history remains visible.</p>}
            {isExpert ? <p className="rb-meta">Recorded source IDs: {contact.source_ids.join(', ') || 'None recorded'}</p> : <details className="product-disclosure"><summary>Source record for this contact</summary><p>Recorded source IDs: {contact.source_ids.join(', ') || 'None recorded'}</p></details>}
            <div className="rb-cluster">{url && <a className="rb-btn rb-btn--quiet" href={url} target="_blank" rel="noopener noreferrer">Public page · {urlHost(url)}<Icon name="external" /></a>}<button className="rb-btn rb-btn--quiet" type="button" onClick={() => { setSelectedId(contact.id); setDraft('') }} aria-pressed={selected?.id === contact.id}>Plan a discussion · Preview</button></div>
          </li>
        })}</ul>}
      {selected && <section className="product-planner" aria-labelledby="planner-title"><p className="product-preview-label"><Icon name="clock" />Appointment planner · Preview</p><h3 id="planner-title">Prepare a discussion with {selected.label}</h3><p>Build a local outline before contacting the public team. Clinical services and appointment availability have not been verified.</p>{selected.all_sources_withdrawn && <p className="product-contact-warning">The contact’s supporting sources are hidden in this view. Confirm the current role and public contact route before using this outline.</p>}
        <form className="product-form" onSubmit={saveDraft}><label>Type of discussion<select value={format} onChange={(event) => { setFormat(event.target.value); setDraft('') }}><option>Research conversation</option><option>Clinical appointment inquiry</option></select></label><label>Question to ask<textarea required maxLength={600} rows={3} value={topic} onChange={(event) => { setTopic(event.target.value); setDraft('') }} /></label><button type="submit" className="rb-btn rb-btn--primary">Create local discussion outline</button></form>
        {draft && <div className="product-notice product-notice--stacked" role="status"><strong>Draft ready · nothing sent or booked</strong><pre>{draft}</pre></div>}
      </section>}
    </>
  )
}

function Guide() {
  const { closePanel } = usePreferences()
  return <><p className="product-panel__intro">RareBridge helps patient organizations work out whether an existing research resource could help with their particular goal.</p><ol className="product-guide">
    <li><span>01</span><div><h3>Choose a condition and goal</h3><p>For this prototype, the goal is planning a study that follows how a condition changes over time.</p></div></li>
    <li><span>02</span><div><h3>Explore resources and connections</h3><p>A shared study method can be a useful lead. A relationship between conditions alone does not establish that a resource will work for your group.</p></div></li>
    <li><span>03</span><div><h3>Read what is supported and what is open</h3><p>Inspect the sources and the checks about participants, access, and feasibility. Hide a source to see which checks depended on it.</p></div></li>
    <li><span>04</span><div><h3>Prepare a collaboration brief</h3><p>Take the resource, supporting evidence, unanswered questions, and a public contact route into a draft that you can review and share yourself.</p></div></li>
  </ol><a className="rb-btn rb-btn--primary" href={routeHash({ name: 'home' })} onClick={closePanel}>Explore the collection<Icon name="arrowRight" /></a></>
}
