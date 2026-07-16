# Kaleido Deployment And Ops

Last updated: 2026-07-15

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

## Spatial Catalog Persistence

- Step 2 的嵌入式受控空间目录默认写入
  `backend/uploads/spatial_catalog.sqlite3`，生产环境也可通过
  `SPATIAL_CATALOG_PATH` 改到单独持久卷。
- 发布切换不得覆盖该文件；导入新版本 GeoJSON 前先执行 `--dry-run`，记录
  数据版本和摘要哈希，并备份现有目录文件。
- 当前 SQLite 目录是单机适配器。扩大到多实例或大范围数据时，应在同一
  `SpatialCatalogPort` 后接 PostGIS，而不是把 SQLite 文件复制到多个可写副本。

## Known Risks

- The repository currently has no RCDF-style single deploy script with built-in lock, manifest, backup, health check, and rollback. Manual deployments must follow the recorded release rules until that script exists.
- `latest` tags are mutable. Always record old image IDs before replacing them.
- The production `.env` contains runtime provider credentials. Do not copy it into build artifacts or print secret values in release notes.
- Kaleido currently has no database migration gate in the compose release path, but generated files, uploads, and logs still need preservation across container replacement.

## Wuhan V2 Release Boundary

`wuhan_covid_v2` is currently a local shadow fixture only. `backend/scripts/build_wuhan_showcase.py` may compile and validate local golden artifacts, but it must not deploy them, change `/demo/wuhan` away from V1, rebuild a production image, or overwrite the V1 fixture. Promotion requires separate semantic and visual acceptance, browser verification of all four direct routes, V1/V2 screenshot and playback comparison, and an explicit alias-switch change with V1 retained at `?version=v1`.
