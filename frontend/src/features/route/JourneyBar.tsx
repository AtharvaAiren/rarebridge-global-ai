type JourneyBarProps = {
  canTrace: boolean
  canShowResource: boolean
  canOpenEvidence: boolean
  canOpenBrief: boolean
  onConnection: () => void
  onResource: () => void
  onEvidence: () => void
  onBrief: () => void
}

/** Persistent journey controls. Stages are UI steps, not graph records. */
export function JourneyBar(props: JourneyBarProps) {
  const { canTrace, canShowResource, canOpenEvidence, canOpenBrief, onConnection, onResource, onEvidence, onBrief } = props
  return (
    <nav className="journey-bar" aria-label="Journey">
      <ol className="rb-container journey-bar__inner">
        <li>
          <button type="button" className="journey-step" onClick={onConnection} disabled={!canTrace}>
            <span className="journey-step__index">1</span>Connection
          </button>
        </li>
        <li>
          <button type="button" className="journey-step" onClick={onResource} disabled={!canShowResource}>
            <span className="journey-step__index">2</span>Resource
          </button>
        </li>
        <li>
          <button type="button" className="journey-step" onClick={onEvidence} disabled={!canOpenEvidence}>
            <span className="journey-step__index">3</span>Evidence
          </button>
        </li>
        <li>
          <button
            type="button"
            className="journey-step"
            onClick={onBrief}
            disabled={!canOpenBrief}
            title={canOpenBrief ? undefined : 'Open the evidence for a resource first'}
          >
            <span className="journey-step__index">4</span>Collaboration brief
          </button>
        </li>
      </ol>
    </nav>
  )
}
