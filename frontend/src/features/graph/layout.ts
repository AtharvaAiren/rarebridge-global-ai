/**
 * Deterministic force layout. Placement is a reading aid: group anchors
 * and distances say nothing about biological similarity or compatibility.
 * Pure module (d3-force only): tested under Node.
 */
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from 'd3-force'
import { nodeGroup, type GraphModel, type NodeGroup } from './graphModel.ts'

export interface Point {
  readonly x: number
  readonly y: number
}

export const WORLD = { width: 1000, height: 640 } as const

export type NodeRole = 'focusDisease' | 'focusResource' | 'regular'

/** Where each group settles. The two anchors are fixed while browsing. */
export const ANCHORS: Readonly<Record<NodeGroup | 'focusDisease' | 'focusResource', Point>> = {
  focusDisease: { x: 230, y: 330 },
  focusResource: { x: 760, y: 320 },
  disease: { x: 500, y: 470 },
  study: { x: 500, y: 200 },
  publication: { x: 760, y: 95 },
  resource: { x: 910, y: 210 },
  people: { x: 850, y: 520 },
  gene: { x: 110, y: 170 },
  biology: { x: 120, y: 470 },
  phenotype: { x: 300, y: 590 },
}

const RADIUS: Readonly<Record<NodeGroup, number>> = {
  disease: 14,
  resource: 12,
  study: 11,
  publication: 11,
  people: 10,
  gene: 8,
  biology: 7,
  phenotype: 7,
}

export function nodeRadius(group: NodeGroup, role: NodeRole): number {
  if (role === 'focusDisease') return 22
  if (role === 'focusResource') return 19
  return RADIUS[group]
}

export type Orientation = 'landscape' | 'portrait'

/** Portrait canvases (phones) read top to bottom: anchors swap axes. */
export function anchorFor(key: keyof typeof ANCHORS, orientation: Orientation = 'landscape'): Point {
  const anchor = ANCHORS[key]
  return orientation === 'portrait' ? { x: anchor.y, y: anchor.x } : anchor
}

export interface LayoutInput {
  model: GraphModel
  visibleIds: ReadonlySet<string>
  focusDiseaseId: string
  focusResourceId?: string
  /** Nodes that must not move (already on screen). */
  pinned?: ReadonlyMap<string, Point>
  ticks?: number
  orientation?: Orientation
}

interface SimNode extends SimulationNodeDatum {
  id: string
  radius: number
  anchor: Point
}

const DEFAULT_TICKS = 300
/** Labels sit under nodes and are wider than tall, so collide wider than the shape. */
const LABEL_ROOM = 38
/** Portrait canvases are zoomed further out, so each label covers more of the world. */
const PORTRAIT_LABEL_ROOM = 58

export function nodeRole(id: string, focusDiseaseId: string, focusResourceId: string | undefined): NodeRole {
  if (id === focusDiseaseId) return 'focusDisease'
  if (id === focusResourceId) return 'focusResource'
  return 'regular'
}

/** Same input, same output: seeded jitter and a seeded simulation. */
export function computeLayout(input: LayoutInput): Map<string, Point> {
  const { model, visibleIds, focusDiseaseId, focusResourceId, pinned = new Map() } = input
  const ids = [...visibleIds].filter((id) => model.nodes.has(id)).sort()
  const placed = new Map<string, Point>(pinned)

  const simNodes: SimNode[] = ids.map((id) => {
    const node = model.nodes.get(id)
    const group = nodeGroup(node?.type ?? '')
    const role = nodeRole(id, focusDiseaseId, focusResourceId)
    const anchor = anchorFor(role === 'regular' ? group : role, input.orientation)
    const fixed = pinned.get(id) ?? (role === 'regular' ? undefined : anchor)
    const start = fixed ?? startPoint(id, anchor, model, placed)
    placed.set(id, start)
    return {
      id,
      radius: nodeRadius(group, role),
      anchor,
      x: start.x,
      y: start.y,
      fx: fixed?.x,
      fy: fixed?.y,
    }
  })

  const visible = new Set(ids)
  const links = model.edges
    .filter((e) => visible.has(e.sourceId) && visible.has(e.targetId))
    .map((e) => ({ source: e.sourceId, target: e.targetId }))

  const labelRoom = input.orientation === 'portrait' ? PORTRAIT_LABEL_ROOM : LABEL_ROOM
  const simulation = forceSimulation<SimNode>(simNodes)
    .randomSource(seededRandom(7))
    .force('link', forceLink<SimNode, { source: string; target: string }>(links).id((n) => n.id).distance(110).strength(0.05))
    .force('charge', forceManyBody<SimNode>().strength(-320).distanceMax(340))
    .force('collide', forceCollide<SimNode>((n) => n.radius + labelRoom).strength(0.9).iterations(2))
    .force('x', forceX<SimNode>((n) => n.anchor.x).strength(0.14))
    .force('y', forceY<SimNode>((n) => n.anchor.y).strength(0.14))
    .stop()
  simulation.tick(input.ticks ?? DEFAULT_TICKS)

  return new Map(simNodes.map((n) => [n.id, clampToWorld({ x: n.x ?? n.anchor.x, y: n.y ?? n.anchor.y })]))
}

/** New nodes start beside an already placed neighbour, else near their anchor. */
function startPoint(id: string, anchor: Point, model: GraphModel, placed: ReadonlyMap<string, Point>): Point {
  const random = seededRandom(hashString(id))
  const neighbor = (model.incident.get(id) ?? [])
    .map((edgeId) => model.edgesById.get(edgeId))
    .map((edge) => (edge ? placed.get(edge.sourceId === id ? edge.targetId : edge.sourceId) : undefined))
    .find((point) => point !== undefined)
  const base = neighbor ?? anchor
  const angle = random() * Math.PI * 2
  const distance = 20 + random() * 30
  return { x: base.x + Math.cos(angle) * distance, y: base.y + Math.sin(angle) * distance }
}

