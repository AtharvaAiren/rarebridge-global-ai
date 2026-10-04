/**
 * Hand-drawn 24px line icons. Decorative only: every use sits next to a
 * text label, so they are hidden from assistive technology.
 */
const PATHS = {
  check: 'M5 12.5l4.5 4.5L19 7.5',
  question: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18 M9.6 9.4a2.5 2.5 0 1 1 3.4 2.4c-.6.3-1 .9-1 1.6v.4 M12 16.8v.2',
  list: 'M9.5 7h10 M9.5 12h10 M9.5 17h10 M5 7h.01 M5 12h.01 M5 17h.01',
  clock: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18 M12 7.5V12l3 2',
  split: 'M12 21v-7.5 M12 13.5L6 5 M12 13.5L18 5 M6 5v4.5 M6 5h4.5 M18 5v4.5 M18 5h-4.5',
  person: 'M12 4.5a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7 M5 20c1-3.6 3.8-5.6 7-5.6s6 2 7 5.6',
  x: 'M7 7l10 10 M17 7L7 17',
  slash: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18 M5.8 18.2L18.2 5.8',
  flag: 'M6 21V4 M6 4.5h11l-2.5 4 2.5 4H6',
  search: 'M10.5 4a6.5 6.5 0 1 0 0 13a6.5 6.5 0 1 0 0-13 M15.5 15.5L20.5 20.5',
  info: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18 M12 11v5.5 M12 7.6v.2',
  alert: 'M12 4L21.5 20H2.5z M12 10v4.5 M12 17.3v.2',
  archive: 'M3.5 5.5h17v4h-17z M5 9.5v9h14v-9 M10 13h4',
  live: 'M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6 M6.3 6.3a8 8 0 0 0 0 11.4 M17.7 6.3a8 8 0 0 1 0 11.4',
  arrowRight: 'M5 12h14 M13 6l6 6-6 6',
  arrowLeft: 'M19 12H5 M11 6l-6 6 6 6',
  external: 'M14 4.5h5.5V10 M19.5 4.5L11 13 M17 14v5.5H4.5V7H10',
  retry: 'M4.5 12a7.5 7.5 0 1 0 2.2-5.3 M4.5 4.5v4h4',
  fit: 'M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5',
} as const

export type IconName = keyof typeof PATHS

type IconProps = {
  name: IconName
  className?: string
}

export function Icon({ name, className }: IconProps) {
  return (
    <svg
      className={className ? `rb-icon ${className}` : 'rb-icon'}
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
