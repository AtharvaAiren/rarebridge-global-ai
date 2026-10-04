import type { ReactNode } from 'react'
import type { Contact } from '../../api/types.ts'
import { Icon } from '../../components/Icon.tsx'
import { SourceItem } from '../../components/SourceItem.tsx'
import { OutcomeChip, ReviewBadge } from '../../components/StatusChip.tsx'
import { diseaseDisplayName } from '../../domain/diseases.ts'
import { originLabel } from '../../domain/status.ts'
import { safeExternalUrl } from '../../domain/urls.ts'
import { routeHash } from '../../routing.ts'
import { checkIdLabel, contactKindLabel, type RouteEntry } from '../route/routes.ts'
import {
  canonicalSourceId,
  edgeLineStyle,
  nodeDisplayName,
  nodeGroup,
  nodeTypeLabel,
  relationLabel,
  type GraphModel,
  type ModelEdge,
} from './graphModel.ts'
import { NodeShape } from './NodeShape.tsx'

const MAX_ALIASES = 5
const MAX_CONNECTIONS = 12

const NODE_ORIGINS: Readonly<Record<string, string>> = {
  dismech_snapshot: 'From the pinned DisMech snapshot (AI-curated)',
  curation_overlay: 'From the curated overlay',
}

const LINE_STYLE_TEXT = {
  solid: 'Solid line: fact checked against its source',
  dashed: 'Dashed line: source check pending',
  dotted: 'Dotted line: inferred for navigation',
} as const

const displayName = nodeDisplayName

type NodePanelProps = {
  model: GraphModel
  nodeId: string
  focusDiseaseId: string
  goalId: string
  contact: Contact | undefined
  visibleIds: ReadonlySet<string>
  hiddenNeighbourCount: number
  /** Present for the assessed resource: opens its evidence view. */
  onOpenEvidence?: () => void
  /** Present for a source while an assessment is open. */
  sourceToggle?: { isHidden: boolean; onToggle: () => void }
  onSelectEdge: (id: string) => void
  onReveal: (id: string) => void
}

