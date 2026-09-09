/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_BACKEND_URL?: string;
  readonly VITE_QUERY_TIMEOUT_MS?: string;
  readonly VITE_DEMO_USERNAME?: string;
  readonly VITE_DEMO_PASSWORD?: string;
  readonly VITE_ACTOR_ID?: string;
  readonly VITE_ACTOR_ROLES?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
