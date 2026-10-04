import { reviewSpec, statusSpec, type StatusSpec } from '../domain/status.ts'
import { Icon } from './Icon.tsx'

type StatusChipProps = {
  spec: StatusSpec
}

/** Icon + exact label; colour only reinforces. */
export function StatusChip({ spec }: StatusChipProps) {
  return (
    <span className={`rb-chip status-chip status-chip--${spec.tone}`}>
      <Icon name={spec.icon} />
      {spec.label}
    </span>
  )
}

export function OutcomeChip({ state }: { state: string }) {
  return <StatusChip spec={statusSpec(state)} />
}

export function ReviewBadge({ status }: { status: string | undefined }) {
  return <StatusChip spec={reviewSpec(status)} />
}
