import { defineConfig } from 'vite';

// The frontend calls the backend through relative /api URLs. The dev and
// preview servers forward them to Django. Docker Compose points
// API_PROXY_TARGET at the backend service.
const apiProxy = {
  '/api': { target: process.env.API_PROXY_TARGET || 'http://localhost:8000' },
};

export default defineConfig({
  oxc: { jsx: { runtime: 'automatic' } },
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
});
