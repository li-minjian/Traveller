import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { defineConfig } from 'vite';

// The frontend calls the backend through relative /api URLs. The dev and
// preview servers forward them to Django. Docker Compose points
// API_PROXY_TARGET at the backend service.
const apiProxy = {
  '/api': { target: process.env.API_PROXY_TARGET || 'http://localhost:8000' },
};

export default defineConfig(({ mode }) => ({
  oxc: { jsx: { runtime: 'automatic' } },
  plugins: mode === 'mock' ? [{
    name: 'traveller-mock-worker',
    apply: 'serve',
    configureServer(server) {
      // Serve the installed MSW worker at the root for /api scope.
      const require = createRequire(import.meta.url);
      const worker = readFileSync(require.resolve('msw/mockServiceWorker.js'));
      server.middlewares.use('/mockServiceWorker.js', (_request, response) => {
        response.setHeader('Content-Type', 'text/javascript');
        response.end(worker);
      });
    },
  }] : [],
  server: {
    proxy: apiProxy,
    // WATCH_POLLING=true helps where file events do not reach the container,
    // e.g. Docker on Windows with the project outside WSL.
    watch:
      process.env.WATCH_POLLING === 'true'
        ? { usePolling: true, interval: 300 }
        : undefined,
  },
  preview: { proxy: apiProxy },
}));
