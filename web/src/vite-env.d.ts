/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Where the API lives when it isn't the page's own origin. Public: compiled into the bundle. */
  readonly LEARNABLE_PUBLIC_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
