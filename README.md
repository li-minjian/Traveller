# Wohin

Wohin is a travel discovery and planning prototype for TU Berlin’s Project VS. **Travel search** helps you browse destinations and set concrete criteria. **Ask AI** starts from a travel wish and opens a workspace for refining, comparing and exploring the same journeys. Both use the same tab-local trip context.

## Run with Docker

From the repository root:

```sh
docker compose up --build -d
docker compose ps
curl -fsS http://localhost:3000/healthz
```

Open [http://localhost:3000](http://localhost:3000). Re-run the first command after changing the frontend. Stop the app with `docker compose down`.

The image builds a static frontend and serves it with Nginx, including direct navigation to paths like `/explore/faroe-coast`. Docker needs network access for its base images and npm installation. The running app uses local assets and fixtures.

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
