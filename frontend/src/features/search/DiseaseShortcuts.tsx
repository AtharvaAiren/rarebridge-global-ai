import { Icon } from '../../components/Icon.tsx'
import { usePreferences } from '../../app/PreferencesContext.tsx'
import { DEMO_DISEASES } from '../../domain/diseases.ts'
import { routeHash } from '../../routing.ts'

type DiseaseShortcutsProps = {
  goalId: string
}

export function DiseaseShortcuts({ goalId }: DiseaseShortcutsProps) {
  const { isExpert } = usePreferences()
  return (
    <section className="page-section" aria-labelledby="shortcuts-title">
      <h2 id="shortcuts-title" className="section-title">
        Choose a condition to explore
      </h2>
      <p className="section-intro">
        This collection covers three diseases. If something is missing here, it is missing from this collection, not
        necessarily from research.
      </p>
      <ul className="row-list">
        {DEMO_DISEASES.map((disease) => (
          <li key={disease.id}>
            <a className="row-link" href={routeHash({ name: 'disease', diseaseId: disease.id, goal: goalId })}>
              <span className="row-link__title">{disease.shortName}<span className="product-shortcut-note">Explore resources, open questions, and public contacts</span></span>
              {isExpert && <span className="rb-id row-link__meta">{disease.id}</span>}
              <Icon name="arrowRight" className="row-link__arrow" />
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}
