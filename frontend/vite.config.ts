import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { defineConfig, loadEnv } from 'vite';
import type { Plugin } from 'vite';

// The frontend calls Django using relative /api URLs. Vite forwards these
// requests in ordinary development; the opt-in mock worker intercepts them.
const apiProxy = {
  '/api': { target: process.env.API_PROXY_TARGET || 'http://localhost:8000' },
};

function mockWorkerPlugin(): Plugin {
  const require = createRequire(import.meta.url);
  // Use the worker shipped with the installed MSW version, not a stale copy.
  const worker = readFileSync(require.resolve('msw/mockServiceWorker.js'));

  return {
    name: 'traveller-mock-worker',
    configureServer(server) {
      // Local dev: serve the worker at the origin root to cover /api.
      server.middlewares.use('/mockServiceWorker.js', (_request, response) => {
        response.setHeader('Content-Type', 'text/javascript');
        response.end(worker);
      });
    },
    generateBundle() {
      // Production demo: emit the same worker to dist/mockServiceWorker.js.
      // Normal production builds never include this plugin or mock handlers.
      this.emitFile({
        type: 'asset',
        fileName: 'mockServiceWorker.js',
        source: worker,
      });
    },
  };
}

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const demoMode = mode === 'demo' || env.VITE_DEMO_MODE === 'true';
  const localMockMode = command === 'serve' && mode === 'mock';

  return {
    oxc: { jsx: { runtime: 'automatic' } },
    plugins: demoMode || localMockMode ? [mockWorkerPlugin()] : [],
    server: {
      proxy: apiProxy,
      // WATCH_POLLING=true helps where file events don't reach the container.
      watch:
        process.env.WATCH_POLLING === 'true'
          ? { usePolling: true, interval: 300 }
          : undefined,
    },
    preview: { proxy: apiProxy },
  };
});
