import type { AssessmentCheck, ChangedCheck, EvidenceItem, SourceMap } from '../../api/types.ts'
import { Icon } from '../../components/Icon.tsx'
import { OutcomeChip, ReviewBadge } from '../../components/StatusChip.tsx'
import { polarityLabel } from '../../domain/assessment.ts'
import { statusSpec } from '../../domain/status.ts'
import { safeExternalUrl } from '../../domain/urls.ts'

type CheckRowProps = {
  check: AssessmentCheck
  change: ChangedCheck | undefined
  sources: SourceMap
  isBusy: boolean
  onHide: (sourceId: string) => void
  onShow: (sourceId: string) => void
}

/**
 * One check, collapsed to a single line: status icon + question. The
 * evidence (or the missing-evidence question) opens on demand.
 */
export function CheckRow({ check, change, sources, isBusy, onHide, onShow }: CheckRowProps) {
  const spec = statusSpec(check.status)
  const hasActive = check.active_evidence.length > 0
  return (
    <li className={`check${change ? ' is-changed' : ''}`}>
      <details className="check__details">
        <summary className="check__summary">
          <span className={`check__icon status-chip--${spec.tone}`} aria-hidden="true">
            <Icon name={spec.icon} />
          </span>
          <span className="check__text">
            <span className="check__question">{check.question}</span>
            <span className="check__status">
              {spec.label}
              {change && <span className="check__changed"> · changed in this view</span>}
            </span>
          </span>
        </summary>
        <div className="check__body">
          {change && (
            <p className="check__change">
              <OutcomeChip state={change.before} />
              <Icon name="arrowRight" className="check-row__arrow" />
              <OutcomeChip state={change.after} />
            </p>
          )}
          {check.active_evidence.map((item) => (
            <EvidenceRow key={`active-${item.source_id}`} item={item} sources={sources} isBusy={isBusy} onToggle={onHide} />
          ))}
          {check.withdrawn_evidence.map((item) => (
            <EvidenceRow
              key={`hidden-${item.source_id}`}
              item={item}
              sources={sources}
              isBusy={isBusy}
              isHidden
              onToggle={onShow}
            />
          ))}
          {!hasActive && (
            <div className="check__gap">
              <p className="check__gap-title">No source in this collection answers this.</p>
              <p>
                <span className="rb-label">Next question</span> {check.next_question}
              </p>
              <p>
                <span className="rb-label">Who could answer</span> {check.contact_role}
              </p>
            </div>
          )}
        </div>
      </details>
    </li>
  )
}

type EvidenceRowProps = {
  item: EvidenceItem
  sources: SourceMap
  isBusy: boolean
  isHidden?: boolean
  onToggle: (sourceId: string) => void
}

function EvidenceRow({ item, sources, isBusy, isHidden = false, onToggle }: EvidenceRowProps) {
  const source = sources[item.source_id]
  const url = safeExternalUrl(source?.url)
  const title = source?.title ?? item.source_id
  return (
    <div className={`evidence-item${isHidden ? ' is-hidden' : ''}`}>
      <p className="evidence-item__polarity">{isHidden ? 'Hidden in this view' : polarityLabel(item.polarity)}</p>
      {url ? (
        <a className="evidence-item__title" href={url} target="_blank" rel="noopener noreferrer">
          {title}
          <Icon name="external" />
        </a>
      ) : (
        <span className="evidence-item__title">{title}</span>
      )}
      <p className="evidence-item__rationale">{item.rationale}</p>
      <div className="evidence-item__actions">
        <ReviewBadge status={item.review_status} />
        <button type="button" className="rb-btn rb-btn--quiet evidence-item__toggle" disabled={isBusy} onClick={() => onToggle(item.source_id)}>
          {isHidden ? 'Show again' : 'Hide this publication'}
        </button>
      </div>
    </div>
  )
}
