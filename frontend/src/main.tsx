/// <reference types="vite/client" />

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router';
import '@fontsource-variable/eb-garamond/wght.css';
import '@fontsource-variable/eb-garamond/wght-italic.css';
import '@fontsource-variable/plus-jakarta-sans/wght.css';
import { router } from './app/App';
import './styles.css';

// The public demo is opt-in. A normal production build always uses Django.
// Local `dev:mock` continues to work without a production demo flag.
const demoMode = import.meta.env.MODE === 'demo' ||
  import.meta.env.VITE_DEMO_MODE === 'true';
const localMockMode = import.meta.env.DEV && import.meta.env.MODE === 'mock';
const mockEnabled = demoMode || localMockMode;

const root = createRoot(document.getElementById('root')!);

function renderApp(scenario?: string) {
  root.render(
    <StrictMode>
      {mockEnabled && scenario && (
        <p
          role="status"
          style={{
            margin: 0,
            padding: '0.5rem 1rem',
            textAlign: 'center',
            fontSize: '0.875rem',
            fontWeight: 600,
            color: '#352f1a',
            backgroundColor: '#fff1b8',
          }}
        >
          Demo mode · Simulated travel data · No real bookings · {scenario}
        </p>
      )}
      <RouterProvider router={router} />
    </StrictMode>,
  );
}

if (mockEnabled) {
  // Wait for the service worker before the app makes its first API request.
  import('./mocks/browser')
    .then(({ startMockApi }) => startMockApi())
    .then(renderApp)
    .catch((error: unknown) => {
      console.error(error);
      root.render(
        <p role="alert">
          The demo API could not start. Check browser support and the console.
        </p>,
      );
    });
} else {
  renderApp();
}
