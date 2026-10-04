import type { OverviewResponse } from '../../api/types.ts'

/** An opened assessment takes precedence over the overview's first resource. */
export function selectedGraphAssessment(
  overview: OverviewResponse,
  openedAssessmentId?: string,
  retainedAssessmentId?: string,
): string | undefined {
  return openedAssessmentId ?? retainedAssessmentId ?? overview.opportunities[0]?.assessment_id
}
