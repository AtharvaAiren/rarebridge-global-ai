import type { Contact, OverviewResponse, RelatedDisease, SourceMap } from '../../api/types.ts'
import { usePreferences } from '../../app/PreferencesContext.tsx'
import { Icon } from '../../components/Icon.tsx'
import { SourceItem } from '../../components/SourceItem.tsx'
import { OutcomeChip, ReviewBadge } from '../../components/StatusChip.tsx'
import { diseaseDisplayName } from '../../domain/diseases.ts'
import { findGoal } from '../../domain/goals.ts'
import { originLabel } from '../../domain/status.ts'
import { safeExternalUrl, urlHost } from '../../domain/urls.ts'
import { routeHash } from '../../routing.ts'
import { assetTypeLabel, contactKindLabel, type RouteEntry } from './routes.ts'

export function DiseaseHeader({ overview }: { overview: OverviewResponse }) {
  const { isExpert } = usePreferences()
  const { disease } = overview
  const goalLabel = findGoal(overview.goal_id)?.label ?? overview.goal_label ?? overview.goal_id
  const shortName = diseaseDisplayName(disease.id, disease.label)
  return (
    <header className="disease-header">
      <p className="disease-header__goal">
        <span className="rb-label">Goal</span> {goalLabel}
      </p>
      <h1>{shortName}</h1>
      {shortName !== disease.label && isExpert && <p className="disease-header__full">{disease.label}</p>}
      <div className="disease-summary">
        {isExpert ? <p>{disease.summary}</p> : <><p>Explore existing research for this condition, see what needs checking, and find a team to approach about your study goal.</p><details className="product-disclosure"><summary>About this condition and its research</summary>{shortName !== disease.label && <p>{disease.label}</p>}<p>{disease.summary}</p></details></>}
        {disease.summary_note && (
          <p className="summary-note">
            <Icon name="info" />
            <span>{disease.summary_note}</span>
          </p>
        )}
      </div>
    </header>
  )
}

type RouteCalloutProps = {
  related: RelatedDisease
  entries: readonly RouteEntry[]
  sources: SourceMap
  onTrace: (routeKey: string) => void
}

/** The one bold element: a study route that is recorded, not suggested. */
export function RouteCallout({ related, entries, sources, onTrace }: RouteCalloutProps) {
  const [primary, ...others] = entries
  if (!primary) return null
  const relatedName = diseaseDisplayName(related.id, related.label)
  return (
    <section className="route-callout rb-band rb-band--warm" aria-labelledby="route-callout-title">
      <p className="rb-label">Recorded study route · {primary.title}</p>
      <h2 id="route-callout-title" className="route-callout__title">
        A recorded research connection with {relatedName}
      </h2>
      <p className="route-callout__body">{primary.route.explanation}</p>
      <div className="rb-cluster">
        <ReviewBadge status={primary.route.review_status} />
        <span className="origin-tag origin-tag--light">{originLabel(primary.route.claim_origin)}</span>
      </div>
      <div className="route-callout__grid">
        <div>
          <h3 className="rb-label">Source</h3>
          <ul className="source-list">
            {(primary.route.source_ids ?? []).map((id) => (
              <SourceItem key={id} id={id} source={sources[id]} />
            ))}
          </ul>
        </div>
        {(related.organizations ?? []).length > 0 && (
          <div>
            <h3 className="rb-label">Patient organizations and research contacts</h3>
            <ul className="contact-mini">
              {(related.organizations ?? []).map((contact) => (
                <ContactMini key={contact.id} contact={contact} />
              ))}
            </ul>
          </div>
        )}
      </div>
      <div className="route-callout__actions">
        <button type="button" className="rb-btn rb-btn--accent" onClick={() => onTrace(primary.key)}>
          Trace this route on the map
        </button>
        {others.map((entry) => (
          <button key={entry.key} type="button" className="rb-btn rb-btn--quiet" onClick={() => onTrace(entry.key)}>
            Also recorded: {entry.title.toLowerCase()} (
            {entry.route.review_status === 'source_checked' ? 'fact checked' : 'source check pending'})
          </button>
        ))}
      </div>
    </section>
  )
}

function ContactMini({ contact }: { contact: Contact }) {
  const url = safeExternalUrl(contact.url)
  return (
    <li>
      {url ? (
        <a href={url} target="_blank" rel="noopener noreferrer">
          {contact.label}
          <Icon name="external" />
        </a>
      ) : (
        <span>{contact.label}</span>
      )}
      <span className="rb-meta">{contact.role}</span>
    </li>
  )
}

type OpportunitiesProps = {
  overview: OverviewResponse
  onShowOnMap: (assetId: string) => void
  onOpenEvidence: (assessmentId: string) => void
}

