/**
 * URLs come from data files, so only http(s) links are rendered.
 * javascript:, data: and malformed values return undefined.
 */
export function safeExternalUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : undefined
  } catch {
    return undefined
  }
}

/** Host name for link captions, e.g. "doi.org". */
export function urlHost(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, '')
  } catch {
    return url
  }
}
