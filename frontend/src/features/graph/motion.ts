/**
 * One small tween helper for every graph animation: consistent easing,
 * cancellable, and instant when motion is off (reduced motion or paused).
 */
export const EASE = {
  outCubic: (t: number) => 1 - Math.pow(1 - t, 3),
  inOutCubic: (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  /** A subtle elastic settle (overshoot ~6%). */
  outBack: (t: number) => {
    const c1 = 1.2
    const c3 = c1 + 1
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2)
  },
} as const

export const DURATION = {
  camera: 550,
  birth: 720,
  birthStagger: 85,
  fade: 320,
  traceStep: 420,
} as const

export interface TweenOptions {
  duration: number
  delay?: number
  ease?: (t: number) => number
  onFrame: (eased: number) => void
  onDone?: () => void
}

export type Cancel = () => void

/** Runs onFrame(0..1) over the duration; duration 0 completes synchronously. */
export function tween({ duration, delay = 0, ease = EASE.outCubic, onFrame, onDone }: TweenOptions): Cancel {
  if (duration <= 0 && delay <= 0) {
    onFrame(1)
    onDone?.()
    return () => {}
  }
  let frame = 0
  let start: number | null = null
  const step = (now: number) => {
    if (start === null) start = now
    const elapsed = now - start - delay
    if (elapsed < 0) {
      frame = requestAnimationFrame(step)
      return
    }
    const t = duration <= 0 ? 1 : Math.min(1, elapsed / duration)
    onFrame(ease(t))
    if (t < 1) frame = requestAnimationFrame(step)
    else onDone?.()
  }
  frame = requestAnimationFrame(step)
  return () => cancelAnimationFrame(frame)
}

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
