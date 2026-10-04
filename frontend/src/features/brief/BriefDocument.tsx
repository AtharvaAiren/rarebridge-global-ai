import type { ReactNode } from 'react'
import type { BriefCheck, BriefModel } from '../../domain/brief.ts'
import { safeExternalUrl } from '../../domain/urls.ts'

type BriefDocumentProps = {
  model: BriefModel
  draftEditor: ReactNode
  draftText: string
}

/** The brief as a printable document. Every line comes from the brief model. */
export function BriefDocument({ model, draftEditor, draftText }: BriefDocumentProps) {
  return (
    <article className="brief" aria-labelledby="brief-title">
      <header className="brief__head">
        <p className="rb-label">Collaboration brief · prepared {model.preparedOn}</p>
        <h2 id="brief-title" className="brief__title" tabIndex={-1}>
          {model.resourceLabel}
        </h2>
        <p className="brief__lead">
          {model.goalLabel} for {model.diseaseName}
          {model.diseaseFullName && model.diseaseFullName !== model.diseaseName && ` (${model.diseaseFullName})`}.
        </p>
        {model.goalDefinition && <p className="brief__muted">{model.goalDefinition}</p>}
      </header>

      <BriefSection title="The resource">
        <p>
          <Link url={model.resourceUrl}>{model.resourceUrl}</Link>
        </p>
        <p>
          <strong>Access:</strong> {model.accessStatus}
        </p>
        <p>
          <strong>Overall:</strong> {model.outcomeLabel}
        </p>
        {model.outcomeNote && <p className="brief__note">{model.outcomeNote}</p>}
      </BriefSection>

      <BriefSection title="What the sources support">
        {model.supported.length === 0 ? (
          <p>No check is supported by the sources in this view.</p>
        ) : (
          <ul className="brief__list">
            {model.supported.map((check) => (
              <CheckItem key={check.question} check={check} />
            ))}
          </ul>
        )}
      </BriefSection>

      <BriefSection title="Open checks">
        <ul className="brief__list">
          {model.open.map((check) => (
            <CheckItem key={check.question} check={check} isOpen />
          ))}
        </ul>
      </BriefSection>

      {model.differences.length > 0 && (
        <BriefSection title="Relevant differences and limits">
          <ul className="brief__list">
            {model.differences.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </BriefSection>
      )}

      <BriefSection title="Proposed next step">
        <p>{model.nextStep}</p>
      </BriefSection>

      <BriefSection title="Public contact routes">
        {model.contacts.length === 0 ? (
          <p>No contact route is recorded for this assessment.</p>
        ) : (
          <ul className="brief__list">
            {model.contacts.map((contact) => (
              <li key={contact.label}>
                <strong>{contact.label}</strong>{' '}
                <span className="brief__muted">
                  ({contact.kind}; {contact.reviewLabel})
                </span>
                <br />
                {contact.role}
                <br />
                <Link url={contact.url}>{contact.url}</Link>
                {contact.isAllSourcesHidden && (
                  <>
                    <br />
                    <span className="brief__muted">Every source for this contact is hidden in this view.</span>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </BriefSection>

      <BriefSection title="Draft message">
        <p className="brief__muted">Review and edit before sending. RareBridge does not send messages.</p>
        <div className="brief__screen-only">{draftEditor}</div>
        <pre className="brief__print-only brief__draft-print">{draftText}</pre>
      </BriefSection>

      <BriefSection title="Sources">
        <ol className="brief__sources">
          {model.sources.map((source) => (
            <li key={source.id} value={source.number}>
              {source.title}
              {source.publishedOn && ` (${source.publishedOn})`}
              {source.isHidden && <strong> · hidden in this view</strong>}
              <br />
              <Link url={source.url}>{source.url}</Link>
              {source.aliases.length > 0 && <span className="brief__muted"> · also {source.aliases.join(', ')}</span>}
            </li>
          ))}
        </ol>
      </BriefSection>

      {model.hiddenSources.length > 0 && (
        <BriefSection title="Sources hidden in this view">
          <p>This brief reflects the assessment with these sources hidden:</p>
          <ul className="brief__list">
            {model.hiddenSources.map((source) => (
              <li key={source.id}>
                {source.title} <span className="brief__muted">({source.id})</span>
              </li>
            ))}
          </ul>
        </BriefSection>
      )}

      <footer className="brief__footer">
        <p>{model.generation}</p>
        <p>{model.dataNote}</p>
        <p>{model.coverage}</p>
        <p>{model.limitations}</p>
        <p className="brief__disclaimer">
          {model.disclaimer} Prepared {model.preparedOn}.
        </p>
      </footer>
    </article>
  )
}

function BriefSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="brief__section">
      <h3 className="brief__section-title">{title}</h3>
      {children}
    </section>
  )
}

function CheckItem({ check, isOpen = false }: { check: BriefCheck; isOpen?: boolean }) {
  const refs = check.sourceNumbers.length > 0 ? ` [${check.sourceNumbers.join(', ')}]` : ''
  return (
    <li>
      <strong>{check.question}</strong>
      {refs}
      {isOpen && (
        <>
          <br />
          <span className="brief__muted">
            {check.statusLabel}
            {!check.isRequired && ', not required'}
          </span>
          <br />
          Next question: {check.nextQuestion}
          <br />
          Who could answer: {check.contactRole}
        </>
      )}
      {!isOpen &&
        check.rationale.map((line) => (
          <span key={line} className="brief__rationale">
            {line}
          </span>
        ))}
    </li>
  )
}

function Link({ url, children }: { url: string; children: ReactNode }) {
  const safe = safeExternalUrl(url)
  return safe ? (
    <a href={safe} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ) : (
    <span>{children}</span>
  )
}
