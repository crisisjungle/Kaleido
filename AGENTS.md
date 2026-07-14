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

## User-Facing Text And Localization

- Formal product UI follows `docs/modules/result-first-output.md`: show validated business results directly and do not narrate whether internal processing succeeded or failed. Testing and diagnostics may expose success, failure, retries, model routes, confidence, fallback, and unresolved references. In the formal Step 1-4 workflow, normal completion must not add success Toasts, banners, badges, or copy; a generated result replaces the process UI directly. This rule does not permit fabricated success: when no valid artifact exists, preserve input and the last valid artifact, continue recovery or expose the next task action without presenting an internal execution judgment as the product result.
- Do not return raw backend English hard-coded labels to the frontend for anything users will read. API payload fields such as `title`, `name`, `label`, `summary`, `description`, `message`, `reason`, `rationale`, `note`, `relation_label`, `trigger_conditions`, progress text, report text, ontology descriptions, and mechanism narratives must be Simplified Chinese, or must include an explicit localized companion field such as `display_name`, `label_zh`, or `description_zh` that the frontend actually consumes.
- English identifiers are allowed only when they are machine identifiers or enums, for example `id`, `key`, `status`, `type`, `node_family`, `agent_type`, `source_type`, and relationship keys. They must never be rendered raw in the UI. Frontend views should route visible tokens through `frontend/src/utils/displayText.js` or use backend localized companion fields.
- Any LLM prompt that produces JSON later shown in Step 1/2/3/4 must explicitly require Simplified Chinese for display fields. The backend should sanitize legacy or fallback artifacts before returning them so old English summaries, snake_case labels, class names, and placeholder IDs do not leak forward.
- When adding or changing API payloads, include a quick leakage check in the implementation loop: inspect the response shape for raw English display strings, snake_case labels, class-name labels, and fallback phrases; add focused tests when the payload is part of the normal simulation/report flow.

## System Logs And Business UI

- System logs exist for testing, debugging, operations, and audit. They may truthfully show internal success, failure, timeout, retry, cancellation, model selection, fallback, confidence, unresolved references, task stages, and structured error reasons.
- A development or authorized diagnostic surface may render those system logs. This does not make the log stream part of the formal user product. Secrets, credentials, private prompts, personal data, and other sensitive values must still be redacted.
- The formal Step 1-4 business pages must not reuse system-log messages as user-facing banners, Toasts, badges, empty states, result summaries, activity feeds, or completion copy. Business components consume validated artifacts and structured state, not log prose.
- Keep diagnostic visibility and business visibility as separate surfaces. A test build may enable a system-log panel or diagnostic switch; the formal product keeps it out of the normal workflow and presents the resulting map, scene, Agent configuration, simulation state, analysis, or report directly.
- Do not weaken logs merely to make them suitable for end users. Preserve operational truth in the diagnostic channel, then project a separate result-first business DTO for the formal UI.
- Normal completion does not need a user-facing success message. The appearance or update of the validated business result is the completion feedback.
- An internal failure must not be disguised as a completed business action. Preserve the user's input and last valid artifact, retry or recover internally, and expose only the next meaningful task action when user intervention is required.

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
