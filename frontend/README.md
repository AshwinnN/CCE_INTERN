# CCE Frontend MVP

Fresh React/Vite frontend for the CoStrategix Context Engine (CCE). The backend is intentionally unchanged.

## What is included

- Temporary demo login isolated in `src/config/auth.ts` and `.env`
- CoStrategix-inspired top navigation with active-page underline
- Minimal footer with CoStrategix wordmark and copyright
- Domains: list + create
- Sources: list + register + details + test + ingest
- Ingestion Run: automatic 3-second status polling while non-terminal, loader during checks, and manual Refresh
- Knowledge proposals: list + review/edit + approve/reject
- Packages: list + detail + active version + immutable version view
- Query: governed `/query` call and side-by-side Context ON / Context OFF proof view
- Reusable API client, loader, feedback, modal, buttons, fields and status badges

## Backend API used

The frontend calls the current root-level HTTP routes from `backend/src/cce/http/app.py` (no `/api/v1` prefix):

`/domains`, `/sources`, `/sources/{id}/test`, `/sources/{id}/ingest`, `/ingestion-runs/{id}`, `/proposals`, `/proposals/{id}`, `/proposals/{id}/approve`, `/proposals/{id}/reject`, `/packages`, `/packages/{domain_id}/active`, `/packages/{package_id}`, `/packages/{package_id}/versions/{version}`, `/query`.

The diagnostic `/retrieve` endpoint is intentionally not exposed in normal UI.

## Install and run

### 1. Prerequisites

- Node.js 20.19+ (Node 22 LTS is recommended)
- npm 10+
- CCE backend running on its HTTP port (default expected: `http://localhost:8000`)

### 2. Configure frontend

From `frontend`:

```powershell
copy .env.example .env
```

Edit `.env` if needed:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_DEMO_USERNAME=cce-admin
VITE_DEMO_PASSWORD=cce-admin
VITE_ACTOR_ID=cce-demo-user
VITE_ACTOR_ROLES=ADMIN,STEWARD
```

Important: `VITE_*` values are browser-visible. This login is only a temporary UI gate until SSO/authentication is added.

### 3. Install packages

```powershell
npm install
```

### 4. Start the frontend

```powershell
npm run dev
```

Open the URL shown by Vite, normally:

`http://localhost:5173`

### 5. Production build

```powershell
npm run build
npm run preview
```

## Recommended test flow

1. Sign in using the demo credentials.
2. Create a Domain.
3. Register a Snowflake, Local FS, or Azure Blob source using values valid for the running backend.
4. Open the source and click **Test connection**.
5. Click **Start ingestion**.
6. The Ingestion Run page automatically calls `GET /ingestion-runs/{run_id}` every 3 seconds until a terminal status. **Refresh** performs an immediate check.
7. Open **Knowledge** and review proposals after a COMPLETE ingestion.
8. Edit reviewed payload if needed, then Approve or Reject.
9. Open **Packages** to inspect automatically generated package versions.
10. Open **Query**, ask a question, and review Context ON vs Context OFF proof.

## Notes

- No backend files were changed by this frontend build.
- No package create/activate UI exists because the current backend automatically builds/activates packages after terminal proposal decisions.
- There is no trace-detail API in the current backend, so the query result page displays the returned `trace_id` instead of inventing a trace endpoint.
- The exact proprietary website font/logo asset could not be safely bundled from the public site in the build environment. The UI uses a close system sans stack and a local lightweight CoStrategix-style wordmark. Replace `brand-mark/brand-word` styling or add the official local SVG later if desired.
