# React UI Shell (Design Preview)

This folder contains a design-first React UI for the Cross-Platform Sync app.

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Open the local Vite URL (usually `http://localhost:5173`).

## Current scope

- Visual shell only
- Mock data for pipeline steps, logs, and run history
- Responsive layout for desktop and mobile

## Next wiring step

Connect buttons and panels to backend API endpoints (`/sync/run`, `/sync/runs`, `/sync/runs/{id}/logs`).
