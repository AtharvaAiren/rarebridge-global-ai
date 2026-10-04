import type { ReactNode } from 'react'
import type { AssessmentResponse, Contact } from '../../api/types.ts'
import { usePreferences } from '../../app/PreferencesContext.tsx'
import { Icon } from '../../components/Icon.tsx'
import { ErrorState, LoadingState } from '../../components/StateViews.tsx'
import { OutcomeChip, ReviewBadge } from '../../components/StatusChip.tsx'
import { changesByCheck, citedSourceIds, splitChecks } from '../../domain/assessment.ts'
import { diseaseDisplayName } from '../../domain/diseases.ts'
import { statusSpec } from '../../domain/status.ts'
import { safeExternalUrl } from '../../domain/urls.ts'
import { shortLabel } from '../graph/graphModel.ts'
import { assetTypeLabel, contactKindLabel } from '../route/routes.ts'
import { AiExplanation } from './AiExplanation.tsx'
import { CheckRow } from './CheckRow.tsx'
import type { EvidenceState } from './useAssessment.ts'

const SOURCE_TITLE_MAX = 58

type EvidencePanelProps = {
  evidence: EvidenceState
  /** Opens the brief built from this exact assessment view. */
  onPrepareBrief?: () => void
}

/**
 * Summary first, depth on demand: outcome, the source-dependence test and
 * one line per check; everything else folds away.
 */
export function EvidencePanel({ evidence, onPrepareBrief }: EvidencePanelProps) {
  const data = evidence.current ?? evidence.previous
  if (evidence.error) {
    return (
      <div className="evidence">
        <ErrorState error={evidence.error} onRetry={evidence.retry} />
        {evidence.hidden.length > 0 && (
          <button type="button" className="rb-btn rb-btn--quiet" onClick={evidence.reset}>
            Show all sources again
          </button>
        )}
      </div>
    )
  }
  if (!data) return <LoadingState label="Loading the assessment…" />

  const isStale = evidence.current === null
  return (
    <div className="evidence">
      <OutcomeSummary data={data} hiddenCount={evidence.hidden.length} />
      {evidence.hidden.length > 0 && evidence.current && <ChangeSummary data={evidence.current} />}
      <DependenceTest evidence={evidence} data={data} isBusy={isStale} />
      {isStale && (
        <p className="evidence__updating" role="status">
          <span className="spinner" aria-hidden="true" />
          Re-checking the assessment for the sources you chose…
        </p>
      )}
      <div className={`evidence__body${isStale ? ' is-stale' : ''}`} aria-busy={isStale}>
        <AssessmentBody data={data} evidence={evidence} isBusy={isStale} />
      </div>
      {onPrepareBrief && (
        <div className="evidence__footer">
          <button type="button" className="rb-btn rb-btn--primary evidence__footer-btn" onClick={onPrepareBrief} disabled={!evidence.current}>
            Prepare collaboration brief
          </button>
          <span className="evidence__footer-note">
            {evidence.hidden.length > 0 ? 'Lists the hidden source' : 'Uses this view'}
          </span>
        </div>
      )}
    </div>
  )
}

function OutcomeSummary({ data, hiddenCount }: { data: AssessmentResponse; hiddenCount: number }) {
  const { before, after } = data
  const target = after.target_disease
  const supported = after.checks.filter((c) => c.status === 'supported').length
  const open = after.checks.length - supported
  return (
    <header className="evidence__head">
      {after.asset && <p className="inspector__kind">{assetTypeLabel(after.asset.type)}</p>}
      <h3 className="inspector__title">{after.asset?.label ?? after.assessment_id}</h3>
      {target && <p className="inspector__note">For {diseaseDisplayName(target.id, target.label)}</p>}
      <div className="evidence__outcome">
        <OutcomeChip state={after.outcome} />
        <span className="evidence__tally">
          {supported} supported · {open} open
        </span>
      </div>
      {hiddenCount > 0 && (
        <p className="evidence__compare">
          {before.outcome === after.outcome ? (
            'Overall result unchanged with the hidden source.'
          ) : (
            <>
              Before hiding: <OutcomeChip state={before.outcome} />
            </>
          )}
        </p>
      )}
    </header>
  )
}

