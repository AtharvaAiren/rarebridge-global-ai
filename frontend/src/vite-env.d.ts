/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public base URL of the RareBridge API. Empty means demo mode. Never a secret. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
