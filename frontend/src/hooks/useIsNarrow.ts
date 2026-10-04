import { useEffect, useState, type RefObject } from 'react'

/** True while the element is narrower than the given width (CSS pixels). */
export function useIsNarrow(ref: RefObject<Element | null>, width: number): boolean {
  const [isNarrow, setIsNarrow] = useState(false)
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => setIsNarrow(entry.contentRect.width < width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref, width])
  return isNarrow
}
