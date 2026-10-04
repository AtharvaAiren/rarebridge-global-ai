import type { Contact, OverviewResponse } from '../../api/types.ts'
import { Icon } from '../../components/Icon.tsx'
import { SourceItem } from '../../components/SourceItem.tsx'
import { OutcomeChip, ReviewBadge } from '../../components/StatusChip.tsx'
import { diseaseDisplayName } from '../../domain/diseases.ts'
import { originLabel } from '../../domain/status.ts'
import { checkIdLabel, type RouteEntry } from '../route/routes.ts'
import {
  canonicalSourceId,
  nodeDisplayName as displayName,
  relationLabel,
  type GraphModel,
  type RouteCheck,
  type RouteStep,
} from './graphModel.ts'
import { EdgePanel, NodePanel } from './InspectorDetails.tsx'
import type { EvidenceState } from '../evidence/useAssessment.ts'
import type { Selection } from './types.ts'

export interface TraceView {
  entry: RouteEntry
  check: RouteCheck
  steps: readonly RouteStep[]
  step: number
}

type GraphInspectorProps = {
  model: GraphModel
  overview: OverviewResponse
  selection: Selection
  trace: TraceView | null
  routes: readonly RouteEntry[]
  contacts: ReadonlyMap<string, Contact>
  visibleIds: ReadonlySet<string>
  focusResourceId: string | undefined
  hiddenNeighbourCount: (nodeId: string) => number
  canShowMore: boolean
  onSelectNode: (id: string) => void
  onSelectEdge: (id: string) => void
  onReveal: (id: string) => void
  onTrace: (routeKey: string) => void
  onClear: () => void
  onShowMore: () => void
  evidence: EvidenceState | null
  primaryAssessmentId: string | undefined
  onOpenEvidence: (assessmentId: string) => void
}

export function GraphInspector(props: GraphInspectorProps) {
  const { model, overview, selection, trace } = props
  const hasSelection = trace !== null || selection.kind !== 'none'

  return (
    <aside className="inspector" aria-labelledby="inspector-heading">
      <div className="inspector__bar">
        <h2 id="inspector-heading" className="rb-label">
          {trace ? 'Route' : selection.kind === 'node' ? 'Selected item' : selection.kind === 'edge' ? 'Selected connection' : 'Overview'}
        </h2>
        {hasSelection && (
          <button type="button" className="rb-btn rb-btn--quiet inspector__close" onClick={props.onClear}>
            Back to overview
          </button>
        )}
      </div>
      {trace ? (
        <TracePanel {...props} trace={trace} />
      ) : selection.kind === 'node' ? (
        <NodePanel
          model={model}
          nodeId={selection.id}
          focusDiseaseId={overview.disease.id}
          goalId={overview.goal_id}
          contact={props.contacts.get(selection.id)}
          visibleIds={props.visibleIds}
          hiddenNeighbourCount={props.hiddenNeighbourCount(selection.id)}
          onOpenEvidence={
            selection.id === props.focusResourceId && props.primaryAssessmentId
              ? () => props.onOpenEvidence(props.primaryAssessmentId ?? '')
              : undefined
          }
          sourceToggle={sourceToggleFor(selection.id, props.evidence, model)}
          onSelectEdge={props.onSelectEdge}
          onReveal={props.onReveal}
        />
      ) : selection.kind === 'edge' ? (
        <EdgePanel
          model={model}
          edgeId={selection.id}
          routes={props.routes}
          hiddenSourceIds={props.evidence?.hidden ?? []}
          checkStatusNow={(checkId) => props.evidence?.current?.after.checks.find((c) => c.id === checkId)?.status}
          onSelectNode={props.onSelectNode}
        />
      ) : (
        <DefaultPanel {...props} />
      )}
    </aside>
  )
}

/** Hide/show is offered for a source node while an assessment is open. */
function sourceToggleFor(nodeId: string, evidence: EvidenceState | null, model: GraphModel) {
  const type = model.nodes.get(nodeId)?.type
  if (!evidence || (type !== 'publication' && type !== 'source')) return undefined
  const sourceId = canonicalSourceId(model.sources, nodeId)
  const isHidden = evidence.hidden.includes(sourceId)
  return { isHidden, onToggle: () => (isHidden ? evidence.show(sourceId) : evidence.hide(sourceId)) }
}

