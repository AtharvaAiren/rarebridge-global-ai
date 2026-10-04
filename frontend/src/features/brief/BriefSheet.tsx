import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useApiClient } from '../../api/ApiContext.tsx'
import type { AssessmentResponse } from '../../api/types.ts'
import { Icon } from '../../components/Icon.tsx'
import { ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { briefFileName, briefToText, buildBrief, defaultDraft } from '../../domain/brief.ts'
import type { EvidenceState } from '../evidence/useAssessment.ts'
import { BriefDocument } from './BriefDocument.tsx'

const STATUS_CLEAR_MS = 4000
/** A pending permission prompt can leave the Clipboard API unsettled; don't wait forever. */
const CLIPBOARD_TIMEOUT_MS = 1500
const BODY_CLASS = 'has-brief'

type BriefSheetProps = {
  evidence: EvidenceState
  onClose: () => void
}

/**
 * The brief as a document sheet over the page. The page underneath is inert,
 * so the hidden-source state cannot change while the brief is open.
 */
export function BriefSheet({ evidence, onClose }: BriefSheetProps) {
  // Make the page behind inert, lock its scroll, and restore focus on close.
  useEffect(() => {
    const root = document.getElementById('root')
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    root?.setAttribute('inert', '')
    document.body.classList.add(BODY_CLASS)
    return () => {
      root?.removeAttribute('inert')
      document.body.classList.remove(BODY_CLASS)
      opener?.focus()
    }
  }, [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const content = evidence.error ? (
    <div className="brief-sheet__state">
      <ErrorState error={evidence.error} onRetry={evidence.retry} />
    </div>
  ) : evidence.current ? (
    <BriefContent key={evidence.hidden.join('|')} assessment={evidence.current} hidden={evidence.hidden} onClose={onClose} />
  ) : (
    <div className="brief-sheet__state">
      <LoadingState label="Preparing the brief from the current assessment…" />
    </div>
  )

  return createPortal(
    <div className="brief-sheet" role="dialog" aria-modal="true" aria-labelledby="brief-title">
      {content}
      {!evidence.current && (
        <button type="button" className="rb-btn rb-btn--quiet brief-sheet__close-alone" onClick={onClose}>
          Close
        </button>
      )}
    </div>,
    document.body,
  )
}

type BriefContentProps = {
  assessment: AssessmentResponse
  hidden: readonly string[]
  onClose: () => void
}

function BriefContent({ assessment, hidden, onClose }: BriefContentProps) {
  const client = useApiClient()
  const [preparedOn] = useState(() => new Date())
  const model = useMemo(
    () => buildBrief({ assessment, hidden, preparedOn, dataMode: client.mode }),
    [assessment, hidden, preparedOn, client.mode],
  )
  const [draft, setDraft] = useState(() => defaultDraft(model))
  const [status, setStatus] = useState('')
  const statusTimer = useRef(0)

  useEffect(() => {
    document.getElementById('brief-title')?.focus()
    return () => window.clearTimeout(statusTimer.current)
  }, [])

  const announce = (message: string) => {
    setStatus(message)
    window.clearTimeout(statusTimer.current)
    statusTimer.current = window.setTimeout(() => setStatus(''), STATUS_CLEAR_MS)
  }

  const copy = async (text: string, what: string) => {
    const isCopied = (await copyWithClipboardApi(text)) || copyWithSelection(text)
    announce(isCopied ? `${what} copied.` : 'Copying is blocked in this browser. Use "Download as text" instead.')
  }

  const download = () => {
    const blob = new Blob([briefToText(model, draft)], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = briefFileName(model)
    link.click()
    URL.revokeObjectURL(url)
    announce(`Downloaded ${link.download}.`)
  }

  const draftEditor = (
    <div className="brief-draft">
      <label htmlFor="brief-draft" className="rb-label">
        Your message (addressed to a role, not a named person)
      </label>
      <textarea
        id="brief-draft"
        className="rb-input brief-draft__text"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        rows={14}
      />
      <div className="rb-cluster">
        <button type="button" className="rb-btn rb-btn--quiet" onClick={() => copy(draft, 'Message')}>
          Copy message only
        </button>
        <button type="button" className="rb-btn rb-btn--quiet" onClick={() => setDraft(defaultDraft(model))}>
          Reset draft
        </button>
      </div>
    </div>
  )

  return (
    <>
      <div className="brief-sheet__bar">
        <div className="brief-sheet__bar-inner">
          <p className="brief-sheet__bar-title">Collaboration brief</p>
          <div className="brief-actions">
            <button type="button" className="rb-btn rb-btn--accent" onClick={() => copy(briefToText(model, draft), 'Brief')}>
              Copy text
            </button>
            <button type="button" className="rb-btn rb-btn--primary" onClick={download}>
              Download as text
            </button>
            <button type="button" className="rb-btn rb-btn--primary" onClick={() => window.print()}>
              Print or save as PDF
            </button>
            <button type="button" className="rb-btn rb-btn--quiet" onClick={onClose}>
              <Icon name="x" />
              Close
            </button>
          </div>
        </div>
        <p className="brief-sheet__status" role="status" aria-live="polite">
          {status}
        </p>
      </div>
      <div className="brief-sheet__page">
        <BriefDocument model={model} draftEditor={draftEditor} draftText={draft} />
      </div>
    </>
  )
}

async function copyWithClipboardApi(text: string): Promise<boolean> {
  if (!navigator.clipboard?.writeText) return false
  const timeout = new Promise<boolean>((resolve) => window.setTimeout(() => resolve(false), CLIPBOARD_TIMEOUT_MS))
  const write = navigator.clipboard.writeText(text).then(
    () => true,
    () => false,
  )
  return Promise.race([write, timeout])
}

/** Fallback for browsers or contexts without the Clipboard API. */
function copyWithSelection(text: string): boolean {
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.append(area)
  area.select()
  try {
    return document.execCommand('copy')
  } catch {
    return false
  } finally {
    area.remove()
  }
}
