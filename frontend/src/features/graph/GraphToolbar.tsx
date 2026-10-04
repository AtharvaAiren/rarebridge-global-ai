import { Icon } from '../../components/Icon.tsx'
import type { ViewMode } from './types.ts'

type GraphToolbarProps = {
  mode: ViewMode
  isMotionOn: boolean
  isMotionAvailable: boolean
  isLegendOpen: boolean
  canShowMore: boolean
  isLoadingMore: boolean
  onMode: (mode: ViewMode) => void
  onToggleMotion: () => void
  onFit: () => void
  onReset: () => void
  onToggleLegend: () => void
  onShowMore: () => void
}

export function GraphToolbar(props: GraphToolbarProps) {
  const { mode, isMotionOn, isLegendOpen } = props
  return (
    <div className="atlas-toolbar" role="toolbar" aria-label="Map controls">
      <div className="atlas-segmented" role="group" aria-label="View">
        {(['focused', 'explore'] as const).map((value) => (
          <button
            key={value}
            type="button"
            className="atlas-tool"
            aria-pressed={mode === value}
            onClick={() => props.onMode(value)}
          >
            {value === 'focused' ? 'Focused' : 'Explore'}
          </button>
        ))}
      </div>
      <div className="atlas-toolbar__group">
        <button type="button" className="atlas-tool" onClick={props.onFit}>
          <Icon name="fit" />
          Fit view
        </button>
        <button type="button" className="atlas-tool atlas-tool--motion" aria-pressed={!isMotionOn}
          onClick={props.onToggleMotion} disabled={!props.isMotionAvailable}>
          {!props.isMotionAvailable ? 'Reduced motion' : isMotionOn ? 'Pause motion' : 'Motion paused'}
        </button>
        <button type="button" className="atlas-tool" onClick={props.onReset}>
          <Icon name="retry" />
          Reset view
        </button>
        <button type="button" className="atlas-tool" aria-expanded={isLegendOpen} aria-controls="atlas-legend" onClick={props.onToggleLegend}>
          Legend
        </button>
      </div>
      {props.canShowMore && (
        <button type="button" className="atlas-tool atlas-tool--more" onClick={props.onShowMore} disabled={props.isLoadingMore}>
          {props.isLoadingMore ? 'Loading more…' : 'Show more of the map'}
        </button>
      )}
    </div>
  )
}
