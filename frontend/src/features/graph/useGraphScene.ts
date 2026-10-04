/**
 * The graph scene engine. React renders the SVG structure; this hook owns
 * positions, camera and animation and writes them straight to the DOM, so
 * no React state changes on animation frames.
 */
import { forceCollide, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from 'd3-force'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import { centerOn, fitCamera, lerpCamera, screenToWorld, zoomAround, type Camera, type Viewport } from './camera.ts'
import { edgeShape } from './geometry.ts'
import { hopDistances, type GraphModel, type ModelEdge } from './graphModel.ts'
import { computeLayout, labelPlacements, type LabelPlacement, type LabelSide, type Orientation, type Point } from './layout.ts'
import { DURATION, EASE, tween, type Cancel } from './motion.ts'

export interface SceneInput {
  model: GraphModel
  visibleIds: ReadonlySet<string>
  visibleKey: string
  visibleEdges: readonly ModelEdge[]
  radii: ReadonlyMap<string, number>
  /** Labels that are drawn persistently, used to keep them from overlapping. */
  labels: ReadonlyMap<string, string>
  /** Two-line anchor labels, and labels that must never be hidden as crowded. */
  anchorLabelIds: ReadonlySet<string>
  mustShowLabelIds: ReadonlySet<string>
  curvature: ReadonlyMap<string, number>
  focusDiseaseId: string
  focusResourceId?: string
  isMotionOn: boolean
  onNodeClick: (id: string) => void
  onBackgroundClick: () => void
}

const DRAG_THRESHOLD = 4
const FOCUS_ZOOM = 1.15
const FOCUS_MAX_ZOOM = 1.6
const FOCUS_MARGIN = { x: 140, top: 90, bottom: 110 }
const LABEL_DETAIL_ZOOM = 1.35
const WHEEL_ZOOM_RATE = 0.01
const WHEEL_HINT_MS = 1400
const MAX_STAGGER_STEPS = 6
/** Screen pixels between a node's outline and its label pill. */
const LABEL_OFFSET_PX = 6
/** Per side: direction from the node centre, and how the pill hangs from that point. */
const LABEL_ANCHORS: Readonly<Record<LabelSide, readonly [number, number, string]>> = {
  below: [0, 1, '-50%, 0'],
  above: [0, -1, '-50%, -100%'],
  right: [1, 0, '0, -50%'],
  left: [-1, 0, '-100%, -50%'],
}
const GRID_PARALLAX = 0.5

interface DragNode extends SimulationNodeDatum {
  id: string
  home: Point
  radius: number
}

interface DragState {
  id: string
  pointerId: number
  start: Point
  isDragging: boolean
  simulation: ReturnType<typeof forceSimulation<DragNode>> | null
}

interface PanState {
  pointerId: number
  start: Point
  camera: Camera
  hasMoved: boolean
}

type RefKind = 'node' | 'inner' | 'edge' | 'label'

const PORTRAIT_RATIO = 1.1

function orientationOf(viewport: Viewport): Orientation {
  return viewport.height > viewport.width * PORTRAIT_RATIO ? 'portrait' : 'landscape'
}

/** Capture can fail for a pointer the browser no longer tracks; dragging still works without it. */
function capturePointer(element: Element, pointerId: number): void {
  try {
    element.setPointerCapture(pointerId)
  } catch {
    // Pointer already released: nothing to capture.
  }
}

export function useGraphScene(input: SceneInput) {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const viewportRef = useRef<SVGGElement | null>(null)
  const gridRef = useRef<SVGPatternElement | null>(null)
  const nodeEls = useRef(new Map<string, SVGGElement>())
  const innerEls = useRef(new Map<string, SVGGElement>())
  const edgeEls = useRef(new Map<string, SVGGElement>())
  /** HTML label pills, positioned in screen space over the SVG. */
  const labelEls = useRef(new Map<string, HTMLElement>())
  const positions = useRef(new Map<string, Point>())
  const homes = useRef(new Map<string, Point>())
  const placements = useRef(new Map<string, LabelPlacement>())
  /** Re-place labels for the current zoom; assigned once the writers exist. */
  const settleLabelsRef = useRef<() => void>(() => {})
  const camera = useRef<Camera>({ x: 0, y: 0, k: 1 })
  const size = useRef<Viewport>({ width: 0, height: 0 })
  const hasFitted = useRef(false)
  const layoutSignature = useRef('')
  const layoutIdentity = useRef({ disease: '', resource: '', orientation: 'landscape' as Orientation })
  const cameraWasAdjusted = useRef(false)
  const cancelBirth = useRef<Cancel | null>(null)
  const cancelCamera = useRef<Cancel | null>(null)
  const drag = useRef<DragState | null>(null)
  const pan = useRef<PanState | null>(null)
  const labelDetailRef = useRef(false)
  const [isLabelDetail, setIsLabelDetail] = useState(false)
  const [orientation, setOrientation] = useState<Orientation>('landscape')
  const [isWheelHintVisible, setIsWheelHintVisible] = useState(false)
  const [isSettling, setIsSettling] = useState(false)

  const edgesByNode = useMemo(() => {
    const map = new Map<string, ModelEdge[]>()
    for (const edge of input.visibleEdges) {
      for (const id of [edge.sourceId, edge.targetId]) map.set(id, [...(map.get(id) ?? []), edge])
    }
    return map
  }, [input.visibleEdges])

  // Synced in layout effects declared first, so later layout effects see this render's values.
  const inputRef = useRef(input)
  const edgesByNodeRef = useRef(edgesByNode)
  useLayoutEffect(() => {
    inputRef.current = input
    edgesByNodeRef.current = edgesByNode
  })

  // ---------- DOM writers ----------
  const edgeD = useCallback((edge: ModelEdge): string | null => {
    const { radii, curvature } = inputRef.current
    const a = positions.current.get(edge.sourceId) ?? homes.current.get(edge.sourceId)
    const b = positions.current.get(edge.targetId) ?? homes.current.get(edge.targetId)
    if (!a || !b) return null
    return edgeShape(a, b, curvature.get(edge.id) ?? 0, radii.get(edge.sourceId) ?? 8, radii.get(edge.targetId) ?? 8).d
  }, [])

  const writeEdge = useCallback(
    (edge: ModelEdge) => {
      const el = edgeEls.current.get(edge.id)
      const d = edgeD(edge)
      if (!el || !d) return
      el.querySelectorAll('path').forEach((path) => path.setAttribute('d', d))
    },
    [edgeD],
  )

  /** Labels are HTML pills: crisp text at any zoom, placed above or below the node. */
  const writeLabel = useCallback((id: string) => {
    const label = labelEls.current.get(id)
    const point = positions.current.get(id) ?? homes.current.get(id)
    if (!label || !point) return
    const { x, y, k } = camera.current
    const radius = (inputRef.current.radii.get(id) ?? 8) * k
    const placement = placements.current.get(id) ?? 'below'
    label.dataset.crowded = String(placement === 'crowded')
    const centerX = point.x * k + x
    const centerY = point.y * k + y
    const offset = radius + LABEL_OFFSET_PX
    const [dx, dy, anchor] = LABEL_ANCHORS[placement === 'crowded' ? 'below' : placement]
    label.style.transform = `translate3d(${(centerX + dx * offset).toFixed(1)}px, ${(centerY + dy * offset).toFixed(1)}px, 0) translate(${anchor})`
  }, [])

  const writeTransform = useCallback(
    (id: string) => {
      const point = positions.current.get(id) ?? homes.current.get(id)
      const el = nodeEls.current.get(id)
      if (!point || !el) return
      el.setAttribute('transform', `translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})`)
      writeLabel(id)
    },
    [writeLabel],
  )

  /** Recompute label sides from settled positions (after layout, reset or drop). */
  const placeLabels = useCallback(() => {
    const { labels, radii } = inputRef.current
    const { anchorLabelIds, mustShowLabelIds } = inputRef.current
    const { x, y, k } = camera.current
    const { width, height } = size.current
    const bounds = width > 0 ? { left: -x / k, top: -y / k, right: (width - x) / k, bottom: (height - y) / k } : undefined
    placements.current = labelPlacements(homes.current, labels, radii, {
      scale: 1 / k,
      bounds,
      anchorIds: anchorLabelIds,
      mustShowIds: mustShowLabelIds,
    })
  }, [])

  /** One node and its edges (dragging). */
  const writeNode = useCallback(
    (id: string) => {
      writeTransform(id)
      for (const edge of edgesByNodeRef.current.get(id) ?? []) writeEdge(edge)
    },
    [writeTransform, writeEdge],
  )

  /** Every visible node and edge, once each. */
  const writeAll = useCallback(() => {
    for (const id of inputRef.current.visibleIds) writeTransform(id)
    for (const edge of inputRef.current.visibleEdges) writeEdge(edge)
  }, [writeTransform, writeEdge])

  useLayoutEffect(() => {
    settleLabelsRef.current = () => {
      placeLabels()
      writeAll()
    }
  })

  const clearBirthStyles = useCallback(() => {
    innerEls.current.forEach((el) => {
      el.style.removeProperty('opacity')
      el.removeAttribute('transform')
    })
    edgeEls.current.forEach((el) => el.style.removeProperty('opacity'))
    labelEls.current.forEach((el) => el.style.removeProperty('opacity'))
  }, [])

  // ---------- Camera ----------
  const applyCamera = useCallback((next: Camera) => {
    camera.current = next
    viewportRef.current?.setAttribute(
      'transform',
      `translate(${next.x.toFixed(1)} ${next.y.toFixed(1)}) scale(${next.k.toFixed(4)})`,
    )
    // Region captions divide by --k, so they keep a steady on-screen size.
    svgRef.current?.style.setProperty('--k', String(next.k))
    labelEls.current.forEach((_, id) => writeLabel(id))
    // The dot grid drifts at half speed: a quiet depth cue.
    gridRef.current?.setAttribute(
      'patternTransform',
      `translate(${(next.x * GRID_PARALLAX).toFixed(1)} ${(next.y * GRID_PARALLAX).toFixed(1)})`,
    )
    const isDetail = next.k >= LABEL_DETAIL_ZOOM
    if (isDetail !== labelDetailRef.current) {
      labelDetailRef.current = isDetail
      setIsLabelDetail(isDetail)
    }
  }, [writeLabel])

  const animateCamera = useCallback(
    (target: Camera) => {
      cancelCamera.current?.()
      const from = camera.current
      cancelCamera.current = tween({
        duration: inputRef.current.isMotionOn ? DURATION.camera : 0,
        ease: EASE.inOutCubic,
        onFrame: (t) => applyCamera(lerpCamera(from, target, t)),
        onDone: () => settleLabelsRef.current(),
      })
    },
    [applyCamera],
  )

  const fitView = useCallback(
    (isAnimated: boolean = true) => {
      const points = [...homes.current.values()]
      if (points.length === 0 || size.current.width === 0) return
      const target = fitCamera(points, size.current)
      cameraWasAdjusted.current = false
      if (isAnimated) animateCamera(target)
      else {
        applyCamera(target)
        settleLabelsRef.current()
      }
    },
    [animateCamera, applyCamera],
  )

  /** One node: centre on it. Several: frame them together, never too close. */
  const focusIds = useCallback(
    (ids: readonly string[]) => {
      // Inspecting is an interruption: settle once so the selected target stays
      // still while its sources are being read, then move only the camera.
      cancelBirth.current?.()
      drag.current?.simulation?.stop()
      positions.current = new Map(homes.current)
      clearBirthStyles()
      writeAll()
      setIsSettling(false)
      cameraWasAdjusted.current = true
      const points = ids
        .map((id) => homes.current.get(id) ?? positions.current.get(id))
        .filter((p): p is Point => p !== undefined)
      if (points.length === 0 || size.current.width === 0) return
      if (points.length === 1) {
        animateCamera(centerOn(points[0], Math.max(camera.current.k, FOCUS_ZOOM), size.current))
        return
      }
      const fitted = fitCamera(points, size.current, FOCUS_MARGIN)
      if (fitted.k <= FOCUS_MAX_ZOOM) {
        animateCamera(fitted)
        return
      }
      const centre = {
        x: points.reduce((sum, p) => sum + p.x, 0) / points.length,
        y: points.reduce((sum, p) => sum + p.y, 0) / points.length,
      }
      animateCamera(centerOn(centre, FOCUS_MAX_ZOOM, size.current))
    },
    [animateCamera, clearBirthStyles, writeAll],
  )

  const zoomBy = useCallback(
    (factor: number) => {
      cameraWasAdjusted.current = true
      const centre = { x: size.current.width / 2, y: size.current.height / 2 }
      animateCamera(zoomAround(camera.current, centre, factor))
    },
    [animateCamera],
  )

  // ---------- Viewport size ----------
  /** Layout may run before the first ResizeObserver callback: read the box directly. */
  const measure = () => {
    if (size.current.width > 0 || !svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    size.current = { width: rect.width, height: rect.height }
  }

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const observer = new ResizeObserver(([entry]) => {
      const previous = size.current
      const previousOrientation = orientationOf(previous)
      size.current = { width: entry.contentRect.width, height: entry.contentRect.height }
      const nextOrientation = orientationOf(size.current)
      setOrientation(nextOrientation)
      if (!hasFitted.current && homes.current.size > 0 && size.current.width > 0) {
        hasFitted.current = true
        fitView(false)
      } else if (hasFitted.current && previous.width > 0 && nextOrientation === previousOrientation) {
        cancelCamera.current?.()
        if (cameraWasAdjusted.current) {
          applyCamera({ ...camera.current,
            x: camera.current.x + (size.current.width - previous.width) / 2,
            y: camera.current.y + (size.current.height - previous.height) / 2 })
          settleLabelsRef.current()
        } else fitView(false)
      }
    })
    observer.observe(svg)
    return () => observer.disconnect()
  }, [fitView, applyCamera])

  // ---------- Layout + birth choreography ----------
  useLayoutEffect(() => {
    const { model, visibleIds, focusDiseaseId, focusResourceId, isMotionOn } = inputRef.current
    measure()
    const layoutOrientation = orientationOf(size.current)
    const nextSignature = `${focusDiseaseId}\n${focusResourceId ?? ''}\n${layoutOrientation}\n${input.visibleKey}`
    if (layoutSignature.current === nextSignature) {
      placeLabels()
      writeAll()
      return
    }
    layoutSignature.current = nextSignature
    cancelBirth.current?.()
    const previous = new Map([...positions.current].filter(([id]) => visibleIds.has(id)))
    const oldIdentity = layoutIdentity.current
    const changedOrientation = oldIdentity.orientation !== layoutOrientation
    const changedResource = oldIdentity.resource !== (focusResourceId ?? '')
    const pinned = changedOrientation ? new Map<string, Point>() : new Map([...homes.current].filter(([id]) =>
      previous.has(id) && !(changedResource && (id === oldIdentity.resource || id === focusResourceId))))
    layoutIdentity.current = { disease: focusDiseaseId, resource: focusResourceId ?? '', orientation: layoutOrientation }
    const layout = computeLayout({ model, visibleIds, focusDiseaseId, focusResourceId, pinned, orientation: layoutOrientation })
    homes.current = layout
    placeLabels()
    positions.current = previous
    const newIds = [...layout.keys()].filter((id) => !previous.has(id))
    const newIdSet = new Set(newIds)
    const movingIds = [...layout.keys()].filter((id) => {
      const from = previous.get(id)
      const to = layout.get(id)
      return from && to && Math.hypot(from.x - to.x, from.y - to.y) > 0.5
    })

    if (!hasFitted.current && size.current.width > 0) {
      hasFitted.current = true
      fitView(false)
    } else if (changedOrientation || changedResource) {
      fitView(isMotionOn)
    }

    const finish = () => {
      positions.current = new Map(layout)
      setIsSettling(false)
      clearBirthStyles()
      writeAll()
    }

    if (!isMotionOn || (newIds.length === 0 && movingIds.length === 0)) {
      finish()
      return
    }
    setIsSettling(true)

    // Each new node is born beside a neighbour already on screen (or nearer
    // the anchor disease) and settles with a small elastic overshoot.
    const isFirstReveal = previous.size === 0
    const hops = hopDistances(model, focusDiseaseId, visibleIds)
    const starts = new Map<string, Point>()
    const delays = new Map<string, number>()
    newIds.forEach((id, index) => {
      const ownHops = hops.get(id) ?? MAX_STAGGER_STEPS
      const neighbour = (edgesByNodeRef.current.get(id) ?? [])
        .map((e) => (e.sourceId === id ? e.targetId : e.sourceId))
        .find((other) => previous.has(other) || (isFirstReveal && (hops.get(other) ?? 99) < ownHops))
      const origin = neighbour ? (previous.get(neighbour) ?? layout.get(neighbour)) : layout.get(focusDiseaseId)
      const start = origin ?? layout.get(id) ?? { x: 0, y: 0 }
      starts.set(id, start)
      const step = isFirstReveal ? Math.min(ownHops, MAX_STAGGER_STEPS) : Math.min(index, 8) * 0.4
      delays.set(id, step * DURATION.birthStagger)
      positions.current.set(id, start)
      innerEls.current.get(id)?.style.setProperty('opacity', '0')
      labelEls.current.get(id)?.style.setProperty('opacity', '0')
    })
    writeAll()

    const total = (delays.size ? Math.max(...delays.values()) : 0) + DURATION.birth
    const progress = (id: string, elapsed: number) =>
      newIdSet.has(id) ? Math.min(1, Math.max(0, (elapsed - (delays.get(id) ?? 0)) / DURATION.birth)) : 1
    cancelBirth.current = tween({
      duration: total,
      ease: (t) => t,
      onFrame: (t) => {
        const elapsed = t * total
        for (const id of movingIds) {
          const from = previous.get(id)
          const to = layout.get(id)
          if (from && to) {
            const eased = EASE.inOutCubic(t)
            positions.current.set(id, { x: from.x + (to.x - from.x) * eased,
              y: from.y + (to.y - from.y) * eased })
          }
        }
        for (const id of newIds) {
          const local = progress(id, elapsed)
          const eased = EASE.outBack(local)
          const from = starts.get(id) ?? { x: 0, y: 0 }
          const to = layout.get(id) ?? from
          positions.current.set(id, { x: from.x + (to.x - from.x) * eased, y: from.y + (to.y - from.y) * eased })
          const inner = innerEls.current.get(id)
          inner?.style.setProperty('opacity', String(Math.min(1, local * 2.2)))
          inner?.setAttribute('transform', `scale(${(0.45 + 0.55 * Math.min(eased, 1.06)).toFixed(3)})`)
          labelEls.current.get(id)?.style.setProperty('opacity', String(Math.max(0, local * 2 - 0.8)))
        }
        for (const edge of inputRef.current.visibleEdges) {
          const opacity = Math.min(progress(edge.sourceId, elapsed), progress(edge.targetId, elapsed))
          edgeEls.current.get(edge.id)?.style.setProperty('opacity', opacity.toFixed(3))
        }
        writeAll()
      },
      onDone: finish,
    })
  }, [input.visibleKey, input.model, input.focusDiseaseId, input.focusResourceId, orientation,
      fitView, writeAll, clearBirthStyles, placeLabels])

  // Turning motion off mid-animation snaps everything to its settled place.
  useEffect(() => {
    if (input.isMotionOn) return
    cancelBirth.current?.()
    cancelCamera.current?.()
    drag.current?.simulation?.stop()
    setIsSettling(false)
    positions.current = new Map(homes.current)
    clearBirthStyles()
    writeAll()
  }, [input.isMotionOn, writeAll, clearBirthStyles])

  useEffect(
    () => () => {
      cancelBirth.current?.()
      cancelCamera.current?.()
      drag.current?.simulation?.stop()
    },
    [],
  )

  // ---------- Wheel zoom (Ctrl/Cmd + wheel or trackpad pinch) ----------
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    let hintTimer = 0
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) {
        setIsWheelHintVisible(true)
        window.clearTimeout(hintTimer)
        hintTimer = window.setTimeout(() => setIsWheelHintVisible(false), WHEEL_HINT_MS)
        return
      }
      event.preventDefault()
      cancelCamera.current?.()
      cameraWasAdjusted.current = true
      const rect = svg.getBoundingClientRect()
      const pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top }
      applyCamera(zoomAround(camera.current, pointer, Math.exp(-event.deltaY * WHEEL_ZOOM_RATE)))
      settleLabelsRef.current()
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => {
      svg.removeEventListener('wheel', onWheel)
      window.clearTimeout(hintTimer)
    }
  }, [applyCamera])

  // ---------- Pointer: pan the background, drag or click nodes ----------
  const localPoint = (event: PointerEvent): Point => {
    const rect = svgRef.current?.getBoundingClientRect()
    return { x: event.clientX - (rect?.left ?? 0), y: event.clientY - (rect?.top ?? 0) }
  }

  const onBackgroundPointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return
    cancelCamera.current?.()
    cameraWasAdjusted.current = true
    capturePointer(event.currentTarget, event.pointerId)
    pan.current = { pointerId: event.pointerId, start: localPoint(event), camera: camera.current, hasMoved: false }
  }

  const onBackgroundPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const state = pan.current
    if (!state || state.pointerId !== event.pointerId) return
    const point = localPoint(event)
    const dx = point.x - state.start.x
    const dy = point.y - state.start.y
    if (!state.hasMoved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
    state.hasMoved = true
    applyCamera({ ...state.camera, x: state.camera.x + dx, y: state.camera.y + dy })
  }

  const onBackgroundPointerUp = (event: PointerEvent<SVGSVGElement>) => {
    const state = pan.current
    if (!state || state.pointerId !== event.pointerId) return
    pan.current = null
    if (!state.hasMoved) inputRef.current.onBackgroundClick()
  }

  const startDragSimulation = (id: string) => {
    const { radii } = inputRef.current
    const nodes: DragNode[] = [...positions.current].map(([nodeId, p]) => ({
      id: nodeId,
      x: p.x,
      y: p.y,
      home: homes.current.get(nodeId) ?? p,
      radius: radii.get(nodeId) ?? 8,
      fx: nodeId === id ? p.x : undefined,
      fy: nodeId === id ? p.y : undefined,
    }))
    return forceSimulation<DragNode>(nodes)
      .force('x', forceX<DragNode>((n) => n.home.x).strength(0.2))
      .force('y', forceY<DragNode>((n) => n.home.y).strength(0.2))
      .force('charge', forceManyBody<DragNode>().strength(-50).distanceMax(120))
      .force('collide', forceCollide<DragNode>((n) => n.radius + 12))
      .alpha(0.45)
      .alphaTarget(0.25)
      .alphaDecay(0.06)
      .on('tick', () => {
        for (const n of nodes) positions.current.set(n.id, { x: n.x ?? n.home.x, y: n.y ?? n.home.y })
        writeAll()
      })
      .on('end', () => {
        // Neighbours return exactly home and stay still: no endless jitter.
        positions.current = new Map(homes.current)
        writeAll()
      })
  }

  const onNodePointerDown = (id: string, event: PointerEvent<SVGGElement>) => {
    if (event.button !== 0) return
    event.stopPropagation()
    capturePointer(event.currentTarget, event.pointerId)
    drag.current = { id, pointerId: event.pointerId, start: localPoint(event), isDragging: false, simulation: null }
  }

  const onNodePointerMove = (event: PointerEvent<SVGGElement>) => {
    const state = drag.current
    if (!state || state.pointerId !== event.pointerId) return
    const point = localPoint(event)
    if (!state.isDragging) {
      if (Math.hypot(point.x - state.start.x, point.y - state.start.y) < DRAG_THRESHOLD) return
      state.isDragging = true
      cancelBirth.current?.()
      setIsSettling(false)
      positions.current = new Map(homes.current)
      clearBirthStyles()
      if (inputRef.current.isMotionOn) state.simulation = startDragSimulation(state.id)
    }
    const world = screenToWorld(camera.current, point)
    const simNode = state.simulation?.nodes().find((n) => n.id === state.id)
    if (simNode) {
      simNode.fx = world.x
      simNode.fy = world.y
    } else {
      positions.current.set(state.id, world)
      writeNode(state.id)
    }
  }

  const onNodePointerUp = (event: PointerEvent<SVGGElement>) => {
    const state = drag.current
    if (!state || state.pointerId !== event.pointerId) return
    drag.current = null
    if (!state.isDragging) {
      inputRef.current.onNodeClick(state.id)
      return
    }
    // The dropped position becomes this node's home.
    const dropped = positions.current.get(state.id)
    if (dropped) homes.current.set(state.id, dropped)
    placeLabels()
    state.simulation?.alphaTarget(0)
  }

  // ---------- Reset: undo drags with the deterministic layout ----------
  const resetLayout = useCallback(() => {
    const { model, visibleIds, focusDiseaseId, focusResourceId, isMotionOn } = inputRef.current
    cancelBirth.current?.()
    drag.current?.simulation?.stop()
    clearBirthStyles()
    const layout = computeLayout({
      model,
      visibleIds,
      focusDiseaseId,
      focusResourceId,
      orientation: orientationOf(size.current),
    })
    const from = new Map(positions.current)
    setIsSettling(isMotionOn)
    homes.current = layout
    placeLabels()
    cancelBirth.current = tween({
      duration: isMotionOn ? DURATION.camera : 0,
      ease: EASE.inOutCubic,
      onFrame: (t) => {
        for (const [id, to] of layout) {
          const start = from.get(id) ?? to
          positions.current.set(id, { x: start.x + (to.x - start.x) * t, y: start.y + (to.y - start.y) * t })
        }
        writeAll()
      },
      onDone: () => setIsSettling(false),
    })
    fitView(true)
  }, [fitView, writeAll, clearBirthStyles, placeLabels])

  // ---------- Ref registration (stable callbacks per id) ----------
  // Held in state, not a ref, because render reads it to hand out callbacks.
  const [refCallbacks] = useState(() => new Map<string, (el: Element | null) => void>())
  const register = useCallback(
    (kind: RefKind, id: string) => {
      const key = `${kind}:${id}`
      const cached = refCallbacks.get(key)
      if (cached) return cached
      const targets: Record<RefKind, { current: Map<string, Element> }> = {
        node: nodeEls,
        inner: innerEls,
        edge: edgeEls,
        label: labelEls,
      }
      const callback = (el: Element | null) => {
        if (el) targets[kind].current.set(id, el)
        else targets[kind].current.delete(id)
        // A label that appears later (hover, selection) is placed straight away.
        if (el && kind === 'label') writeLabel(id)
      }
      refCallbacks.set(key, callback)
      return callback
    },
    [refCallbacks, writeLabel],
  )

  // React never owns transform or d: after every render the engine writes
  // current positions before paint, so a re-render cannot fight an animation.
  useLayoutEffect(() => {
    writeAll()
  })

  return {
    svgRef,
    viewportRef,
    gridRef,
    register,
    isLabelDetail,
    orientation,
    isWheelHintVisible,
    isSettling,
    fitView,
    focusIds,
    zoomBy,
    resetLayout,
    pointer: {
      onBackgroundPointerDown,
      onBackgroundPointerMove,
      onBackgroundPointerUp,
      onNodePointerDown,
      onNodePointerMove,
      onNodePointerUp,
    },
  }
}

export type GraphScene = ReturnType<typeof useGraphScene>
