/**
 * Research goals with plain-language wording. Only goals listed here are
 * offered, because each needs a definition Maria can read.
 */
import { NATURAL_HISTORY_GOAL } from '../api/requests.ts'

export interface ResearchGoal {
  id: string
  label: string
  definition: string
}

export const GOALS: readonly ResearchGoal[] = [
  {
    id: NATURAL_HISTORY_GOAL,
    label: 'Plan a natural-history study',
    definition:
      'A natural-history study follows how a condition changes over time in the people who have it. ' +
      'It shows what typically happens and helps prepare the measurements that future treatment trials will need.',
  },
]

export const DEFAULT_GOAL_ID = NATURAL_HISTORY_GOAL

/** Goals the service supports (from /api/health) that we can also explain. */
export function availableGoals(serviceGoalIds: readonly string[] | undefined): readonly ResearchGoal[] {
  if (!serviceGoalIds) return GOALS
  return GOALS.filter((goal) => serviceGoalIds.includes(goal.id))
}

export function findGoal(goalId: string): ResearchGoal | undefined {
  return GOALS.find((goal) => goal.id === goalId)
}
