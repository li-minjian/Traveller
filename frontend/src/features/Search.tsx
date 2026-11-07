import {
  ArrowRight,
  Map as MapIcon,
  Search as SearchIcon,
  Sparkles,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { useTravel } from '../app/TravelContext';
import {
  CriteriaBar,
  CriteriaDialog,
  CriteriaForm,
} from '../components/Criteria';
import { Results } from '../components/Journeys';
import { Eyebrow } from '../components/ui';

export function SearchPage() {
  const { session, dispatch } = useTravel();
  const [editing, setEditing] = useState(!session.active);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);

  useEffect(() => {
    dispatch({ type: 'activate' });
  }, [dispatch]);

  return (
    <div className="page search-page">
      <section className="search-intro">
        <div>
          <Eyebrow>
            <SearchIcon size={14} /> Travel search / 02
          </Eyebrow>
          <h1>Find your next journey.</h1>
          <p>
            Pick a destination or leave it open. Shape your trip around the
            dates, budget and connections that work for you.
          </p>
        </div>
        <Link to="/discover" className="button button-outline">
          <Sparkles size={17} /> Ask AI <ArrowRight size={16} />
        </Link>
      </section>
      <section
        className="section-card search-filters"
        aria-labelledby="search-filters-heading"
      >
        <div className="filter-heading">
          <div>
            <Eyebrow>Plan the essentials</Eyebrow>
            <h2 id="search-filters-heading">Travel criteria</h2>
          </div>
          <button
            className="button button-outline"
            type="button"
            aria-expanded={editing}
            aria-controls="search-form"
            onClick={() => setEditing((value) => !value)}
          >
            {editing ? 'Hide search form' : 'Open search form'}
          </button>
        </div>
        <div id="search-form" hidden={!editing}>
          {editing && (
            <CriteriaForm
              label="Search journeys"
              onApply={(changes) => {
                if (Object.keys(changes).length)
                  dispatch({ type: 'update', changes });
                setEditing(false);
                requestAnimationFrame(() => {
                  const section = document.getElementById('search-results');
                  section?.focus({ preventScroll: true });
                  section?.scrollIntoView({ block: 'start' });
                });
              }}
            />
          )}
        </div>
        {!editing && (
          <CriteriaBar onEdit={() => setDialogOpen(true)}>
            {session.result?.revision === session.revision &&
              Boolean(session.result.opportunities.length) && (
                <button
                  type="button"
                  className="chip"
                  aria-pressed={mapOpen}
                  onClick={() => setMapOpen(!mapOpen)}
                >
                  <MapIcon size={15} />
                  {mapOpen ? 'Hide map' : 'View map'}
                </button>
              )}
          </CriteriaBar>
        )}
      </section>
      <section
        id="search-results"
        tabIndex={-1}
        aria-label="Travel search results"
      >
        <Results
          mode="search"
          onEdit={() => setDialogOpen(true)}
          mapOpen={mapOpen}
        />
      </section>
      <CriteriaDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </div>
  );
}
