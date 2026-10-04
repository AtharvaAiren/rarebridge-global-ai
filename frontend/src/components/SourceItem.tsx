import type { Source } from '../api/types.ts'
import { safeExternalUrl } from '../domain/urls.ts'
import { Icon } from './Icon.tsx'

const COMMIT_DISPLAY_LENGTH = 7

type SourceItemProps = {
  id: string
  source: Source | undefined
}

/** A source as the API describes it. Links are never built from IDs. */
export function SourceItem({ id, source }: SourceItemProps) {
  const url = safeExternalUrl(source?.url)
  const meta = [
    source?.published_on && `Published ${source.published_on}`,
    source?.source_kind && source.source_kind.replace(/_/g, ' '),
    source?.snapshot_commit && `Snapshot ${source.snapshot_commit.slice(0, COMMIT_DISPLAY_LENGTH)}`,
  ].filter(Boolean)

  return (
    <li className="source-item">
      {source && url ? (
        <a className="source-item__title" href={url} target="_blank" rel="noopener noreferrer">
          {source.title}
          <Icon name="external" />
        </a>
      ) : (
        <span className="source-item__title">{source?.title ?? id}</span>
      )}
      <span className="source-item__meta">
        <span className="rb-id">{id}</span>
        {meta.length > 0 && <> · {meta.join(' · ')}</>}
      </span>
      {source && source.aliases.length > 0 && (
        <span className="source-item__meta">Also cited as {source.aliases.join(', ')}</span>
      )}
      {source?.note && <span className="source-item__note">{source.note}</span>}
      {!source && <span className="source-item__meta">Details for this source are not in this response.</span>}
    </li>
  )
}
