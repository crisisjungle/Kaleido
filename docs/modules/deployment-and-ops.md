# Kaleido Deployment And Ops

Last updated: 2026-07-14

## Current Production Shape

- Production runs on Aliyun ECS `8.135.60.155` under `/root/kaleido`.
- Runtime is Docker Compose with two services:
  - `kaleido-backend` from `ghcr.io/crisisjungle/kaleido-backend:latest`.
  - `kaleido-frontend` from `ghcr.io/crisisjungle/kaleido-frontend:latest`.
- The frontend container binds `127.0.0.1:8088:80`; public routing is handled outside the compose file.
- Backend and frontend runtime data are mounted from `/root/kaleido/backend/uploads` and `/root/kaleido/backend/logs`.

## Release Rules

- Do not build images on the production ECS during normal releases.
- Build Linux AMD64 images locally or in CI, then transfer or push the finished images.
- If the registry is unavailable or not authenticated, prefer `docker save` locally and `docker load` on the server over remote `docker compose build`.
- Before switching containers, record:
  - current image IDs,
  - current compose file checksum,
  - container status,
  - disk free space,
  - local server health.
- Retag the previous images before loading replacements so rollback does not depend on registry access.
- Use `docker compose -f docker-compose.prod.yml up -d --no-build --remove-orphans` for runtime switching.
- Verify `http://127.0.0.1:8088/health` from the server after restart, then verify the intended public route when available.
- On health failure, retag the saved previous images back to `latest` and rerun compose with `--no-build`.

## Build Notes

- Local Apple Silicon Docker defaults to ARM images, so production image builds must pass `--platform linux/amd64`.
- `Dockerfile.backend` must not depend on pulling the previous private production image. It uses the public uv image directly so a clean build can be reproduced without GHCR read access.
- Frontend builds run inside `frontend/Dockerfile`; the final image is nginx plus static Vite assets.

## Maintenance Entrypoints

- `docker-compose.prod.yml`
- `Dockerfile.backend`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `package.json`

## Known Risks

- The repository currently has no RCDF-style single deploy script with built-in lock, manifest, backup, health check, and rollback. Manual deployments must follow the recorded release rules until that script exists.
- `latest` tags are mutable. Always record old image IDs before replacing them.
- The production `.env` contains runtime provider credentials. Do not copy it into build artifacts or print secret values in release notes.
- Kaleido currently has no database migration gate in the compose release path, but generated files, uploads, and logs still need preservation across container replacement.
