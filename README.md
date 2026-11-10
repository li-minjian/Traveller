# Wohin

Wohin is a travel discovery and planning prototype for TU Berlin’s Project VS. **Travel search** helps you browse destinations and set concrete criteria. **Ask AI** starts from a travel wish and opens a workspace for refining, comparing and exploring the same journeys. Both use the same tab-local trip context.

## Run with Docker

Docker Compose starts the frontend, the Django backend and PostgreSQL for local development. You need Docker with Compose v2. From the repository root:

```sh
cp .env.example .env           # once: local configuration
docker compose up --build -d   # build and start all services
docker compose ps              # all three services become healthy
```

The backend applies pending database migrations on every start.

| Service | Address |
| --- | --- |
| Frontend (Vite dev server) | [http://localhost:3000](http://localhost:3000) |
| System status page | [http://localhost:3000/status](http://localhost:3000/status) |
| Backend API | [http://localhost:8000/api/v1/health/](http://localhost:8000/api/v1/health/) |
| PostgreSQL | No host port. The backend reaches it as `db` inside Compose. |

Code changes in `frontend/` and `backend/` apply without rebuilding: Vite reloads the browser and Django restarts itself. When `package-lock.json` changes, the frontend container reinstalls its dependencies on the next start, for example with `docker compose restart frontend`. After changing `backend/requirements.txt`, rebuild with `docker compose up --build -d`.

| Task | Command |
| --- | --- |
| Follow logs | `docker compose logs -f backend` (or `frontend`, `db`) |
| Run a Django command | `docker compose exec backend python manage.py <command>` |
| Apply migrations without restarting | `docker compose exec backend python manage.py migrate` |
| Stop and keep the data | `docker compose down` |
| Stop and delete all data (database and frontend dependencies) | `docker compose down -v` |

If the backend does not become healthy, `docker compose logs backend` shows the reason, for example a failed migration. If file changes do not reach the frontend container, set `WATCH_POLLING=true` in `.env` and run `docker compose up -d`.

`docker build frontend` still builds the static Nginx image of the frontend, including direct navigation to paths like `/explore/faroe-coast`. It contains no backend and does not forward `/api`. The first build needs network access for base images and packages. The running app needs no downloads.

## Develop and test

Use Node.js 22.12+ on the 22.x line, or Node.js 24+.

```sh
cd frontend
npm ci
npm run dev
```

Vite prints the local development URL. From the same directory:

```sh
npm run typecheck
npm run lint
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

### Backend connection

The frontend reaches the Django backend only through [src/api/client.ts](frontend/src/api/client.ts), using relative `/api/v1/...` URLs. `npm run dev` and `npm run preview` forward `/api` to `http://localhost:8000`. Set `API_PROXY_TARGET` to use another address. Start the backend as described in [backend/README.md](backend/README.md), then open `/status` to check the connection and to create or load a planning session. In Docker Compose the frontend container forwards `/api` to the `backend` service.

Playwright starts a Vite preview by default. Run the same suite against Compose with `WOHIN_TEST_URL=http://localhost:3000 npm run test:e2e`. Layout screenshots are saved in the ignored `frontend/test-results/` directory.

## Try the demo

- **Discover and compare**. On the homepage, choose **Nature and quiet places**. Select the Faroe Islands and Isle of Skye to compare costs, including an unknown Skye total. Open a journey, select a map stop and return to your comparison.
- **Plan a business trip**. In **Travel search**, set Leipzig, departing from Berlin, and a strict group budget of €400. Enable **Business trip**, add a 10:30 meeting and search. The morning rail fixture meets the 30-minute buffer. Open Leipzig and choose **Ask AI about this destination** to carry over the criteria.
- **Exercise edge states**. In the conversation, enter `Faroe Islands, no flights` for an empty result or `Demo error` for a recoverable search error. Try `Leipzig from Berlin, train only, max €400` or edit criteria directly. Open [Dresden](http://localhost:3000/destinations/dresden) for an example without map coordinates.

The assistant matches a small set of keywords and displays inferred values separately from confirmed ones. Prices, journey durations, meeting checks and itineraries are sample data or estimates. Session storage keeps the current tab’s criteria, prompts and selections through refresh. See the [frontend contract draft](docs/FRONTEND_CONTRACT_DRAFT.md) for the adapter boundary.

## Project references

- [Project structure, versions and data separation](docs/PROJECT_STRUCTURE.md)
- [Product scope and requirement traceability](docs/PRODUCT_SCOPE.md)
- [Journeys and design system](docs/UX_FLOW_AND_DESIGN_SYSTEM.md)
- [Frontend contract draft](docs/FRONTEND_CONTRACT_DRAFT.md)
- [Decisions and gaps](docs/DECISIONS_AND_GAPS.md)
