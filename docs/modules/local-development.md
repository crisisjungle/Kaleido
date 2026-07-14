# Local Development Runtime

Kaleido keeps both local development services on explicit addresses: the Vite frontend uses `127.0.0.1:3000`, and the Flask backend uses `127.0.0.1:5001`. The frontend proxy points to that backend port. Local development must not silently move either service when its configured port is busy.

## Stable Backend Watchdog

- `npm run backend:stable` starts a detached supervisor and waits until `GET /health` succeeds.
- The supervisor keeps running after the launching terminal or Codex command ends.
- The backend is restarted on the same port when its process exits or when two consecutive five-second health checks fail.
- Stable backend mode disables Flask's file-change reloader. Code edits no longer kill in-flight Step 1 compose requests or Step 3 runtime polling; after backend code, dependency, or configuration changes, restart intentionally with `npm run backend:stable:restart`.
- An unrelated listener on port `5001` is reported with its PID and command. The watchdog does not kill an unknown process and does not select a fallback port.
- Runtime state and logs live under ignored `backend/logs/` files, so watchdog operation does not dirty the repository.
- The frontend has the same detached supervision contract on port `3000`. Its health check verifies that the Vite HTML application shell is complete; automatic restarts disable browser auto-open so a recovery does not create new tabs.
- The frontend watchdog also keeps a lightweight legacy redirect on `127.0.0.1:3001` when that port is free. This does not make `3001` a supported development port; it only sends stale browser tabs back to the fixed `3000` address.
- `npm run dev` ensures both stable services are available and then returns. Closing the launching terminal does not stop either service.

## Maintenance Commands

- Start or ensure running: `npm run backend:stable`
- Inspect process, listener, health, and restart state: `npm run backend:stable:status`
- Restart intentionally after backend dependency or configuration changes: `npm run backend:stable:restart`
- Read the latest runtime log: `npm run backend:stable:logs`
- Stop both the supervised backend and watchdog: `npm run backend:stable:stop`
- Start or ensure the full local stack: `npm run dev`
- Inspect both services: `npm run dev:status`
- Restart both services intentionally: `npm run dev:restart`
- Stop both services and watchdogs: `npm run dev:stop`
- Frontend-only commands follow the same pattern: `frontend:stable`, `frontend:stable:status`, `frontend:stable:restart`, `frontend:stable:logs`, and `frontend:stable:stop`.

The fixed host, port, legacy redirect ports, health interval, and failure threshold can be overridden for isolated diagnosis through the `KALEIDO_BACKEND_*` and `KALEIDO_FRONTEND_*` variables implemented by their watchdog scripts. The normal product-development path should retain ports `3000` and `5001` because `frontend/vite.config.js` uses that pair.

## Known Boundaries

- This is a local development process supervisor, not a production deployment mechanism or an operating-system login item.
- Docker and production already use their own `restart: unless-stopped` lifecycle and must continue to follow the repository safe-deployment rules.
- After generated Python dependencies or environment configuration change, use the explicit restart command rather than relying on a health failure.

## History

- 2026-07-14: Disabled Flask file-change reloading in `backend:stable` so long Step 1/Step 3 local requests are not interrupted by backend test, script, or service edits; explicit restart remains the supported way to apply backend changes.
- 2026-07-13: Adapted the proven RCDF stable-development watchdog for Kaleido. Fixed the backend to `127.0.0.1:5001`, added detached supervision and health-based restart, and changed the root development command to preserve the backend when the frontend terminal exits.
- 2026-07-13: Extended the same fixed-port supervision to Vite on `127.0.0.1:3000`; the root development lifecycle now starts, inspects, restarts, and stops the two independently supervised services together.
- 2026-07-13: Added a stale-tab guard for the former `3001` frontend URL. When available, the frontend supervisor redirects `127.0.0.1:3001` back to the fixed `3000` port so old browser tabs do not look like service outages.