export function Opportunities({ overview, onShowOnMap, onOpenEvidence }: OpportunitiesProps) {
  const unassessed = overview.unassessed_assets ?? []
  return (
    <section className="page-section" aria-labelledby="opportunities-title" id="opportunities">
      <h2 id="opportunities-title" className="section-title">
        Research resources for this goal
      </h2>
      {overview.opportunities.length === 0 ? (
        <p className="section-intro">
          No resource has a scoped assessment for this disease and goal yet. A resource assessed for another disease is
          not reused here.
        </p>
      ) : (
        <ul className="resource-list">
          {overview.opportunities.map((opportunity) => (
            <li key={opportunity.id} className="resource">
              <p className="resource__type">{assetTypeLabel(opportunity.asset.type)}</p>
              <h3 className="resource__title">{opportunity.asset.label}</h3>
              {opportunity.outcome && <OutcomeChip state={opportunity.outcome} />}
              <p>{opportunity.reason}</p>
              <p className="resource__access">
                <span className="rb-label">Access</span> {opportunity.asset.access_status}
              </p>
              <div className="rb-cluster">
                <button type="button" className="rb-btn rb-btn--primary" onClick={() => onOpenEvidence(opportunity.assessment_id)}>
                  Open evidence
                </button>
                <button type="button" className="rb-btn rb-btn--quiet" onClick={() => onShowOnMap(opportunity.asset.id)}>
                  Show on the map
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {unassessed.length > 0 && (
        <div className="unassessed">
          <h3 className="unassessed__title">Documented for this disease, not yet assessed</h3>
          <ul className="resource-list resource-list--quiet">
            {unassessed.map((item) => (
              <li key={item.asset.id} className="resource">
                <p className="resource__type">{assetTypeLabel(item.asset.type)}</p>
                <h4 className="resource__title">{item.asset.label}</h4>
                <p>{item.reason}</p>
                <p className="resource__access">
                  <span className="rb-label">Access</span> {item.asset.access_status}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

export function Organizations({ overview }: { overview: OverviewResponse }) {
  const { openPanel } = usePreferences()
  return (
    <section className="page-section" aria-labelledby="organizations-title" id="research-contacts">
      <h2 id="organizations-title" className="section-title">
        Who could help
      </h2>
      <p className="section-intro">
        Public contact routes recorded in this collection. A role is listed, not a promise that this person or group
        owns a resource or will reply.
      </p>
      {overview.organizations.length === 0 ? (
        <p className="section-intro">No organization or study team is recorded for this disease in this collection.</p>
      ) : (
        <ul className="contact-list">
          {overview.organizations.map((contact) => {
            const url = safeExternalUrl(contact.url)
            return (
              <li key={contact.id} className="contact">
                <p className="resource__type">{contactKindLabel(contact.kind)}</p>
                <h3 className="resource__title">{contact.label}</h3>
                <p>{contact.role}</p>
                <div className="rb-cluster">
                  <ReviewBadge status={contact.review_status} />
                  <span className="rb-meta">
                    {contact.last_checked ? `Last checked ${contact.last_checked}` : 'Not yet checked by a person'}
                  </span>
                </div>
                {url && (
                  <a className="contact__link" href={url} target="_blank" rel="noopener noreferrer">
                    Public page on {urlHost(url)}
                    <Icon name="external" />
                  </a>
                )}
                <div className="product-contact-action"><button type="button" className="rb-btn rb-btn--quiet" onClick={() => openPanel('contacts', contact)}>Plan a discussion · Preview<Icon name="arrowRight" /></button></div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

export function PossiblyRelated({ candidates, goalId }: { candidates: readonly RelatedDisease[]; goalId: string }) {
  if (candidates.length === 0) return null
  return (
    <section className="page-section" aria-labelledby="related-title">
      <h2 id="related-title" className="section-title section-title--quiet">
        Possibly related (suggested, not established)
      </h2>
      <ul className="related-list">
        {candidates.map((related) => (
          <li key={related.id} className="related">
            <a className="related__name" href={routeHash({ name: 'disease', diseaseId: related.id, goal: goalId })}>
              {diseaseDisplayName(related.id, related.label)}
            </a>
            <p>{related.reason}</p>
            {(related.shared_terms ?? []).length > 0 && (
              <details className="rb-disclosure">
                <summary>Shared annotations ({related.shared_terms?.length})</summary>
                <ul className="term-list">
                  {related.shared_terms?.map((term) => (
                    <li key={term.id}>
                      {term.label} <span className="rb-meta">{term.type.replace(/_/g, ' ')}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

export function CoverageNotes({ overview }: { overview: OverviewResponse }) {
  const gaps = overview.coverage.gaps ?? []
  return (
    <section className="page-section coverage" aria-labelledby="coverage-title">
      <h2 id="coverage-title" className="section-title section-title--quiet">
        What this collection covers
      </h2>
      <p>{overview.coverage.scope_note}</p>
      {gaps.length > 0 && (
        <ul className="coverage__gaps">
          {gaps.map((gap) => (
            <li key={gap}>{gap}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
