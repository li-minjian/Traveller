import { defineConfig } from 'vite';

// The frontend calls the backend through relative /api URLs. The dev and
// preview servers forward them to Django. Docker Compose points
// API_PROXY_TARGET at the backend service.
const apiProxy = {
  '/api': { target: process.env.API_PROXY_TARGET || 'http://localhost:8000' },
};

export default defineConfig({
  oxc: { jsx: { runtime: 'automatic' } },
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
});
