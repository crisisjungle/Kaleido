# AGENTS.md

This file is the working agreement for AI agents and automation helpers working in the Kaleido repository.

Kaleido should follow the same safe deployment discipline used across the user's long-lived projects.

## Default Working Style

- Understand the existing implementation before changing it. Inspect the relevant frontend, backend, Docker, and deployment files first.
- Preserve unrelated user changes in the working tree. Never revert files you did not intentionally change.
- Prefer small, verified implementation loops: inspect -> change -> verify -> report.
- If a request is unclear or has multiple risky directions, summarize the key decision points and ask before making broad changes.
- Treat golden/demo cases as repeatable test fixtures for the real product flow, not as separate product paths. UI or workflow problems discovered in the Wuhan demo should be fixed in the shared Step 1/2/3/4 components, APIs, projection services, or data contracts so the normal user-created simulation path benefits from the same correction.
- Maintain demo/formal-flow parity: if a line style, node style, map projection, risk-object card, region panel, Agent panel, tab behavior, or playback behavior is adjusted while looking at the Wuhan demo, implement it through the shared production component or service first, then verify the Wuhan demo as the fast visual fixture. The target is that the demo appearance and behavior represent what a newly generated formal simulation will show after the same data contract is produced.
- Keep frozen demos versioned. Shared UI/style fixes should not require regenerating deterministic demo data, but formal simulation data-contract changes must bump the golden artifact contract version and refresh the fixture so demos do not preserve old broken output.

## Safe Deployment Rules

- Do not treat the production server as the default build machine.
- For Docker deployment, prefer building images locally or in CI, pushing them to the registry, and letting the server pull prebuilt images.
- Avoid running heavy `docker compose build`, frontend builds, dependency installs, or backend environment rebuilds directly on a small production ECS during normal releases.
- Keep runtime deployment separate from data maintenance, backfills, one-off scripts, and read-only checks.
- When the working tree is dirty and only one fix should be shipped, deploy from a clean temporary tree or an explicit commit scope, not the whole local workspace.
- Keep health verification domain-aware. For Kaleido, prefer the intended domain behavior over bare-IP checks when validating production.
- Deployment scripts should preserve safety mechanisms: rollback path, health check, explicit restart scope, and clear failure reporting.

## Documentation

- Deployment incidents, deployment-rule changes, production recovery, and infrastructure changes should be recorded in a repo-owned Markdown file.
- Do not leave important project history only in chat memory.
