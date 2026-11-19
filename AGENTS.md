# Instructions for coding agents

These instructions apply to all automated contributors, including Codex, working in this repository.

## Git branches and pull requests

- **Do not create branches named `codex/*`, `agent/*`, `ai/*`, or any other tool-specific prefix.** Branches describe the feature or workstream, not the tool that produced them.
- Prefer `feature/<area>-<short-kebab-case-description>`; for Frontend work use `feature/frontend-<topic>` (for example, `feature/frontend-v1-uiux`) or `frontend/<topic>` if the team has agreed to that convention.
- For backend changes, use `feature/backend-<topic>`; for broader integration work, use `feature/integration-<topic>`. Use a descriptive suffix and keep names stable for the lifetime of the PR.
- **Before creating a branch**, inspect open PRs and existing feature branches. If a task continues existing work, use the designated active branch/PR or propose a new reviewable PR according to the team's preference. Do not silently create competing branches for the same change.
- Open pull requests against the agreed base (normally `main`) and link relevant issues. Never merge, force-push, delete a collaborative branch, or deploy without explicit approval.
- If a legacy PR already uses an agent-prefixed branch, prefer **GitHub's native branch rename** to preserve its reviews, CI, and references. If that is unavailable, migrate deliberately to a new named branch and PR, link the old PR, and confirm the head commits are identical before closing the old PR; leave historical branches untouched until an authorized cleanup.
- Do not describe an unmerged draft PR as completed or its feature as live.

## Frontend scope and interface ownership

- The approved V1 design direction is a minimal **Concept A landing page + Concept C AI Workspace**. Treat screenshots and the handoff as UI/UX references, not as evidence that booking, hotels, authentication, Discovery, Explore or Compare were approved.
- Keep the existing Django REST API contract in `frontend/src/api/client.ts` as the sole browser-facing backend integration. Frontend must not connect directly to the Journey Planner, Agent internals, LLM provider, or private API keys.
- Distinguish **local scripted/demo UI**, **MSW API fixtures**, and **real Django integration**. Never present mock data as live search availability, or label unverified backend behavior as implemented.
- Follow existing typecheck/lint/tests/build workflows, document the actual verification performed, and use reviewable incremental PRs.

The team decides product scope, assignment, sprint estimates, and final acceptance.
