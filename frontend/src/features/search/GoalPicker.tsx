import type { ResearchGoal } from '../../domain/goals.ts'

type GoalPickerProps = {
  goals: readonly ResearchGoal[]
  value: string
  onChange: (goalId: string) => void
}

export function GoalPicker({ goals, value, onChange }: GoalPickerProps) {
  return (
    <section className="page-section" aria-labelledby="goal-title">
      <fieldset className="goal-picker">
        <legend id="goal-title" className="section-title">
          What would you like to do?
        </legend>
        <p className="section-intro">Choose the goal before opening a condition. Each resource is assessed for that particular purpose.</p>
        {goals.length === 0 ? (
          <p className="section-intro">The service did not report a goal this page can explain yet.</p>
        ) : (
          <ul className="goal-list">
            {goals.map((goal) => (
              <li key={goal.id}>
                <label className="goal-option">
                  <input
                    type="radio"
                    name="goal"
                    value={goal.id}
                    checked={goal.id === value}
                    onChange={() => onChange(goal.id)}
                    aria-describedby={`goal-${goal.id}-definition`}
                  />
                  <span className="goal-option__label">{goal.label}</span>
                  <span id={`goal-${goal.id}-definition`} className="goal-option__definition">
                    {goal.definition}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </fieldset>
    </section>
  )
}
