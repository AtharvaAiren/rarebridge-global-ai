/**
 * Edge geometry: a quadratic curve between two node centres, trimmed so
 * the line starts and ends at the node outline. Pure module.
 */
import type { Point } from './layout.ts'

export interface EdgeShape {
  readonly d: string
  readonly mid: Point
  readonly start: Point
  readonly end: Point
}

const ARROW_GAP = 3

function unit(from: Point, to: Point): Point {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const length = Math.hypot(dx, dy) || 1
  return { x: dx / length, y: dy / length }
}

/** curvature is a fraction of the edge length, applied along the normal. */
export function edgeShape(a: Point, b: Point, curvature: number, radiusA: number, radiusB: number): EdgeShape {
  const length = Math.hypot(b.x - a.x, b.y - a.y) || 1
  const normal = { x: -(b.y - a.y) / length, y: (b.x - a.x) / length }
  const control = {
    x: (a.x + b.x) / 2 + normal.x * curvature * length,
    y: (a.y + b.y) / 2 + normal.y * curvature * length,
  }
  const startDir = unit(a, control)
  const endDir = unit(b, control)
  const start = { x: a.x + startDir.x * radiusA, y: a.y + startDir.y * radiusA }
  const end = { x: b.x + endDir.x * (radiusB + ARROW_GAP), y: b.y + endDir.y * (radiusB + ARROW_GAP) }
  // Point on the curve at t = 0.5 (for relationship labels).
  const mid = { x: 0.25 * start.x + 0.5 * control.x + 0.25 * end.x, y: 0.25 * start.y + 0.5 * control.y + 0.25 * end.y }
  const d = `M${round(start.x)} ${round(start.y)}Q${round(control.x)} ${round(control.y)} ${round(end.x)} ${round(end.y)}`
  return { d, mid, start, end }
}

function round(value: number): number {
  return Math.round(value * 10) / 10
}