/** The API's changed checks, right under the outcome so the change is seen at once. */
function ChangeSummary({ data }: { data: AssessmentResponse }) {
  const questions = new Map(data.after.checks.map((check) => [check.id, check.question]))
  const count = data.changed_checks.length
  return (
    <section className="change-summary" aria-live="polite" aria-label="What changed">
      <p className="evidence__changes">
        {count === 0 ? 'No check changed.' : `${count === 1 ? '1 check' : `${count} checks`} changed:`}
      </p>
      {count > 0 && (
        <ul className="change-summary__list">
          {data.changed_checks.map((change) => (
            <li key={change.check_id} className="change-summary__item">
              <span>{questions.get(change.check_id) ?? change.check_id}</span>
              <span className="change-summary__delta">
                {statusSpec(change.before).label} <Icon name="arrowRight" /> <strong>{statusSpec(change.after).label}</strong>
              </span>
            </li>
          ))}
        </ul>
      )}
      {data.interpretation && <p className="evidence__interpretation">{data.interpretation}</p>}
    </section>
  )
}

/** The signature interaction, near the top: what if a cited paper were missing? */
function DependenceTest({ evidence, data, isBusy }: { evidence: EvidenceState; data: AssessmentResponse; isBusy: boolean }) {
  const roles = data.source_roles
  const cited = roles
    ? Object.keys(data.sources).filter((id) => roles[id]?.includes('assessment_evidence'))
    : citedSourceIds(data.after.checks)
  if (cited.length === 0 && evidence.hidden.length === 0) return null
  const hidden = new Set(evidence.hidden)
  return (
    <section className="dependence" aria-labelledby="dependence-title">
      <h4 id="dependence-title" className="dependence__title">
        What if a source were missing?
      </h4>
      <p className="dependence__intro">Hide a cited source to see which checks depend on it. The records themselves do not change.</p>
      <ul className="dependence__list">
        {[...new Set([...cited, ...evidence.hidden])].map((id) => {
          const isHidden = hidden.has(id)
          return (
            <li key={id} className={isHidden ? 'is-hidden' : undefined}>
              <span className="dependence__source">{shortLabel(data.sources[id]?.title ?? id, SOURCE_TITLE_MAX)}</span>
              <button
                type="button"
                className={`rb-btn ${isHidden ? 'rb-btn--quiet' : 'rb-btn--primary'} dependence__toggle`}
                disabled={isBusy}
                onClick={() => (isHidden ? evidence.show(id) : evidence.hide(id))}
              >
                {isHidden ? 'Show again' : 'Hide'}
              </button>
            </li>
          )
        })}
      </ul>
      {evidence.hidden.length > 1 && (
        <button type="button" className="rb-btn rb-btn--quiet" onClick={evidence.reset} disabled={isBusy}>
          <Icon name="retry" />
          Show all sources again
        </button>
      )}
    </section>
  )
}

type BodyProps = { data: AssessmentResponse; evidence: EvidenceState; isBusy: boolean }

