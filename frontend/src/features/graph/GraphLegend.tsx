import { GROUP_LABELS, type LineStyle, type NodeGroup } from './graphModel.ts'
import { NodeShape } from './NodeShape.tsx'

const GROUPS: readonly NodeGroup[] = ['disease', 'resource', 'study', 'publication', 'people', 'gene', 'biology', 'phenotype']

const LINES: ReadonlyArray<{ style: LineStyle; text: string }> = [
  { style: 'solid', text: 'Recorded or imported, fact checked against its source' },
  { style: 'dashed', text: 'Recorded or imported, source check pending' },
  { style: 'dotted', text: 'Inferred for navigation (its check status is in the details)' },
]

export function GraphLegend() {
  return (
    <div id="atlas-legend" className="atlas-legend">
      <ul className="atlas-legend__list" aria-label="Item types">
        {GROUPS.map((group) => (
          <li key={group}>
            <svg viewBox="-13 -13 26 26" width="22" height="22" aria-hidden="true" className={`g-swatch g-node--${group}`}>
              <NodeShape group={group} radius={8} />
            </svg>
            {GROUP_LABELS[group]}
          </li>
        ))}
      </ul>
      <ul className="atlas-legend__list" aria-label="Line styles">
        {LINES.map(({ style, text }) => (
          <li key={style}>
            <svg width="34" height="12" aria-hidden="true" className={`g-edge g-edge--${style} g-swatch-line`}>
              <path className="g-edge__line" d="M2 6H32" />
            </svg>
            {text}
          </li>
        ))}
        <li>
          <svg width="34" height="12" aria-hidden="true" className="g-edge is-route g-swatch-line">
            <path className="g-edge__under" d="M2 6H32" />
            <path className="g-edge__line" d="M2 6H32" />
          </svg>
          Part of a recorded study route
        </li>
      </ul>
      <p className="atlas-legend__note">
        Shapes and colours show the type of item only. Position, size and distance are a reading aid: they do not mean
        similarity, compatibility, safety, severity or confidence. Arrows point the way each relationship was recorded.
      </p>
    </div>
  )
}
