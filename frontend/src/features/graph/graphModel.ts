/**
 * Read-only model built from a copy of the graph response. Renderer state
 * (positions, animation) lives elsewhere and never flows back into this.
 * Pure module: tested under Node.
 */
import type { GraphEdge, GraphNode, GraphResponse, RecordedRoute, SourceMap } from '../../api/types.ts'
import { canonicalId } from '../../domain/assessment.ts'
import { diseaseDisplayName } from '../../domain/diseases.ts'

export type NodeGroup = 'disease' | 'resource' | 'study' | 'publication' | 'people' | 'gene' | 'biology' | 'phenotype'

const GROUP_BY_TYPE: Readonly<Record<string, NodeGroup>> = {
  disease: 'disease',
  asset: 'resource',
  study: 'study',
  publication: 'publication',
  source: 'publication',
  organization: 'people',
  researcher: 'people',
  study_team: 'people',
  gene: 'gene',
  phenotype: 'phenotype',
}

/** Claims, processes, cell types and other biology terms share one group. */
export function nodeGroup(type: string): NodeGroup {
  return GROUP_BY_TYPE[type] ?? 'biology'
}

export const GROUP_LABELS: Readonly<Record<NodeGroup, string>> = {
  disease: 'Disease',
  resource: 'Research resource',
  study: 'Study',
  publication: 'Publication',
  people: 'Organization, team or researcher',
  gene: 'Gene',
  biology: 'Biology: mechanism, process or cell type',
  phenotype: 'Symptom or feature',
}

const TYPE_LABELS: Readonly<Record<string, string>> = {
  disease: 'Disease',
  asset: 'Research resource',
  study: 'Study',
  publication: 'Publication',
  organization: 'Organization',
  researcher: 'Researcher',
  study_team: 'Study team',
  gene: 'Gene',
  phenotype: 'Symptom or feature',
  claim: 'Mechanism claim',
  process: 'Biological process',
  cell_type: 'Cell type',
}

export function nodeTypeLabel(type: string): string {
  const known = TYPE_LABELS[type]
  if (known) return known
  const words = type.replace(/[_-]+/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1) : 'Other'
}

export interface ModelEdge extends GraphEdge {
  /** Endpoint IDs kept separately from anything a renderer might attach. */
  readonly sourceId: string
  readonly targetId: string
}

export interface GraphModel {
  readonly nodes: ReadonlyMap<string, GraphNode>
  readonly edges: readonly ModelEdge[]
  readonly edgesById: ReadonlyMap<string, ModelEdge>
  /** nodeId -> IDs of edges touching it. */
  readonly incident: ReadonlyMap<string, readonly string[]>
  readonly sources: SourceMap
  /** Edges whose endpoints were missing from the response (contract violation). */
  readonly droppedEdgeIds: readonly string[]
}

/** Accepts an ID or an object a renderer replaced it with. */
export function endpointId(endpoint: string | { id: string }): string {
  return typeof endpoint === 'string' ? endpoint : endpoint.id
}

export function buildGraphModel(response: GraphResponse): GraphModel {
  const nodes = new Map(response.nodes.map((node) => [node.id, { ...node }]))
  const edges: ModelEdge[] = []
  const droppedEdgeIds: string[] = []
  for (const edge of response.edges) {
    const sourceId = endpointId(edge.source)
    const targetId = endpointId(edge.target)
    if (!nodes.has(sourceId) || !nodes.has(targetId)) {
      droppedEdgeIds.push(edge.id)
      continue
    }
    edges.push({ ...edge, source_ids: [...edge.source_ids], sourceId, targetId })
  }
  const incident = new Map<string, string[]>()
  for (const edge of edges) {
    for (const id of [edge.sourceId, edge.targetId]) incident.set(id, [...(incident.get(id) ?? []), edge.id])
  }
  return {
    nodes,
    edges,
    edgesById: new Map(edges.map((edge) => [edge.id, edge])),
    incident,
    sources: response.sources,
    droppedEdgeIds,
  }
}

export type LineStyle = 'solid' | 'dashed' | 'dotted'

/**
 * Origin and review are encoded separately: inferred links are dotted even
 * when their source was checked, so checked navigation never looks like
 * proven biology. Otherwise pending is dashed and checked is solid.
 */
export function edgeLineStyle(edge: Pick<GraphEdge, 'claim_origin' | 'review_status'>): LineStyle {
  if (edge.claim_origin === 'inferred') return 'dotted'
  return edge.review_status === 'source_checked' ? 'solid' : 'dashed'
}

export interface FocusContext {
  diseaseId: string
  assessmentId?: string
  routes: readonly RecordedRoute[]
  relatedDiseaseIds: readonly string[]
  contactIds: readonly string[]
}

/** The asset an assessment is scoped to, from its assessment_scope edge. */
export function assessmentAssetId(model: GraphModel, assessmentId: string | undefined): string | undefined {
  if (!assessmentId) return undefined
  return model.edges.find((e) => e.relation === 'assessment_scope' && e.assessment_id === assessmentId)?.targetId
}

/**
 * Focused view: only real nodes that tell the route story. Edges between
 * them are the response's own edges; nothing is synthesised.
 */
