# Traveller

A travel-planning prototype for TU Berlin’s Project VS.

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

`docker build frontend` still builds the static Nginx image of the frontend, including direct navigation to paths like `/status`. It contains no backend and does not forward `/api`. The first build needs network access for base images and packages. The running app needs no downloads.

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
```

### Backend connection

The frontend reaches the Django backend only through [src/api/client.ts](frontend/src/api/client.ts), using relative `/api/v1/...` URLs. `npm run dev` and `npm run preview` forward `/api` to `http://localhost:8000`. Set `API_PROXY_TARGET` to use another address. Start the backend as described in [backend/README.md](backend/README.md), then open `/status` to check the connection and to create or load a planning session. In Docker Compose the frontend container forwards `/api` to the `backend` service.

## Project references

- [Project structure, versions and data separation](docs/PROJECT_STRUCTURE.md)
