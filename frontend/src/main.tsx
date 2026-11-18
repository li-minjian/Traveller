/// <reference types="vite/client" />

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router';
import '@fontsource-variable/eb-garamond/wght.css';
import '@fontsource-variable/eb-garamond/wght-italic.css';
import '@fontsource-variable/plus-jakarta-sans/wght.css';
import { router } from './app/App';
import './styles.css';

const root = createRoot(document.getElementById('root')!);

function renderApp(scenario?: string) {
  root.render(
    <StrictMode>
      {import.meta.env.DEV && scenario && <p role="status">Mock API active · {scenario}</p>}
      <RouterProvider router={router} />
    </StrictMode>,
  );
}

if (import.meta.env.DEV && import.meta.env.MODE === 'mock') {
  import('./mocks/browser')
    .then(({ startMockApi }) => startMockApi())
    .then(renderApp)
    .catch((error: unknown) => {
      console.error(error);
      root.render(<p role="alert">The development Mock API could not start. See the browser console.</p>);
    });
} else {
  renderApp();
}
