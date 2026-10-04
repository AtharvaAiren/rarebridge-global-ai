import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { useIsNarrow } from '../../hooks/useIsNarrow.ts'
import { usePreferences } from '../../app/PreferencesContext.tsx'
import type { GraphResponse, OverviewResponse } from '../../api/types.ts'
import { diseaseDisplayName } from '../../domain/diseases.ts'
import { sourceOverlay } from '../../domain/assessment.ts'
import { EvidencePanel } from '../evidence/EvidencePanel.tsx'
import type { EvidenceControls } from '../evidence/useAssessment.ts'
import { contactsById, recordedRoutes } from '../route/routes.ts'
import { GraphCanvas, type CanvasNode } from './GraphCanvas.tsx'
import { GraphInspector, type TraceView } from './GraphInspector.tsx'
import { GraphLegend } from './GraphLegend.tsx'
import { GraphList } from './GraphList.tsx'
import {
  assessmentAssetId,
  buildGraphModel,
  canonicalSourceId,
  checkRoute,
  focusedNodeIds,
  neighborIds,
  nodeGroup,
  parallelCurvature,
  routeSteps,
  shortLabel,
} from './graphModel.ts'
import { GraphToolbar } from './GraphToolbar.tsx'
import { nodeRadius, nodeRole } from './layout.ts'
import { DURATION, prefersReducedMotion } from './motion.ts'
import type { AtlasRequest, Selection, ViewMode } from './types.ts'
import { useGraphScene } from './useGraphScene.ts'

const TRACE_FIRST_STEP_MS = 350
/** Below this width only key nodes are labelled, with shorter labels. */
const COMPACT_WIDTH = 640
const COMPACT_LABEL_MAX = 20
const TRACE_STEP_GAP_MS = 140

type AtlasViewProps = {
  overview: OverviewResponse
  graph: GraphResponse
  assessmentId: string | undefined
  request: AtlasRequest | null
  canShowMore: boolean
  isLoadingMore: boolean
  expansionNotice: ReactNode
  onShowMore: () => void
  evidence: EvidenceControls
}

type SidePanel = 'evidence' | 'map'