export function NodePanel(props: NodePanelProps) {
  const { model, nodeId, focusDiseaseId, goalId, contact, visibleIds, hiddenNeighbourCount } = props
  const node = model.nodes.get(nodeId)
  if (!node) return <p>This item is not in the current map.</p>
  const group = nodeGroup(node.type)
  const aliases = [...(node.aliases ?? []), ...(node.synonyms ?? [])].slice(0, MAX_ALIASES)
  const publicUrl = safeExternalUrl(contact?.url ?? node.url)
  const connections = (model.incident.get(nodeId) ?? [])
    .map((id) => model.edgesById.get(id))
    .filter((e): e is ModelEdge => e !== undefined && visibleIds.has(e.sourceId) && visibleIds.has(e.targetId))

  return (
    <div className="inspector__body">
      <p className="inspector__kind">
        <svg viewBox="-12 -12 24 24" width="18" height="18" aria-hidden="true" className={`g-swatch g-node--${group}`}>
          <NodeShape group={group} radius={8} />
        </svg>
        {nodeTypeLabel(node.type)}
      </p>
      <h3 className="inspector__title">{node.label}</h3>
      <div className="rb-cluster">
        <ReviewBadge status={node.review_status} />
      </div>
      <dl className="inspector__facts">
        {node.origin && <Fact term="Record">{NODE_ORIGINS[node.origin] ?? node.origin.replace(/_/g, ' ')}</Fact>}
        {node.asset_type && <Fact term="Resource type">{node.asset_type.replace(/_/g, ' ')}</Fact>}
        {node.access_status && <Fact term="Access">{node.access_status}</Fact>}
        {aliases.length > 0 && <Fact term="Also known as">{aliases.join('; ')}</Fact>}
        <Fact term="ID">
          <span className="rb-id">{node.id}</span>
        </Fact>
      </dl>

      {contact && <ContactFacts contact={contact} />}
      {node.type === 'researcher' && (
        <p className="inspector__note">
          A paper author is a possible contact. The record does not say they own or control this resource.
        </p>
      )}

      <div className="inspector__actions">
        {publicUrl && (
          <a className="rb-btn rb-btn--primary" href={publicUrl} target="_blank" rel="noopener noreferrer">
            Open public page
            <Icon name="external" />
          </a>
        )}
        {node.type === 'disease' && node.id !== focusDiseaseId && (
          <a className="rb-btn rb-btn--quiet" href={routeHash({ name: 'disease', diseaseId: node.id, goal: goalId })}>
            Open {diseaseDisplayName(node.id, node.label)}
            <Icon name="arrowRight" />
          </a>
        )}
        {props.onOpenEvidence && (
          <button type="button" className="rb-btn rb-btn--primary" onClick={props.onOpenEvidence}>
            Open evidence
          </button>
        )}
        {props.sourceToggle && (
          <button type="button" className="rb-btn rb-btn--quiet" onClick={props.sourceToggle.onToggle}>
            {props.sourceToggle.isHidden ? 'Show this publication again' : 'Hide this publication'}
          </button>
        )}
        {hiddenNeighbourCount > 0 && (
          <button type="button" className="rb-btn rb-btn--quiet" onClick={() => props.onReveal(nodeId)}>
            <Icon name="arrowRight" />
            Show {hiddenNeighbourCount} more connected {hiddenNeighbourCount === 1 ? 'item' : 'items'}
          </button>
        )}
      </div>

      {connections.length > 0 && (
        <section className="inspector__section" aria-label="Connections on the map">
          <h4 className="rb-label">Connections on the map</h4>
          <ul className="inspector__links">
            {connections.slice(0, MAX_CONNECTIONS).map((edge) => (
              <li key={edge.id}>
                <button type="button" className="inspector__link" onClick={() => props.onSelectEdge(edge.id)}>
                  <span>
                    {displayName(model, edge.sourceId)} <em>{relationLabel(edge.relation)}</em>{' '}
                    {displayName(model, edge.targetId)}
                  </span>
                  <Icon name="arrowRight" />
                </button>
              </li>
            ))}
          </ul>
          {connections.length > MAX_CONNECTIONS && (
            <p className="inspector__note">{connections.length - MAX_CONNECTIONS} more in the list view below the map.</p>
          )}
        </section>
      )}
    </div>
  )
}

function ContactFacts({ contact }: { contact: Contact }) {
  return (
    <section className="inspector__section" aria-label="Recorded contact route">
      <h4 className="rb-label">{contactKindLabel(contact.kind)} recorded in this collection</h4>
      <p>{contact.role}</p>
      {contact.relevance && <p className="inspector__note">{contact.relevance}</p>}
      <div className="rb-cluster">
        <ReviewBadge status={contact.review_status} />
        <span className="rb-meta">
          {contact.last_checked ? `Last checked ${contact.last_checked}` : 'Not yet checked by a person'}
        </span>
      </div>
    </section>
  )
}

type EdgePanelProps = {
  model: GraphModel
  edgeId: string
  routes: readonly RouteEntry[]
  /** Canonical sources hidden in this view. */
  hiddenSourceIds: readonly string[]
  /** A check's status in the current assessment response, if one is open. */
  checkStatusNow: (checkId: string) => string | undefined
  onSelectNode: (id: string) => void
}

