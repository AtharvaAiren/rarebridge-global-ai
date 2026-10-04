import type { NodeGroup } from './graphModel.ts'

type NodeShapeProps = {
  group: NodeGroup
  radius: number
  className?: string
}

/**
 * One distinct shape per entity group, so type never depends on colour.
 * Size reflects importance in this view, not patient count or certainty.
 */
export function NodeShape({ group, radius: r, className = 'g-node__shape' }: NodeShapeProps) {
  switch (group) {
    case 'disease':
      return <circle className={className} r={r} />
    case 'resource':
      return <rect className={className} x={-r} y={-r} width={2 * r} height={2 * r} rx={r * 0.32} />
    case 'study':
      return <polygon className={className} points={polygon(6, r * 1.08, Math.PI / 6)} />
    case 'publication':
      return (
        <path
          className={className}
          d={`M${-0.78 * r} ${-r}H${0.32 * r}L${0.78 * r} ${-0.54 * r}V${r}H${-0.78 * r}Z`}
        />
      )
    case 'people':
      return (
        <g className={className}>
          <circle r={r} className="g-node__ring" />
          <circle r={r * 0.42} />
        </g>
      )
    case 'gene':
      return <rect className={className} x={-1.35 * r} y={-0.75 * r} width={2.7 * r} height={1.5 * r} rx={0.75 * r} />
    case 'biology':
      return <polygon className={className} points={polygon(4, r * 1.25, 0)} />
    case 'phenotype':
      return <polygon className={className} points={polygon(3, r * 1.3, -Math.PI / 2)} />
  }
}

function polygon(sides: number, radius: number, rotation: number): string {
  return Array.from({ length: sides }, (_, i) => {
    const angle = rotation + (i * 2 * Math.PI) / sides
    return `${(Math.cos(angle) * radius).toFixed(2)},${(Math.sin(angle) * radius).toFixed(2)}`
  }).join(' ')
}
