/**
 * Camera maths for the SVG viewport: screen = world * k + (x, y).
 * Pure module: tested under Node.
 */
import type { Point } from './layout.ts'

export interface Camera {
  readonly x: number
  readonly y: number
  readonly k: number
}

export interface Viewport {
  readonly width: number
  readonly height: number
}

export const ZOOM_LIMITS = { min: 0.35, max: 3 } as const

export function clampZoom(k: number): number {
  return Math.min(ZOOM_LIMITS.max, Math.max(ZOOM_LIMITS.min, k))
}

/** Labels hang below nodes and run wide, so the default margin is wider than tall. */
export const FIT_MARGIN: Margin = { x: 130, top: 90, bottom: 90 }

export interface Margin {
  readonly x: number
  readonly top: number
  readonly bottom: number
}

/** Fit points (plus a world-unit margin) inside the viewport. */
export function fitCamera(points: readonly Point[], viewport: Viewport, margin: Margin | number = FIT_MARGIN): Camera {
  if (points.length === 0 || viewport.width <= 0 || viewport.height <= 0) return { x: 0, y: 0, k: 1 }
  const m = typeof margin === 'number' ? { x: margin, top: margin, bottom: margin } : margin
  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const minX = Math.min(...xs) - m.x
  const maxX = Math.max(...xs) + m.x
  const minY = Math.min(...ys) - m.top
  const maxY = Math.max(...ys) + m.bottom
  const k = clampZoom(Math.min(viewport.width / (maxX - minX), viewport.height / (maxY - minY)))
  return centerOn({ x: (minX + maxX) / 2, y: (minY + maxY) / 2 }, k, viewport)
}

export function centerOn(point: Point, k: number, viewport: Viewport): Camera {
  return { x: viewport.width / 2 - point.x * k, y: viewport.height / 2 - point.y * k, k }
}

/** Zoom by a factor while keeping one screen point fixed. */
export function zoomAround(camera: Camera, screenPoint: Point, factor: number): Camera {
  const k = clampZoom(camera.k * factor)
  const world = screenToWorld(camera, screenPoint)
  return { x: screenPoint.x - world.x * k, y: screenPoint.y - world.y * k, k }
}

export function screenToWorld(camera: Camera, point: Point): Point {
  return { x: (point.x - camera.x) / camera.k, y: (point.y - camera.y) / camera.k }
}

export function lerpCamera(from: Camera, to: Camera, t: number): Camera {
  // Interpolate zoom geometrically so it feels even at every scale.
  const k = from.k * Math.pow(to.k / from.k, t)
  return { x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t, k }
}