export function focusedNodeIds(model: GraphModel, ctx: FocusContext): Set<string> {
  const evidenceSources = model.edges
    .filter((e) => e.relation === 'evidence_for_check' && e.assessment_id === ctx.assessmentId)
    .map((e) => e.sourceId)
  const candidates = [
    ctx.diseaseId,
    assessmentAssetId(model, ctx.assessmentId),
    ...evidenceSources,
    ...ctx.routes.flatMap((route) => route.node_path ?? []),
    ...ctx.relatedDiseaseIds,
    ...ctx.contactIds,
  ]
  return new Set(candidates.filter((id): id is string => id !== undefined && model.nodes.has(id)))
}

export interface RouteCheck {
  readonly nodeIds: readonly string[]
  readonly edgeIds: readonly string[]
  readonly missingNodeIds: readonly string[]
  readonly missingEdgeIds: readonly string[]
  readonly isComplete: boolean
}

export function checkRoute(route: RecordedRoute, model: GraphModel): RouteCheck {
  const nodeIds = route.node_path ?? []
  const edgeIds = route.edge_ids ?? []
  const missingNodeIds = nodeIds.filter((id) => !model.nodes.has(id))
  const missingEdgeIds = edgeIds.filter((id) => !model.edgesById.has(id))
  return {
    nodeIds,
    edgeIds,
    missingNodeIds,
    missingEdgeIds,
    isComplete: missingNodeIds.length === 0 && missingEdgeIds.length === 0,
  }
}

export interface RouteStep {
  readonly fromId: string
  readonly toId: string
  /** Null when no listed edge joins this pair in the current view. */
  readonly edgeId: string | null
  /** True when navigation runs against the edge's recorded direction. */
  readonly isReversed: boolean
}

/** node_path is navigation order; edges keep their recorded direction. */
export function routeSteps(route: RecordedRoute, model: GraphModel): RouteStep[] {
  const path = route.node_path ?? []
  const routeEdges = (route.edge_ids ?? []).map((id) => model.edgesById.get(id)).filter((e) => e !== undefined)
  return path.slice(1).map((toId, index) => {
    const fromId = path[index]
    const forward = routeEdges.find((e) => e.sourceId === fromId && e.targetId === toId)
    const backward = routeEdges.find((e) => e.sourceId === toId && e.targetId === fromId)
    const edge = forward ?? backward
    return { fromId, toId, edgeId: edge?.id ?? null, isReversed: !forward && Boolean(backward) }
  })
}

/** Nodes one edge away. */
export function neighborIds(model: GraphModel, nodeId: string): Set<string> {
  const result = new Set<string>()
  for (const edgeId of model.incident.get(nodeId) ?? []) {
    const edge = model.edgesById.get(edgeId)
    if (edge) result.add(edge.sourceId === nodeId ? edge.targetId : edge.sourceId)
  }
  return result
}

/** Undirected hop count from a start node within the visible set. */
export function hopDistances(model: GraphModel, startId: string, visible: ReadonlySet<string>): Map<string, number> {
  const distances = new Map<string, number>([[startId, 0]])
  let frontier = [startId]
  while (frontier.length > 0) {
    const next: string[] = []
    for (const id of frontier) {
      for (const neighbor of neighborIds(model, id)) {
        if (!visible.has(neighbor) || distances.has(neighbor)) continue
        distances.set(neighbor, (distances.get(id) ?? 0) + 1)
        next.push(neighbor)
      }
    }
    frontier = next
  }
  return distances
}

/** DOI and PMID aliases name one paper; a different version is not an alias. */
export const canonicalSourceId = canonicalId

const PARALLEL_STEP = 0.22

/** Curvature per edge so parallel links between one pair stay separate. */
export function parallelCurvature(edges: readonly ModelEdge[]): Map<string, number> {
  const byPair = new Map<string, ModelEdge[]>()
  for (const edge of edges) {
    const key = [edge.sourceId, edge.targetId].sort().join('\u0000')
    byPair.set(key, [...(byPair.get(key) ?? []), edge])
  }
  const curvature = new Map<string, number>()
  for (const group of byPair.values()) {
    group.forEach((edge, index) => {
      const offset = (index - (group.length - 1) / 2) * PARALLEL_STEP
      // Relative to the pair, not the arrow, so opposite-direction edges still separate.
      const pairForward = edge.sourceId < edge.targetId
      curvature.set(edge.id, pairForward ? offset : -offset)
    })
  }
  return curvature
}

const RELATION_LABELS: Readonly<Record<string, string>> = {
  evidence_for_check: 'is cited as evidence for a check on',
  assessment_scope: 'is the target of a scoped assessment of',
  candidate_shared_annotations: 'shares some recorded annotations with',
}

export function relationLabel(relation: string): string {
  return RELATION_LABELS[relation] ?? relation.replace(/_/g, ' ')
}

const LABEL_MAX = 30

export function shortLabel(label: string, max: number = LABEL_MAX): string {
  return label.length <= max ? label : `${label.slice(0, max - 1).trimEnd()}…`
}

/** Short display name: the disease short name map, else a shortened label. */
export function nodeDisplayName(model: GraphModel, id: string): string {
  const node = model.nodes.get(id)
  if (node?.type === 'disease') return diseaseDisplayName(id, node.label)
  return shortLabel(node?.label ?? id)
}
