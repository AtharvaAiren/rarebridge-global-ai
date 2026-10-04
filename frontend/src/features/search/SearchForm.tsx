import { useState, type FormEvent } from 'react'
import { Icon } from '../../components/Icon.tsx'
import { navigate } from '../../hooks/useRoute.ts'

type SearchFormProps = {
  initialQuery: string
}

export function SearchForm({ initialQuery }: SearchFormProps) {
  const [value, setValue] = useState(initialQuery)
  const [isEmptySubmit, setIsEmptySubmit] = useState(false)

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const query = value.trim()
    setIsEmptySubmit(query === '')
    if (query) navigate({ name: 'search', query })
  }

  return (
    <form role="search" className="search-form" onSubmit={handleSubmit} noValidate>
      <label htmlFor="search-input" className="rb-label">
        Disease, gene, symptom, organization or mechanism
      </label>
      <div className="rb-search">
        <Icon name="search" className="search-form__icon" />
        <input
          id="search-input"
          type="search"
          name="q"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="For example SYNGAP1"
          autoComplete="off"
          enterKeyHint="search"
          aria-describedby={isEmptySubmit ? 'search-hint' : undefined}
        />
        <button type="submit" className="rb-btn rb-btn--accent">
          Search
        </button>
      </div>
      {isEmptySubmit && (
        <p id="search-hint" className="search-form__hint" role="alert">
          Type a disease, gene, symptom, organization or mechanism first.
        </p>
      )}
    </form>
  )
}