export function AtlasView(props: AtlasViewProps) {
  const { isExpert, reducedMotion } = usePreferences()
  const { overview, graph, assessmentId, request, evidence } = props
  const evidenceState = evidence.state
  const diseaseId = overview.disease.id
  const model = useMemo(() => buildGraphModel(graph), [graph])
  const routes = useMemo(() => recordedRoutes(overview), [overview])
  const contacts = useMemo(() => contactsById(overview), [overview])
  const focusResourceId = useMemo(() => assessmentAssetId(model, assessmentId), [model, assessmentId])

  const [mode, setMode] = useState<ViewMode>('focused')
  const [selection, setSelection] = useState<Selection>({ kind: 'none' })
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [revealed, setRevealed] = useState<ReadonlySet<string>>(() => new Set())
  const [motionEnabled, setMotionEnabled] = useState(true)
  const [systemReducedMotion, setSystemReducedMotion] = useState(prefersReducedMotion)
  const isMotionAvailable = !reducedMotion && !systemReducedMotion
  const isMotionOn = motionEnabled && isMotionAvailable
  const [isLegendOpen, setIsLegendOpen] = useState(false)
  const [trace, setTrace] = useState<{ key: string; step: number } | null>(null)
  const previousResourceId = useRef(focusResourceId)
  const sectionRef = useRef<HTMLElement | null>(null)
  const pendingFocus = useRef<string[] | 'fit' | null>(null)
  const isCompact = useIsNarrow(sectionRef, COMPACT_WIDTH)
  // Which side panel shows, remembered per open assessment (no effect needed).
  const [panelChoice, setPanelChoice] = useState<{ forId: string | null; panel: SidePanel }>({ forId: null, panel: 'map' })
  const openEvidenceId = evidenceState?.assessmentId ?? null
  const sidePanel: SidePanel = !openEvidenceId ? 'map' : panelChoice.forId === openEvidenceId ? panelChoice.panel : 'evidence'
  const showMapDetails = () => setPanelChoice({ forId: openEvidenceId, panel: 'map' })

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setSystemReducedMotion(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  // A newly chosen research resource gets its own inspection context. Keep
  // the camera/layout transition, but retire the prior item or route focus.
  useEffect(() => {
    if (previousResourceId.current === focusResourceId) return
    previousResourceId.current = focusResourceId
    setSelection({ kind: 'none' })
    setHoveredId(null)
    setTrace(null)
  }, [focusResourceId])

  // ---------- Visible set: the focused story or the whole response ----------
  const focusSet = useMemo(
    () =>
      focusedNodeIds(model, {
        diseaseId,
        assessmentId,
        routes: routes.map((r) => r.route),
        relatedDiseaseIds: overview.related_diseases.map((r) => r.id),
        contactIds: [...contacts.keys()],
      }),
    [model, diseaseId, assessmentId, routes, overview.related_diseases, contacts],
  )
  const visibleKey = useMemo(() => {
    const ids = mode === 'explore' ? [...model.nodes.keys()] : [...focusSet, ...revealed].filter((id) => model.nodes.has(id))
    return [...new Set(ids)].sort().join('\n')
  }, [mode, model, focusSet, revealed])
  const visibleIds = useMemo(() => new Set(visibleKey ? visibleKey.split('\n') : []), [visibleKey])
  const visibleEdges = useMemo(
    () => model.edges.filter((e) => visibleIds.has(e.sourceId) && visibleIds.has(e.targetId)),
    [model, visibleIds],
  )
  const nodes = useMemo<CanvasNode[]>(
    () =>
      [...visibleIds].map((id) => {
        const node = model.nodes.get(id)
        const group = nodeGroup(node?.type ?? '')
        const role = nodeRole(id, diseaseId, focusResourceId)
        const label = node?.label ?? id
        return {
          id,
          group,
          role,
          radius: nodeRadius(group, role),
          shortLabel:
            node?.type === 'disease'
              ? diseaseDisplayName(id, label)
              : shortLabel(label, isCompact ? COMPACT_LABEL_MAX : undefined),
          fullLabel: label,
        }
      }),
    [visibleIds, model, diseaseId, focusResourceId, isCompact],
  )
  const radii = useMemo(() => new Map(nodes.map((n) => [n.id, n.radius])), [nodes])
  const curvature = useMemo(() => parallelCurvature(visibleEdges), [visibleEdges])
  const routeEdgeIds = useMemo(() => new Set(routes.flatMap((r) => r.route.edge_ids ?? [])), [routes])
  const routeNodeIds = useMemo(() => new Set(routes.flatMap((r) => r.route.node_path ?? [])), [routes])
  const isLabelAllBase = mode === 'focused' && !isCompact
  const selectedNodeId = selection.kind === 'node' ? selection.id : null
  const labels = useMemo(
    () =>
      new Map(
        nodes
          .filter((n) => isLabelAllBase || n.role !== 'regular' || routeNodeIds.has(n.id) || n.id === selectedNodeId)
          .map((n) => [n.id, n.shortLabel]),
      ),
    [nodes, isLabelAllBase, routeNodeIds, selectedNodeId],
  )
  const anchorLabelIds = useMemo(() => new Set(nodes.filter((n) => n.role !== 'regular').map((n) => n.id)), [nodes])
  const mustShowLabelIds = useMemo(
    () => new Set([...anchorLabelIds, ...routeNodeIds, ...(selectedNodeId ? [selectedNodeId] : [])]),
    [anchorLabelIds, routeNodeIds, selectedNodeId],
  )

  // ---------- Hidden-source overlay (this view only; records are unchanged) ----------
  const hiddenIds = useMemo(() => evidenceState?.hidden ?? [], [evidenceState?.hidden])
  const overlay = useMemo(
    () => sourceOverlay(visibleEdges, hiddenIds, (id) => canonicalSourceId(model.sources, id)),
    [visibleEdges, hiddenIds, model.sources],
  )
  const hiddenNodeIds = useMemo(() => {
    const hidden = new Set(hiddenIds.map((id) => canonicalSourceId(model.sources, id)))
    return new Set([...model.nodes.keys()].filter((id) => hidden.has(canonicalSourceId(model.sources, id))))
  }, [hiddenIds, model])

  // ---------- Route trace ----------
  const traceView = useMemo<TraceView | null>(() => {
    const entry = trace ? routes.find((r) => r.key === trace.key) : undefined
    if (!trace || !entry) return null
    return { entry, check: checkRoute(entry.route, model), steps: routeSteps(entry.route, model), step: trace.step }
  }, [trace, routes, model])
  const traceSets = useMemo(() => {
    if (!traceView) return { nodeIds: new Set<string>(), edgeIds: new Set<string>(), active: null }
    const path = traceView.entry.route.node_path ?? []
    const reachedSteps = traceView.steps.slice(0, traceView.step)
    return {
      nodeIds: new Set(path.slice(0, traceView.step + 1)),
      edgeIds: new Set(reachedSteps.map((s) => s.edgeId).filter((id): id is string => id !== null)),
      active: traceView.step > 0 ? (traceView.steps[traceView.step - 1]?.edgeId ?? null) : null,
    }
  }, [traceView])

  const stepCount = traceView?.steps.length ?? 0
  useEffect(() => {
    if (!trace || !isMotionOn || trace.step >= stepCount) return
    const delay = trace.step === 0 ? TRACE_FIRST_STEP_MS : DURATION.traceStep + TRACE_STEP_GAP_MS
    const timer = window.setTimeout(() => {
      setTrace((current) => (current && current.key === trace.key ? { ...current, step: current.step + 1 } : current))
    }, delay)
    return () => window.clearTimeout(timer)
  }, [trace, stepCount, isMotionOn])

  // ---------- Selection and commands ----------
  const clear = useCallback(() => {
    setSelection({ kind: 'none' })
    setTrace(null)
  }, [])

  const scene = useGraphScene({
    model,
    visibleIds,
    visibleKey,
    visibleEdges,
    radii,
    labels,
    anchorLabelIds,
    mustShowLabelIds,
    curvature,
    focusDiseaseId: diseaseId,
    focusResourceId,
    isMotionOn,
    onNodeClick: (id) => selectNode(id),
    onBackgroundClick: clear,
  })

  const focusWhenVisible = (ids: string[]) => {
    if (ids.every((id) => visibleIds.has(id))) scene.focusIds(ids)
    else pendingFocus.current = ids
  }

  const selectNode = (id: string) => {
    showMapDetails()
    setTrace(null)
    setSelection({ kind: 'node', id })
    if (!visibleIds.has(id)) setRevealed((current) => new Set([...current, id]))
    focusWhenVisible([id])
  }

  const selectEdge = (id: string) => {
    const edge = model.edgesById.get(id)
    if (!edge) return
    showMapDetails()
    setTrace(null)
    setSelection({ kind: 'edge', id })
    focusWhenVisible([edge.sourceId, edge.targetId])
  }

  const startTrace = (key: string) => {
    const entry = routes.find((r) => r.key === key)
    if (!entry) return
    const path = (entry.route.node_path ?? []).filter((id) => model.nodes.has(id))
    showMapDetails()
    setSelection({ kind: 'none' })
    setRevealed((current) => new Set([...current, ...path]))
    const steps = routeSteps(entry.route, model).length
    setTrace({ key, step: isMotionOn ? 0 : steps })
    focusWhenVisible(path)
  }

  const reveal = (nodeId: string) => {
    setRevealed((current) => new Set([...current, ...neighborIds(model, nodeId)]))
    pendingFocus.current = 'fit'
  }

  const changeMode = (next: ViewMode) => {
    if (next === mode) return
    setMode(next)
    if (next === 'focused') {
      setRevealed(new Set())
      if (selection.kind === 'node' && !focusSet.has(selection.id)) setSelection({ kind: 'none' })
      if (selection.kind === 'edge') setSelection({ kind: 'none' })
    }
    pendingFocus.current = 'fit'
  }

  // Camera moves that had to wait for newly revealed nodes to be laid out.
  useEffect(() => {
    const pending = pendingFocus.current
    if (!pending) return
    pendingFocus.current = null
    if (pending === 'fit') scene.fitView(true)
    else scene.focusIds(pending)
  }, [visibleKey, scene])

  // Opening the evidence view brings the map and its panel into view.
  useEffect(() => {
    if (!openEvidenceId) return
    sectionRef.current?.scrollIntoView({ behavior: isMotionOn ? 'smooth' : 'auto', block: 'start' })
    // Only a newly opened assessment should scroll, not a motion toggle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openEvidenceId])

  // Commands from the rest of the page are one-shot: only a new nonce runs them.
  const lastRequest = useRef<number | null>(null)
  const runRequest = useRef<(r: AtlasRequest) => void>(() => {})
  useEffect(() => {
    runRequest.current = (r) => {
      sectionRef.current?.scrollIntoView({ behavior: isMotionOn ? 'smooth' : 'auto', block: 'start' })
      if (r.kind === 'trace') startTrace(r.routeKey)
      else selectNode(r.nodeId)
    }
  })
  useEffect(() => {
    if (!request || request.nonce === lastRequest.current) return
    lastRequest.current = request.nonce
    runRequest.current(request)
  }, [request])

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'Escape') clear()
  }

  const hiddenNeighbourCount = (id: string) =>
    mode === 'explore' ? 0 : [...neighborIds(model, id)].filter((n) => !visibleIds.has(n)).length

  const shortName = diseaseDisplayName(diseaseId, overview.disease.label)
  const summary = `Research map around ${shortName}: ${visibleIds.size} items and ${visibleEdges.length} connections. The list view below the map gives the same content as buttons.`
  const pendingCount = visibleEdges.filter((e) => e.review_status !== 'source_checked').length

  return (
    <section ref={sectionRef} className="atlas page-section" aria-labelledby="atlas-title" onKeyDown={handleKeyDown}>
      <div className="atlas__head">
        <h2 id="atlas-title" className="section-title">
          Research map
        </h2>
        <p className="section-intro">
          Follow {shortName} through its research resources, evidence and collaborators.
          Open any connection to inspect its sources and review state.
        </p>
      </div>
      <GraphToolbar
        mode={mode}
        isMotionOn={isMotionOn}
        isMotionAvailable={isMotionAvailable}
        isLegendOpen={isLegendOpen}
        canShowMore={props.canShowMore && mode === 'explore'}
        isLoadingMore={props.isLoadingMore}
        onMode={changeMode}
        onToggleMotion={() => setMotionEnabled((value) => !value)}
        onFit={() => scene.fitView(true)}
        onReset={() => {
          clear()
          scene.resetLayout()
        }}
        onToggleLegend={() => setIsLegendOpen((value) => !value)}
        onShowMore={props.onShowMore}
      />
      {props.expansionNotice}
      {isLegendOpen && <GraphLegend />}
      <div className="atlas__stage">
        <GraphCanvas
          scene={scene}
          model={model}
          nodes={nodes}
          edges={visibleEdges}
          highlight={{
            selectedNodeId: selection.kind === 'node' ? selection.id : null,
            selectedEdgeId: selection.kind === 'edge' ? selection.id : null,
            hoveredNodeId: hoveredId,
            routeEdgeIds,
            routeNodeIds,
            traceNodeIds: traceSets.nodeIds,
            traceEdgeIds: traceSets.edgeIds,
            traceActiveEdgeId: traceSets.active,
            hiddenNodeIds,
            partlyHiddenEdgeIds: overlay.partly,
            fullyHiddenEdgeIds: overlay.fully,
          }}
          isLabelAll={isLabelAllBase || scene.isLabelDetail}
          isMotionOn={isMotionOn}
          viewMode={mode}
          hiddenSourceCount={hiddenIds.length}
          changedCheckCount={evidenceState?.current?.changed_checks.length ?? 0}
          summary={summary}
          onEdgeClick={selectEdge}
          onHoverNode={setHoveredId}
        />
        <div className="atlas__side">
          {openEvidenceId && (
            <div className="side-tabs" role="tablist" aria-label="Side panel">
              <button
                type="button"
                role="tab"
                className="side-tab"
                aria-selected={sidePanel === 'evidence'}
                onClick={() => setPanelChoice({ forId: openEvidenceId, panel: 'evidence' })}
              >
                Evidence
              </button>
              <button type="button" role="tab" className="side-tab" aria-selected={sidePanel === 'map'} onClick={showMapDetails}>
                Map details
              </button>
              <button type="button" className="rb-btn rb-btn--quiet side-tabs__close" onClick={evidence.close}>
                Close evidence
              </button>
            </div>
          )}
          {sidePanel === 'evidence' && evidenceState ? (
            <section className="inspector inspector--evidence" role="tabpanel" aria-label="Evidence">
              <EvidencePanel evidence={evidenceState} onPrepareBrief={evidence.openBrief} />
            </section>
          ) : (
          <GraphInspector
            model={model}
            overview={overview}
            selection={selection}
            trace={traceView}
            routes={routes}
            contacts={contacts}
            visibleIds={visibleIds}
            focusResourceId={focusResourceId}
            hiddenNeighbourCount={hiddenNeighbourCount}
            canShowMore={props.canShowMore}
            onSelectNode={selectNode}
            onSelectEdge={selectEdge}
            onReveal={reveal}
            onTrace={startTrace}
            onClear={clear}
            evidence={evidenceState}
            primaryAssessmentId={assessmentId}
            onOpenEvidence={evidence.open}
            onShowMore={() => {
              changeMode('explore')
              props.onShowMore()
            }}
          />
          )}
        </div>
      </div>
      <div className="atlas__footer">
        <p>
          {visibleIds.size} items · {visibleEdges.length} connections · {visibleEdges.length - pendingCount} checked
          against their source · {pendingCount} awaiting source review.
        </p>
        <details className="atlas-coverage rb-disclosure" open={isExpert}>
          <summary>Coverage and limits</summary>
          <p className="rb-meta">
            Showing {visibleIds.size} of {graph.nodes.length} items in this response, from {graph.coverage.total_nodes}
            {' '}items in the collection. Placement is a reading aid; distance does not establish biological similarity.
          </p>
          <p className="rb-meta">{graph.coverage.scope_note}</p>
        </details>
      </div>
      <GraphList
        model={model}
        nodeIds={[...visibleIds]}
        edges={visibleEdges}
        selection={selection}
        onSelectNode={selectNode}
        onSelectEdge={selectEdge}
      />
    </section>
  )
}