/**
 * A loose safety bound only. The camera fits to content, so large views may
 * spread past WORLD instead of piling up against an edge.
 */
export const LAYOUT_BOUNDS = {
  minX: -WORLD.width * 0.5,
  maxX: WORLD.width * 1.5,
  minY: -WORLD.width * 0.5,
  maxY: WORLD.width * 1.5,
} as const

function clampToWorld(point: Point): Point {
  return {
    x: Math.min(LAYOUT_BOUNDS.maxX, Math.max(LAYOUT_BOUNDS.minX, point.x)),
    y: Math.min(LAYOUT_BOUNDS.maxY, Math.max(LAYOUT_BOUNDS.minY, point.y)),
  }
}

export type LabelSide = 'below' | 'above' | 'right' | 'left'
export type LabelPlacement = LabelSide | 'crowded'

const SIDES: readonly LabelSide[] = ['below', 'above', 'right', 'left']

/** Label pills in screen pixels (12px Lexend medium plus padding). */
const LABEL_CHAR_WIDTH = 6.9
const LABEL_PADDING_X = 18
const LABEL_HEIGHT = 22
const ANCHOR_CHAR_WIDTH = 7.9
const ANCHOR_LABEL_HEIGHT = 40
const LABEL_GAP = 6

export interface LabelBox {
  left: number
  right: number
  top: number
  bottom: number
}

export interface LabelOptions {
  /** World units per screen pixel (1 / zoom); labels keep their screen size. */
  scale?: number
  /** Two-line, larger labels (the disease and the selected resource). */
  anchorIds?: ReadonlySet<string>
  /** Labels that must always show; others may be marked crowded. */
  mustShowIds?: ReadonlySet<string>
  /** The visible world area: a side that would leave it is not free. */
  bounds?: LabelBox
}

function overlaps(a: LabelBox, b: LabelBox): boolean {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom
}

/**
 * Greedy placement in priority order (anchors, then must-show labels, then
 * the rest, top to bottom). Each label tries below, above, right, left, while
 * avoiding placed labels and other nodes. An optional label with no free
 * side is "crowded": it appears only on hover or selection.
 */
export function labelPlacements(
  positions: ReadonlyMap<string, Point>,
  labels: ReadonlyMap<string, string>,
  radii: ReadonlyMap<string, number>,
  options: LabelOptions = {},
): Map<string, LabelPlacement> {
  const { scale = 1, anchorIds = new Set(), mustShowIds = new Set(), bounds } = options
  const rank = (id: string) => (anchorIds.has(id) ? 0 : mustShowIds.has(id) ? 1 : 2)
  const ids = [...positions.keys()]
    .filter((id) => labels.has(id))
    .sort((a, b) => rank(a) - rank(b) || (positions.get(a)?.y ?? 0) - (positions.get(b)?.y ?? 0) || a.localeCompare(b))

  const nodeBoxes = [...positions].map(([id, p]) => {
    const r = radii.get(id) ?? 8
    return { id, box: { left: p.x - r, right: p.x + r, top: p.y - r, bottom: p.y + r } }
  })
  const placed: LabelBox[] = []
  const placement = new Map<string, LabelPlacement>()

  const boxFor = (id: string, side: LabelSide): LabelBox => {
    const point = positions.get(id) ?? { x: 0, y: 0 }
    const radius = radii.get(id) ?? 8
    const isAnchor = anchorIds.has(id)
    const text = labels.get(id) ?? ''
    const width = (text.length * (isAnchor ? ANCHOR_CHAR_WIDTH : LABEL_CHAR_WIDTH) + LABEL_PADDING_X) * scale
    const height = (isAnchor ? ANCHOR_LABEL_HEIGHT : LABEL_HEIGHT) * scale
    const gap = LABEL_GAP * scale
    switch (side) {
      case 'below':
        return { left: point.x - width / 2, right: point.x + width / 2, top: point.y + radius + gap, bottom: point.y + radius + gap + height }
      case 'above':
        return { left: point.x - width / 2, right: point.x + width / 2, top: point.y - radius - gap - height, bottom: point.y - radius - gap }
      case 'right':
        return { left: point.x + radius + gap, right: point.x + radius + gap + width, top: point.y - height / 2, bottom: point.y + height / 2 }
      case 'left':
        return { left: point.x - radius - gap - width, right: point.x - radius - gap, top: point.y - height / 2, bottom: point.y + height / 2 }
    }
  }
  const isInside = (box: LabelBox) =>
    !bounds || (box.left >= bounds.left && box.right <= bounds.right && box.top >= bounds.top && box.bottom <= bounds.bottom)
  const isFree = (id: string, box: LabelBox) =>
    isInside(box) && placed.every((other) => !overlaps(box, other)) && nodeBoxes.every((n) => n.id === id || !overlaps(box, n.box))

  for (const id of ids) {
    const side = SIDES.find((s) => isFree(id, boxFor(id, s)))
    if (side) {
      placement.set(id, side)
      placed.push(boxFor(id, side))
    } else if (rank(id) < 2) {
      placement.set(id, 'below')
      placed.push(boxFor(id, 'below'))
    } else {
      placement.set(id, 'crowded')
    }
  }
  return placement
}

export function hashString(value: string): number {
  let hash = 2166136261
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

/** mulberry32: small, fast, deterministic. */
export function seededRandom(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
