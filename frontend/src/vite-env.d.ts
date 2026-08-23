/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL for the API in production builds (default: same origin). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
