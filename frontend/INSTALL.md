# CCE Frontend MVP - Installation & Run

## Prerequisites
- Node.js 20.19+ (Node 22 LTS recommended)
- npm 10+
- CCE backend HTTP API running (normally http://localhost:8000)

## 1. Configure

PowerShell:

```powershell
cd frontend
copy .env.example .env
```

Edit `.env` if your backend is on another port:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_DEMO_USERNAME=cce-admin
VITE_DEMO_PASSWORD=cce-admin
VITE_ACTOR_ID=cce-demo-user
VITE_ACTOR_ROLES=ADMIN,STEWARD
```

The demo credentials are a temporary frontend-only gate. `VITE_*` values are visible in the browser and are not production authentication.

## 2. Install

```powershell
npm install
```

## 3. Run

```powershell
npm run dev
```

Open the Vite URL, normally:

http://localhost:5173

## 4. Build

```powershell
npm run build
```

## 5. Test the ingestion refresh behavior

1. Sources -> open a source.
2. Start ingestion.
3. The Ingestion Run page immediately calls `GET /ingestion-runs/{run_id}`.
4. While the status is non-terminal, it automatically checks again every 3 seconds.
5. The loader remains visible while waiting for the next status check.
6. When a terminal status is returned, polling and the loader stop.
7. The Refresh button performs an immediate status check.
