import { originLabel, reviewSpec } from '../../domain/status.ts'
import {
  GROUP_LABELS,
  nodeDisplayName as displayName,
  nodeGroup,
  relationLabel,
  type GraphModel,
  type ModelEdge,
  type NodeGroup,
} from './graphModel.ts'
import type { Selection } from './types.ts'

type GraphListProps = {
  model: GraphModel
  nodeIds: readonly string[]
  edges: readonly ModelEdge[]
  selection: Selection
  onSelectNode: (id: string) => void
  onSelectEdge: (id: string) => void
}

/** The same map as lists of buttons, for keyboard and screen-reader use. */
export function GraphList({ model, nodeIds, edges, selection, onSelectNode, onSelectEdge }: GraphListProps) {
  const byGroup = new Map<NodeGroup, string[]>()
  for (const id of nodeIds) {
    const group = nodeGroup(model.nodes.get(id)?.type ?? '')
    byGroup.set(group, [...(byGroup.get(group) ?? []), id])
  }

  return (
    <details className="rb-disclosure atlas-list">
      <summary>
        List view: {nodeIds.length} items and {edges.length} connections
      </summary>
      <div className="atlas-list__columns">
        <section aria-label="Items on the map">
          <h3 className="rb-label">Items</h3>
          {[...byGroup].map(([group, ids]) => (
            <div key={group} className="atlas-list__group">
              <p className="atlas-list__group-name">{GROUP_LABELS[group]}</p>
              <ul>
                {ids.map((id) => (
                  <li key={id}>
                    <button
                      type="button"
                      className="atlas-list__item"
                      aria-current={selection.kind === 'node' && selection.id === id ? 'true' : undefined}
                      onClick={() => onSelectNode(id)}
                    >
                      {model.nodes.get(id)?.label ?? id}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
        <section aria-label="Connections on the map">
          <h3 className="rb-label">Connections</h3>
          <ul>
            {edges.map((edge) => (
              <li key={edge.id}>
                <button
                  type="button"
                  className="atlas-list__item"
                  aria-current={selection.kind === 'edge' && selection.id === edge.id ? 'true' : undefined}
                  onClick={() => onSelectEdge(edge.id)}
                >
                  {displayName(model, edge.sourceId)} {relationLabel(edge.relation)} {displayName(model, edge.targetId)}
                  <small>
                    {reviewSpec(edge.review_status).label} · {originLabel(edge.claim_origin)}
                  </small>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </details>
  )
}
