import { useEffect, useId, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from 'react'
import { Icon } from '../../components/Icon.tsx'
import { originLabel, reviewSpec } from '../../domain/status.ts'
import { edgeLineStyle, relationLabel, type GraphModel, type ModelEdge, type NodeGroup } from './graphModel.ts'
import type { NodeRole } from './layout.ts'
import { DURATION, EASE, tween } from './motion.ts'
import { NodeShape } from './NodeShape.tsx'
import type { GraphScene } from './useGraphScene.ts'
import type { ViewMode } from './types.ts'

export interface CanvasNode {
  id: string
  group: NodeGroup
  role: NodeRole
  radius: number
  shortLabel: string
  fullLabel: string
}

export interface CanvasHighlight {
  selectedNodeId: string | null
  selectedEdgeId: string | null
  hoveredNodeId: string | null
  routeEdgeIds: ReadonlySet<string>
  routeNodeIds: ReadonlySet<string>
  traceNodeIds: ReadonlySet<string>
  traceEdgeIds: ReadonlySet<string>
  /** The edge the trace light is currently travelling along. */
  traceActiveEdgeId: string | null
  /** Sources hidden in this view, and the relationships that cite them. */
  hiddenNodeIds: ReadonlySet<string>
  partlyHiddenEdgeIds: ReadonlySet<string>
  fullyHiddenEdgeIds: ReadonlySet<string>
}

type GraphCanvasProps = {
  scene: GraphScene
  model: GraphModel
  nodes: readonly CanvasNode[]
  edges: readonly ModelEdge[]
  highlight: CanvasHighlight
  isLabelAll: boolean
  isMotionOn: boolean
  viewMode: ViewMode
  hiddenSourceCount: number
  changedCheckCount: number
  summary: string
  onEdgeClick: (edgeId: string) => void
  onHoverNode: (nodeId: string | null) => void
}

const KEY_LABELS = { solid: 'Fact checked', dashed: 'Check pending', dotted: 'Inferred link' } as const

const ZOOM_STEP = 1.3
const TOOLTIP_OFFSET_PX = 14

const ANCHOR_CAPTIONS: Partial<Record<NodeRole, string>> = {
  focusDisease: 'Your disease',
  focusResource: 'Selected resource',
}

interface EdgeHover {
  id: string
  x: number
  y: number
}

export function GraphCanvas(props: GraphCanvasProps) {
  const { scene, model, nodes, edges, highlight, isLabelAll, isMotionOn, summary, onEdgeClick, onHoverNode } =
    props
  const uid = useId().replace(/:/g, '')
  const particleRef = useRef<SVGCircleElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [edgeHover, setEdgeHover] = useState<EdgeHover | null>(null)
  const active = activeSets(model, highlight, nodes)
  const hoveredEdge = edgeHover ? model.edgesById.get(edgeHover.id) : undefined

  const showEdgeHover = (edgeId: string, event: ReactPointerEvent) => {
    const rect = containerRef.current?.getBoundingClientRect()
    setEdgeHover({ id: edgeId, x: event.clientX - (rect?.left ?? 0), y: event.clientY - (rect?.top ?? 0) })
  }

  useTraceParticle(scene, particleRef, highlight.traceActiveEdgeId, isMotionOn)

  return (
    <div className="atlas-canvas" ref={containerRef} data-motion={isMotionOn ? 'on' : 'paused'}>
      <div className="atlas-status" aria-live="polite" aria-atomic="true">
        <span className="atlas-status__eyebrow">Research connections</span>
        <span className="atlas-status__detail">
          <i className={`atlas-status__signal${isMotionOn && scene.isSettling ? ' is-settling' : ''}`} aria-hidden="true" />
          {scene.isSettling && isMotionOn ? 'Connections settling' : props.viewMode === 'focused' ? 'Focused view' : 'Explore view'}
          <span aria-hidden="true"> · </span>{nodes.length} items
        </span>
        {props.hiddenSourceCount > 0 && (
          <span className="atlas-status__hidden">
            {props.hiddenSourceCount} source{props.hiddenSourceCount === 1 ? '' : 's'} hidden in this view
            {props.changedCheckCount > 0 && ` · ${props.changedCheckCount} checks changed`}
          </span>
        )}
      </div>
      <svg
        ref={scene.svgRef}
        className={`atlas-svg${isMotionOn ? '' : ' is-still'}${active.hasFocus ? ' has-focus' : ''}`}
        role="img"
        aria-label={summary}
        onPointerDown={scene.pointer.onBackgroundPointerDown}
        onPointerMove={scene.pointer.onBackgroundPointerMove}
        onPointerUp={scene.pointer.onBackgroundPointerUp}
        onPointerCancel={scene.pointer.onBackgroundPointerUp}
      >
        <defs>
          <pattern id={`grid-${uid}`} ref={scene.gridRef} width="28" height="28" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="1" className="atlas-grid-dot" />
          </pattern>
          {(['base', 'route', 'selected'] as const).map((kind) => (
            <marker
              key={kind}
              id={`arrow-${kind}-${uid}`}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              markerUnits="userSpaceOnUse"
              orient="auto-start-reverse"
            >
              <path d="M0 1L9 5L0 9z" className={`atlas-arrow atlas-arrow--${kind}`} />
            </marker>
          ))}
        </defs>
        <rect className="atlas-grid" width="100%" height="100%" fill={`url(#grid-${uid})`} />
        <g ref={scene.viewportRef}>
          <g className="atlas-edges">
            {edges.map((edge) => {
              const isSelected = edge.id === highlight.selectedEdgeId
              const isRoute = highlight.routeEdgeIds.has(edge.id)
              const marker = isSelected || highlight.traceEdgeIds.has(edge.id) ? 'selected' : isRoute ? 'route' : 'base'
              const className = [
                'g-edge',
                `g-edge--${edgeLineStyle(edge)}`,
                isRoute && 'is-route',
                isSelected && 'is-selected',
                edge.id === edgeHover?.id && 'is-hovered',
                highlight.traceEdgeIds.has(edge.id) && 'is-traced',
                highlight.fullyHiddenEdgeIds.has(edge.id) && 'is-source-hidden',
                highlight.partlyHiddenEdgeIds.has(edge.id) && 'is-source-partly',
                active.hasFocus && !active.edgeIds.has(edge.id) && 'is-dim',
              ]
                .filter(Boolean)
                .join(' ')
              // Path data is written by the scene engine, not React.
              return (
                <g key={edge.id} className={className} data-edge-id={edge.id}>
                  <g ref={scene.register('edge', edge.id)}>
                    <path className="g-edge__under" />
                    <path className="g-edge__line" markerEnd={`url(#arrow-${marker}-${uid})`} />
                    <path
                      className="g-edge__hit"
                      onPointerDown={(event) => event.stopPropagation()}
                      onPointerEnter={(event) => showEdgeHover(edge.id, event)}
                      onPointerLeave={() => setEdgeHover(null)}
                      onClick={() => {
                        setEdgeHover(null)
                        onEdgeClick(edge.id)
                      }}
                    />
                  </g>
                </g>
              )
            })}
          </g>
          <g className="atlas-nodes">
            {nodes.map((node) => {
              const isSelected = node.id === highlight.selectedNodeId
              const className = [
                'g-node',
                `g-node--${node.group}`,
                `g-node--${node.role}`,
                isSelected && 'is-selected',
                node.id === highlight.hoveredNodeId && 'is-hovered',
                highlight.traceNodeIds.has(node.id) && 'is-traced',
                highlight.hiddenNodeIds.has(node.id) && 'is-source-hidden',
                active.hasFocus && !active.nodeIds.has(node.id) && 'is-dim',
              ]
                .filter(Boolean)
                .join(' ')
              return (
                <g
                  key={node.id}
                  ref={scene.register('node', node.id)}
                  className={className}
                  onPointerDown={(event) => scene.pointer.onNodePointerDown(node.id, event)}
                  onPointerMove={scene.pointer.onNodePointerMove}
                  onPointerUp={scene.pointer.onNodePointerUp}
                  onPointerCancel={scene.pointer.onNodePointerUp}
                  onPointerEnter={() => onHoverNode(node.id)}
                  onPointerLeave={() => onHoverNode(null)}
                >
                  <title>{highlight.hiddenNodeIds.has(node.id) ? `${node.fullLabel} (hidden in this view)` : node.fullLabel}</title>
                  <g ref={scene.register('inner', node.id)}>
                    {node.role !== 'regular' && (
                      <>
                        <circle className="g-node__orbit g-node__orbit--outer" r={node.radius + 15} />
                        <circle className="g-node__orbit" r={node.radius + 8} />
                      </>
                    )}
                    {isSelected && <circle className="g-node__halo" r={node.radius + 7} />}
                    <g className="g-node__core"><NodeShape group={node.group} radius={node.radius} /></g>
                  </g>
                </g>
              )
            })}
          </g>
          <circle ref={particleRef} className="atlas-particle" r="4" cx="-999" cy="-999" />
        </g>
      </svg>
      <div className="atlas-labels" aria-hidden="true">
        {nodes.map((node) => {
          const isImportant = node.role !== 'regular' || highlight.routeNodeIds.has(node.id)
          if (!(isLabelAll || isImportant || active.nodeIds.has(node.id))) return null
          const caption = ANCHOR_CAPTIONS[node.role]
          const isHidden = highlight.hiddenNodeIds.has(node.id)
          const className = [
            'g-label',
            `g-label--${node.role}`,
            caption && 'g-label--anchor',
            node.id === highlight.selectedNodeId && 'is-selected',
            active.nodeIds.has(node.id) && 'is-active',
            highlight.traceNodeIds.has(node.id) && 'is-traced',
            isHidden && 'is-source-hidden',
            active.hasFocus && !active.nodeIds.has(node.id) && 'is-dim',
          ]
            .filter(Boolean)
            .join(' ')
          return (
            <div key={node.id} ref={scene.register('label', node.id)} className={className}>
              {caption && <span className="g-label__caption">{caption}</span>}
              <span className="g-label__name">{node.shortLabel}</span>
              {isHidden && <span className="g-label__tag">hidden in this view</span>}
            </div>
          )
        })}
      </div>
      {hoveredEdge && edgeHover && (
        <div
          className="atlas-tooltip"
          role="tooltip"
          style={{ transform: `translate(${edgeHover.x + TOOLTIP_OFFSET_PX}px, ${edgeHover.y + TOOLTIP_OFFSET_PX}px)` }}
        >
          <span className="atlas-tooltip__relation">{relationLabel(hoveredEdge.relation)}</span>
          <span>
            {reviewSpec(hoveredEdge.review_status).label} · {originLabel(hoveredEdge.claim_origin)}
          </span>
          <span className="atlas-tooltip__hint">Select to read its sources</span>
        </div>
      )}
      <div className="atlas-key" aria-hidden="true">
        {(['solid', 'dashed', 'dotted'] as const).map((style) => (
          <span key={style} className="atlas-key__item">
            <svg width="26" height="8" className={`g-edge g-edge--${style}`}>
              <path className="g-edge__line" d="M1 4H25" />
            </svg>
            {KEY_LABELS[style]}
          </span>
        ))}
      </div>
      <div className="atlas-controls" role="group" aria-label="Zoom">
        <button type="button" className="atlas-control" aria-label="Zoom in" onClick={() => scene.zoomBy(ZOOM_STEP)}>
          +
        </button>
        <button type="button" className="atlas-control" aria-label="Zoom out" onClick={() => scene.zoomBy(1 / ZOOM_STEP)}>
          −
        </button>
        <button type="button" className="atlas-control" aria-label="Fit the map to the view" onClick={() => scene.fitView(true)}>
          <Icon name="fit" />
        </button>
      </div>
      {scene.isWheelHintVisible && (
        <p className="atlas-hint" role="status">
          Use Ctrl + scroll, a trackpad pinch or the zoom buttons to zoom.
        </p>
      )}
    </div>
  )
}

/** Which nodes and edges stay lit when something is hovered, selected or traced. */
function activeSets(model: GraphModel, highlight: CanvasHighlight, nodes: readonly CanvasNode[]) {
  const visible = new Set(nodes.map((n) => n.id))
  const nodeIds = new Set<string>()
  const edgeIds = new Set<string>()
  const focusNode = highlight.hoveredNodeId ?? highlight.selectedNodeId
  if (highlight.traceNodeIds.size > 0) {
    highlight.traceNodeIds.forEach((id) => nodeIds.add(id))
    highlight.traceEdgeIds.forEach((id) => edgeIds.add(id))
  } else if (focusNode) {
    nodeIds.add(focusNode)
    for (const edgeId of model.incident.get(focusNode) ?? []) {
      const edge = model.edgesById.get(edgeId)
      if (!edge || !visible.has(edge.sourceId) || !visible.has(edge.targetId)) continue
      edgeIds.add(edgeId)
      nodeIds.add(edge.sourceId)
      nodeIds.add(edge.targetId)
    }
  } else if (highlight.selectedEdgeId) {
    const edge = model.edgesById.get(highlight.selectedEdgeId)
    if (edge) {
      edgeIds.add(edge.id)
      nodeIds.add(edge.sourceId)
      nodeIds.add(edge.targetId)
    }
  }
  return { nodeIds, edgeIds, hasFocus: nodeIds.size > 0 }
}

/** A small light travelling along the edge in its recorded direction. */
function useTraceParticle(
  scene: GraphScene,
  particleRef: RefObject<SVGCircleElement | null>,
  edgeId: string | null,
  isMotionOn: boolean,
) {
  useEffect(() => {
    const particle = particleRef.current
    if (!particle) return
    const hide = () => {
      particle.setAttribute('cx', '-999')
      particle.setAttribute('cy', '-999')
    }
    const svg = scene.svgRef.current
    const selector = edgeId ? `[data-edge-id="${CSS.escape(edgeId)}"] .g-edge__line` : ''
    const path = selector && svg ? svg.querySelector<SVGPathElement>(selector) : null
    if (!path || !isMotionOn) {
      hide()
      return
    }
    const length = path.getTotalLength()
    const cancel = tween({
      duration: DURATION.traceStep,
      ease: EASE.inOutCubic,
      onFrame: (t) => {
        const point = path.getPointAtLength(t * length)
        particle.setAttribute('cx', point.x.toFixed(1))
        particle.setAttribute('cy', point.y.toFixed(1))
      },
      onDone: hide,
    })
    return () => {
      cancel()
      hide()
    }
  }, [scene.svgRef, particleRef, edgeId, isMotionOn])
}
