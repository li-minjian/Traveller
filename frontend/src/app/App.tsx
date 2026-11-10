import { Compass } from 'lucide-react';
import { useLayoutEffect, useRef } from 'react';
import {
  Link,
  Navigate,
  Outlet,
  ScrollRestoration,
  createBrowserRouter,
  useLocation,
} from 'react-router';
import { SystemStatusPage } from '../features/SystemStatus';

function Layout() {
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const lastPath = useRef(pathname);
  useLayoutEffect(() => {
    if (lastPath.current !== pathname)
      main.current?.focus({ preventScroll: true });
    lastPath.current = pathname;
  }, [pathname]);

  return (
    <>
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <header className="site-header">
        <div className="nav-wrap">
          <Link to="/" className="brand" aria-label="Traveller home">
            <Compass size={21} />
            Traveller
          </Link>
        </div>
      </header>
      <main id="main-content" tabIndex={-1} ref={main}>
        <Outlet />
      </main>
      <footer className="site-footer">
        <div className="page">
          <p>A travel-planning prototype · Project VS, TU Berlin</p>
          <span>
            <Link to="/status">System status</Link>
          </span>
        </div>
      </footer>
      <ScrollRestoration getKey={(location) => location.pathname} />
    </>
  );
}

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/status" replace /> },
      { path: 'status', element: <SystemStatusPage /> },
      {
        path: '*',
        element: (
          <section className="page system-page">
            <h1>Page unavailable</h1>
            <p>
              <Link to="/status">Open system status</Link>
            </p>
          </section>
        ),
      },
    ],
  },
]);