function AssessmentBody({ data, evidence, isBusy }: BodyProps) {
  const { isExpert } = usePreferences()
  const changes = changesByCheck(data.changed_checks)
  const { required, optional } = splitChecks(data.after.checks)
  const rowProps = { sources: data.sources, isBusy, onHide: evidence.hide, onShow: evidence.show }
  const ignored = data.withdrawn_source_ids_ignored ?? []

  return (
    <>
      <section className="evidence__group" aria-labelledby="required-checks">
        <h4 id="required-checks" className="rb-label">
          {isExpert ? 'Required checks · open one for its evidence' : 'What needs to be answered · open a question to see its evidence'}
        </h4>
        <ul className="check-list">
          {required.map((check) => (
            <CheckRow key={check.id} check={check} change={changes.get(check.id)} {...rowProps} />
          ))}
        </ul>
      </section>
      {ignored.length > 0 && (
        <p className="inspector__note">Not cited by this assessment, so hiding it changes no check: {ignored.join(', ')}.</p>
      )}
      {optional.length > 0 && (
        <Fold title={`Also worth checking (${optional.length}, not required)`}>
          <ul className="check-list">
            {optional.map((check) => (
              <CheckRow key={check.id} check={check} change={changes.get(check.id)} {...rowProps} />
            ))}
          </ul>
        </Fold>
      )}
      {data.after.followup_questions.length > 0 && (
      <Fold title={`Questions to ask (${data.after.followup_questions.length})`} defaultOpen={!isExpert}>
          <ol className="followups">
            {data.after.followup_questions.map((question) => (
              <li key={`${question.check_id}-${question.question}`}>
                {question.question}
                <span className="rb-meta">Ask a {question.contact_role}</span>
              </li>
            ))}
          </ol>
        </Fold>
      )}
      <Fold title="Plain-language explanation (AI)">
        <AiExplanation evidence={evidence} />
      </Fold>
      <Fold title={`Who could answer (${data.contacts.length})`}>
        <ContactList contacts={data.contacts} />
      </Fold>
      <Fold title={`Sources (${Object.keys(data.sources).length})`}>
        <SourceList data={data} evidence={evidence} isBusy={isBusy} />
      </Fold>
      <Fold title="About this assessment" defaultOpen={isExpert}>
        <ContextSection data={data} />
      </Fold>
    </>
  )
}

function Fold({ title, children, defaultOpen = false }: { title: string; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <details className="rb-disclosure evidence__fold" open={defaultOpen || undefined}>
      <summary>{title}</summary>
      <div className="evidence__fold-body">{children}</div>
    </details>
  )
}

function SourceList({ data, evidence, isBusy }: BodyProps) {
  const hidden = new Set(evidence.hidden)
  return (
    <ul className="compact-list">
      {Object.entries(data.sources).map(([id, source]) => {
        const isHidden = hidden.has(id)
        const url = safeExternalUrl(source.url)
        return (
          <li key={id} className={`compact-row${isHidden ? ' is-hidden' : ''}`}>
            <span className="compact-row__main">
              {url ? (
                <a href={url} target="_blank" rel="noopener noreferrer">
                  {shortLabel(source.title, SOURCE_TITLE_MAX)}
                </a>
              ) : (
                shortLabel(source.title, SOURCE_TITLE_MAX)
              )}
              <span className="rb-meta">
                {source.published_on ?? 'Undated'} · {source.source_kind.replace(/_/g, ' ')}
                {isHidden && ' · hidden in this view'}
              </span>
            </span>
            <button
              type="button"
              className="rb-btn rb-btn--quiet compact-row__action"
              disabled={isBusy}
              onClick={() => (isHidden ? evidence.show(id) : evidence.hide(id))}
            >
              {isHidden ? 'Show' : 'Hide'}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

function ContactList({ contacts }: { contacts: readonly Contact[] }) {
  if (contacts.length === 0) return <p className="inspector__note">No contact route is recorded for this assessment.</p>
  return (
    <ul className="compact-list">
      {contacts.map((contact) => {
        const url = safeExternalUrl(contact.url)
        return (
          <li key={contact.id} className="compact-row">
            <span className="compact-row__main">
              {url ? (
                <a href={url} target="_blank" rel="noopener noreferrer">
                  {contact.label}
                </a>
              ) : (
                contact.label
              )}
              <span className="rb-meta compact-row__clamp">
                {contactKindLabel(contact.kind)} · {contact.role}
              </span>
              {contact.all_sources_withdrawn && <span className="rb-meta">Every source for this contact is hidden.</span>}
            </span>
            <ReviewBadge status={contact.review_status} />
          </li>
        )
      })}
    </ul>
  )
}

function ContextSection({ data }: { data: AssessmentResponse }) {
  const context = data.asset_context
  return (
    <div className="evidence__context">
      {context?.description && <p>{context.description}</p>}
      {context?.documented_context && <p className="inspector__note">{context.documented_context}</p>}
      {(context?.unverified ?? []).length > 0 && (
        <p className="inspector__note">Not yet checked: {context?.unverified?.join('; ')}.</p>
      )}
      <p className="inspector__note">{data.after.limitations}</p>
      <p className="inspector__note">{data.coverage}</p>
      {data.review_summary?.note && <p className="inspector__note">{data.review_summary.note}</p>}
    </div>
  )
}
