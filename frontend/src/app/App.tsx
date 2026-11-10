import { Compass, Search, Sparkles } from 'lucide-react';
import { useLayoutEffect, useRef } from 'react';
import {
  Link,
  Outlet,
  ScrollRestoration,
  createBrowserRouter,
  useLocation,
} from 'react-router';
import { ComparePage } from '../features/Compare';
import { DestinationPage } from '../features/Destination';
import { ExplorePage } from '../features/Explore';
import { Landing } from '../features/Landing';
import { SearchPage } from '../features/Search';
import { SystemStatusPage } from '../features/SystemStatus';
import { Discovery } from '../features/Workspace';
import { DemoBadge, Notice } from '../components/ui';
import { TravelProvider } from './TravelContext';

function Layout() {
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const lastPath = useRef(pathname);
  const aiActive = ['/discover', '/compare', '/explore'].some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
  const searchActive =
    pathname === '/search' || pathname.startsWith('/destinations/');
  useLayoutEffect(() => {
    if (lastPath.current !== pathname)
      main.current?.focus({ preventScroll: true });
    lastPath.current = pathname;
  }, [pathname]);

  return (
    <TravelProvider>
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <header className="site-header">
        <div className="nav-wrap">
          <Link to="/" className="brand" aria-label="Wohin home">
            <Compass size={21} />
            Wohin<span>.</span>
          </Link>
          <nav aria-label="Main navigation">
            <Link
              to="/search"
              aria-current={searchActive ? 'location' : undefined}
              className={searchActive ? 'nav-link current' : 'nav-link'}
            >
              <Search size={15} /> Travel search
            </Link>
            <Link
              to="/discover"
              aria-current={aiActive ? 'location' : undefined}
              className={aiActive ? 'nav-link current' : 'nav-link'}
            >
              <Sparkles size={15} /> Ask AI
            </Link>
          </nav>
          <div className="nav-meta">
            <DemoBadge />
            <span>EUR · EN</span>
          </div>
        </div>
      </header>
      <main id="main-content" tabIndex={-1} ref={main}>
        <Outlet />
      </main>
      {!aiActive && (
        <footer className="site-footer">
          <div className="page">
            <Link className="brand" to="/" aria-label="Wohin home">
              Wohin<span>.</span>
            </Link>
            <p>A travel-planning prototype · Project VS, TU Berlin</p>
            <span>
              Sample journeys and estimates ·{' '}
              <Link to="/status">System status</Link>
            </span>
          </div>
        </footer>
      )}
      <ScrollRestoration getKey={(location) => location.pathname} />
    </TravelProvider>
  );
}

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { index: true, element: <Landing /> },
      { path: 'discover', element: <Discovery /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'destinations/:destinationId', element: <DestinationPage /> },
      { path: 'compare', element: <ComparePage /> },
      { path: 'explore/:opportunityId', element: <ExplorePage /> },
      { path: 'status', element: <SystemStatusPage /> },
      {
        path: '*',
        element: (
          <div className="page">
            <Notice
              title="We couldn’t find that page"
              action={
                <Link className="button button-primary" to="/">
                  Go to Wohin home
                </Link>
              }
            >
              Try Travel search or Ask AI from the navigation.
            </Notice>
          </div>
        ),
      },
    ],
  },
]);