export function EdgePanel({ model, edgeId, routes, hiddenSourceIds, checkStatusNow, onSelectNode }: EdgePanelProps) {
  const edge = model.edgesById.get(edgeId)
  if (!edge) return <p>This connection is not in the current map.</p>
  const style = edgeLineStyle(edge)
  const sourceIds = [...new Set(edge.source_ids.map((id) => canonicalSourceId(model.sources, id)))]
  const memberOf = routes.filter((entry) => entry.route.edge_ids?.includes(edge.id))
  const provenance = Object.entries(edge.provenance ?? {}).filter(([, value]) => typeof value === 'string')
  const hiddenCount = sourceIds.filter((id) => hiddenSourceIds.includes(id)).length
  const statusNow = edge.check_id ? checkStatusNow(edge.check_id) : undefined

  return (
    <div className="inspector__body">
      <p className="inspector__kind">
        <svg width="28" height="10" aria-hidden="true" className={`g-edge g-edge--${style} g-swatch-line`}>
          <path className="g-edge__line" d="M2 5H26" />
        </svg>
        Connection
      </p>
      <h3 className="inspector__title">
        <button type="button" className="inspector__node-link" onClick={() => onSelectNode(edge.sourceId)}>
          {displayName(model, edge.sourceId)}
        </button>{' '}
        <span aria-label="to">→</span>{' '}
        <button type="button" className="inspector__node-link" onClick={() => onSelectNode(edge.targetId)}>
          {displayName(model, edge.targetId)}
        </button>
      </h3>
      <p className="inspector__relation">
        Recorded relationship: <strong>{relationLabel(edge.relation)}</strong>
      </p>
      <p>{edge.explanation}</p>

      <div className="rb-cluster">
        <ReviewBadge status={edge.review_status} />
        <span className="origin-tag">{originLabel(edge.claim_origin)}</span>
      </div>
      {hiddenCount > 0 && (
        <p className="inspector__callout">
          In this view, {hiddenCount} of {sourceIds.length} {sourceIds.length === 1 ? 'source' : 'sources'} for this
          connection {hiddenCount === 1 ? 'is' : 'are'} hidden. Its recorded review status is unchanged.
        </p>
      )}
      {edge.claim_origin === 'inferred' && (
        <p className="inspector__callout">
          This link helps you move around the map. It is not a proven biological relationship, even when its source has
          been checked.
        </p>
      )}
      <dl className="inspector__facts">
        <Fact term="Confidence label">
          {edge.confidence_label} <span className="rb-meta">(a qualitative label, not a probability)</span>
        </Fact>
        <Fact term="Line on the map">{LINE_STYLE_TEXT[style]}</Fact>
        {edge.check_id && (
          <Fact term="Assessment check">
            {checkIdLabel(edge.check_id)}
            {edge.check_status && (
              <span className="inspector__chip-row">
                <span className="rb-meta">As recorded: </span>
                <OutcomeChip state={edge.check_status} />
              </span>
            )}
            {statusNow && statusNow !== edge.check_status && (
              <span className="inspector__chip-row">
                <span className="rb-meta">In the current assessment view: </span>
                <OutcomeChip state={statusNow} />
              </span>
            )}
          </Fact>
        )}
        {memberOf.map((entry) => (
          <Fact key={entry.key} term="Part of">
            {entry.title} to {diseaseDisplayName(entry.related.id, entry.related.label)}
          </Fact>
        ))}
      </dl>

      <section className="inspector__section" aria-label="Sources for this connection">
        <h4 className="rb-label">{sourceIds.length === 1 ? 'Source' : `Sources (${sourceIds.length})`}</h4>
        {sourceIds.length === 0 ? (
          <p className="inspector__note">No source is listed for this connection.</p>
        ) : (
          <ul className="source-list">
            {sourceIds.map((id) => (
              <SourceItem key={id} id={id} source={model.sources[id]} />
            ))}
          </ul>
        )}
      </section>

      {provenance.length > 0 && (
        <details className="rb-disclosure inspector__section">
          <summary>Where this record comes from</summary>
          <dl className="inspector__facts">
            {provenance.map(([key, value]) => {
              const url = safeExternalUrl(String(value))
              return (
                <Fact key={key} term={key.replace(/_/g, ' ')}>
                  {url ? (
                    <a href={url} target="_blank" rel="noopener noreferrer">
                      {String(value)}
                    </a>
                  ) : (
                    String(value)
                  )}
                </Fact>
              )
            })}
            <Fact term="Connection ID">
              <span className="rb-id">{edge.id}</span>
            </Fact>
          </dl>
        </details>
      )}
    </div>
  )
}

export function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="inspector__fact">
      <dt>{term}</dt>
      <dd>{children}</dd>
    </div>
  )
}
