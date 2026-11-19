import { Compass } from 'lucide-react';
import { useLayoutEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import {
  Link,
  NavLink,
  Outlet,
  ScrollRestoration,
  createBrowserRouter,
  useLocation,
} from 'react-router';
import { ChatPage } from '../features/Chat';
import { SystemStatusPage } from '../features/SystemStatus';
import { LandingPage } from '../features/v1/LandingPage';
import { WorkspacePage } from '../features/v1/WorkspacePage';

function Layout({ children }: { children?: ReactNode }) {
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
          <nav className="site-nav" aria-label="Main">
            <NavLink to="/chat?view=classic">Chat</NavLink>
            <NavLink to="/status">Status</NavLink>
          </nav>
        </div>
      </header>
      <main id="main-content" tabIndex={-1} ref={main}>
        {children ?? <Outlet />}
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

function ChatRoute() {
  const { search } = useLocation();
  if (new URLSearchParams(search).get('view') === 'classic') {
    return <Layout><ChatPage /></Layout>;
  }
  return <WorkspacePage />;
}

export const routes = [
  { index: true, element: <LandingPage /> },
  { path: 'chat', element: <ChatRoute /> },
  {
    element: <Layout />,
    children: [
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
];

export const router = createBrowserRouter(routes);