function DefaultPanel({ overview, routes, focusResourceId, primaryAssessmentId, onSelectNode, onTrace }: GraphInspectorProps) {
  const opportunity = primaryAssessmentId
    ? overview.opportunities.find((item) => item.assessment_id === primaryAssessmentId)
    : overview.opportunities[0]
  const shortName = diseaseDisplayName(overview.disease.id, overview.disease.label)
  return (
    <div className="inspector__body">
      <h3 className="inspector__title">{shortName}</h3>
      <p>
        The map shows the records behind this research route. Select any item or connection to read its sources and
        review state.
      </p>
      {opportunity ? (
        <section className="inspector__section" aria-label="Selected research resource">
          <h4 className="rb-label">Selected research resource</h4>
          <p className="inspector__emphasis">{opportunity.asset.label}</p>
          {opportunity.outcome && <OutcomeChip state={opportunity.outcome} />}
          <p className="inspector__note">{opportunity.asset.access_status}</p>
          {(opportunity.open_required_check_ids ?? []).length > 0 && (
            <>
              <p className="rb-label">Open questions</p>
              <ul className="inspector__plain-list">
                {opportunity.open_required_check_ids?.map((id) => <li key={id}>{checkIdLabel(id)}</li>)}
              </ul>
            </>
          )}
          {focusResourceId && (
            <button type="button" className="rb-btn rb-btn--quiet" onClick={() => onSelectNode(focusResourceId)}>
              <Icon name="search" />
              Find it on the map
            </button>
          )}
        </section>
      ) : (
        <p className="inspector__note">
          {primaryAssessmentId
            ? 'This selected assessment is outside the disease overview. Open its evidence to inspect the exact target and proposed use.'
            : 'No scoped assessment exists for this disease and goal yet.'}
        </p>
      )}
      <section className="inspector__section" aria-label="Recorded routes">
        <h4 className="rb-label">Recorded routes to other diseases</h4>
        {routes.length === 0 ? (
          <p className="inspector__note">
            No recorded study route links this disease to another one in this collection. Related diseases on the map
            are suggestions only.
          </p>
        ) : (
          <ul className="inspector__plain-list">
            {routes.map((entry) => (
              <li key={entry.key} className="inspector__route">
                <span>
                  {entry.title} to {diseaseDisplayName(entry.related.id, entry.related.label)}
                </span>
                <ReviewBadge status={entry.route.review_status} />
                <button type="button" className="rb-btn rb-btn--quiet" onClick={() => onTrace(entry.key)}>
                  Trace on the map
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function TracePanel({ model, trace, canShowMore, onSelectEdge, onShowMore }: GraphInspectorProps & { trace: TraceView }) {
  const { entry, check, steps } = trace
  const route = entry.route
  const sourceIds = [...new Set((route.source_ids ?? []).map((id) => canonicalSourceId(model.sources, id)))]
  return (
    <div className="inspector__body">
      <p className="inspector__kind">{entry.title}</p>
      <h3 className="inspector__title">
        {displayName(model, route.node_path?.[0] ?? '')} to {diseaseDisplayName(entry.related.id, entry.related.label)}
      </h3>
      <div className="rb-cluster">
        <ReviewBadge status={route.review_status} />
        <span className="origin-tag">{originLabel(route.claim_origin)}</span>
      </div>
      <p>{route.explanation}</p>
      <p className="inspector__note">
        The light traces each recorded link in its own direction, one step at a time. It shows how the records connect,
        not anything flowing between diseases.
      </p>
      {!check.isComplete && (
        <div className="inspector__callout">
          <p>
            Part of this route is outside the current map ({check.missingNodeIds.length + check.missingEdgeIds.length}{' '}
            missing pieces). Hidden is not absent.
          </p>
          {canShowMore && (
            <button type="button" className="rb-btn rb-btn--quiet" onClick={onShowMore}>
              Show more of the map
            </button>
          )}
        </div>
      )}
      <ol className="trace-steps">
        {steps.map((step, index) => {
          const edge = step.edgeId ? model.edgesById.get(step.edgeId) : undefined
          const isReached = index < trace.step
          return (
            <li key={`${step.fromId}-${step.toId}`} className={isReached ? 'is-reached' : undefined}>
              {edge ? (
                <button type="button" className="inspector__link" onClick={() => onSelectEdge(edge.id)}>
                  <span>
                    {displayName(model, step.fromId)} → {displayName(model, step.toId)}
                    <small>
                      {relationLabel(edge.relation)}
                      {step.isReversed && ' (recorded in the other direction)'}
                    </small>
                  </span>
                  <ReviewBadge status={edge.review_status} />
                </button>
              ) : (
                <span className="inspector__note">
                  {displayName(model, step.fromId)} → {displayName(model, step.toId)}: link not in the current map
                </span>
              )}
            </li>
          )
        })}
      </ol>
      {sourceIds.length > 0 && (
        <section className="inspector__section" aria-label="Sources for this route">
          <h4 className="rb-label">Sources</h4>
          <ul className="source-list">
            {sourceIds.map((id) => (
              <SourceItem key={id} id={id} source={model.sources[id]} />
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
