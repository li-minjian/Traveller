import {
  ArrowRight,
  CircleAlert,
  CircleCheck,
  GitCompareArrows,
  Map as MapIcon,
  X,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useLocation } from 'react-router';
import type { JourneyMode, JourneySort } from '../app/session';
import { useTravel } from '../app/TravelContext';
import { datesLabel } from '../domain/travel';
import type { TravelOpportunity } from '../domain/travel';
import { PlaceMap } from './PlaceMap';
import { DemoBadge, Eyebrow, JourneyImage, Loading, Notice } from './ui';

export function JourneyCard({
  opportunity,
  mode = 'ai',
}: {
  opportunity: TravelOpportunity;
  mode?: 'ai' | 'search';
}) {
  const { session, dispatch } = useTravel();
  const location = useLocation();
  const selected = session.selected.includes(opportunity.id);
  const { destination, transport, stay } = opportunity;
  return (
    <article
      className={`journey-card ${selected ? 'journey-selected' : ''}`}
      id={`journey-${opportunity.id}`}
    >
      <JourneyImage opportunity={opportunity} />
      <div className="journey-card-content">
        <h4>{opportunity.title}</h4>
        <div className="chip-row">
          {destination.tags.slice(0, 3).map((tag) => (
            <span className="tag" key={tag}>
              {tag}
            </span>
          ))}
        </div>
        <dl className="fact-grid">
          <div>
            <dt>Duration</dt>
            <dd>
              {opportunity.days} {opportunity.days === 1 ? 'day' : 'days'}
            </dd>
          </div>
          <div>
            <dt>Transport</dt>
            <dd>{transport.label}</dd>
          </div>
          <div>
            <dt>Stay</dt>
            <dd>{stay.kind}</dd>
          </div>
          <div>
            <dt>From {transport.origin}</dt>
            <dd>
              {transport.hours ?? 'Unknown'}
              {transport.hours !== null && ' h one way'}
            </dd>
          </div>
        </dl>
        <div className="insight">
          <strong>
            <CircleCheck size={15} /> Why this fits
          </strong>
          <p>{opportunity.reasons[0]}</p>
        </div>
        <div className="insight tradeoff">
          <strong>
            <CircleAlert size={15} /> Things to consider
          </strong>
          <p>{opportunity.considerations[0]}</p>
        </div>
        <div className="card-actions">
          <button
            type="button"
            className="button button-outline select-button"
            aria-pressed={selected}
            aria-label={`Compare ${opportunity.title}`}
            onClick={() => dispatch({ type: 'toggle', id: opportunity.id })}
          >
            {selected ? (
              <CircleCheck size={16} />
            ) : (
              <GitCompareArrows size={16} />
            )}
            {selected ? 'Selected' : 'Compare'}
          </button>
          <Link
            className="button button-primary"
            to={
              mode === 'ai'
                ? `/explore/${opportunity.id}`
                : `/destinations/${destination.id}`
            }
            state={{ from: location.pathname, opportunityId: opportunity.id }}
            aria-label={`${mode === 'ai' ? 'Explore' : 'View destination for'} ${opportunity.title}`}
          >
            {mode === 'ai' ? 'Explore' : 'Destination'}
            <ArrowRight size={15} />
          </Link>
        </div>
      </div>
    </article>
  );
}

export function CompareBar({
  opportunities,
}: {
  opportunities: TravelOpportunity[];
}) {
  const {
    session: { selected },
    dispatch,
  } = useTravel();
  const location = useLocation();
  const current = selected.filter((id) =>
    opportunities.some((item) => item.id === id),
  );
  if (!selected.length) return null;
  const names = current
    .map((id) => opportunities.find((item) => item.id === id)?.destination.name)
    .join(' · ');
  const unavailable = selected.length - current.length;
  return (
    <aside className="compare-bar" aria-label="Comparison selection">
      <div className="compare-count">{current.length}</div>
      <div className="compare-selection">
        <strong>{current.length} selected for comparison</strong>
        <small>
          {unavailable ? `${unavailable} outside current results` : names}
        </small>
      </div>
      <button
        className="compare-clear"
        type="button"
        onClick={() => dispatch({ type: 'clear' })}
        aria-label="Clear comparison selection"
      >
        <X size={17} />
        <span>Clear</span>
      </button>
      {current.length >= 2 ? (
        <Link
          to="/compare"
          className="button button-light"
          state={{ from: location.pathname }}
        >
          Compare ({current.length}) <GitCompareArrows size={16} />
        </Link>
      ) : (
        <span className="compare-hint">Select at least 2</span>
      )}
    </aside>
  );
}

export function Results({
  mode,
  onEdit,
  mapOpen = false,
}: {
  mode: JourneyMode;
  onEdit: () => void;
  mapOpen?: boolean;
}) {
  const { session, dispatch } = useTravel();
  const { revision, result, error } = session;
  const sort = session.sort[mode];
  const [activeMapId, setActiveMapId] = useState('');
  const ai = mode === 'ai';
  if (error?.revision === revision)
    return (
      <Notice
        title="We couldn’t load journeys"
        error
        action={
          <button
            className="button button-primary"
            onClick={() => dispatch({ type: 'retry' })}
          >
            Retry search
          </button>
        }
      >
        {error.message}
      </Notice>
    );
  if (!result || result.revision !== revision)
    return <Loading stale={Boolean(result)} />;
  const { opportunities, conflicts } = result;
  if (!opportunities.length)
    return (
      <Notice
        title="No journeys fit these criteria"
        action={
          <button className="button button-primary" onClick={onEdit}>
            Review criteria
          </button>
        }
      >
        <p>
          {conflicts.length
            ? conflicts.join(' ')
            : 'There are no examples for this combination in the sample catalogue.'}
        </p>
        <p>
          Try a different destination or loosen a requirement you’re comfortable
          changing.
        </p>
      </Notice>
    );

  const partial = opportunities.some(
    (item) => item.completeness === 'provisional',
  );
  const ordered = [...opportunities];
  if (sort === 'price')
    ordered.sort(
      (first, second) => (first.total ?? Infinity) - (second.total ?? Infinity),
    );
  if (sort === 'time')
    ordered.sort(
      (first, second) =>
        (first.transport.hours ?? Infinity) -
        (second.transport.hours ?? Infinity),
    );
  const places = Array.from(
    new Map(
      ordered.map((item) => [item.destination.id, item.destination]),
    ).values(),
  );
  const activeJourney =
    ordered.find(
      (item) =>
        item.destination.id === activeMapId && item.destination.coordinates,
    ) ?? ordered.find((item) => item.destination.coordinates);

  return (
    <>
      <div className="section-heading results-heading">
        <div>
          <Eyebrow>{ai ? 'Curated itineraries' : 'Destination search'}</Eyebrow>
          {ai ? <h1>Journeys to consider</h1> : <h2>Journeys that fit</h2>}
          <p>
            {ai
              ? 'Compare different ways to travel, then take a closer look at the journey that speaks to you.'
              : 'Browse places, compare sample trip estimates and see what you can do when you arrive.'}
          </p>
        </div>
        <span className="result-count" role="status">
          <i />
          {opportunities.length}{' '}
          {opportunities.length === 1 ? 'journey' : 'journeys'} found
        </span>
      </div>
      <div className="result-toolbar">
        <DemoBadge partial={partial} />
        <span>
          {partial
            ? 'Some estimates are incomplete.'
            : 'Estimates for your group.'}
        </span>
        <label>
          Sort by{' '}
          <select
            aria-label="Sort journeys"
            value={sort}
            onChange={(event) =>
              dispatch({
                type: 'sort',
                mode,
                sort: event.target.value as JourneySort,
              })
            }
          >
            <option value="fit">Preference fit</option>
            <option value="price">Lowest estimate</option>
            <option value="time">Shortest travel time</option>
          </select>
        </label>
      </div>
      {mapOpen && (
        <section className="section-card result-map">
          <Eyebrow>
            <MapIcon size={14} /> Journey locations
          </Eyebrow>
          <PlaceMap
            places={places}
            activeId={activeJourney?.destination.id}
            onSelect={setActiveMapId}
          />
          {activeJourney && (
            <a className="text-link" href={`#journey-${activeJourney.id}`}>
              See {activeJourney.destination.name} in results{' '}
              <ArrowRight size={14} />
            </a>
          )}
        </section>
      )}
      <div className="journey-grid">
        {ordered.map((opportunity) => (
          <JourneyCard
            key={opportunity.id}
            opportunity={opportunity}
            mode={mode}
          />
        ))}
      </div>
      <CompareBar opportunities={opportunities} />
    </>
  );
}

export function JourneySummary({
  opportunity,
}: {
  opportunity: TravelOpportunity;
}) {
  return (
    <dl className="summary-strip">
      <div>
        <dt>Trip length</dt>
        <dd>{opportunity.days} days</dd>
      </div>
      <div>
        <dt>Dates</dt>
        <dd>{datesLabel(opportunity.dates)}</dd>
      </div>
      <div>
        <dt>Transit</dt>
        <dd>
          {opportunity.transport.hours === null
            ? 'Unknown'
            : `${opportunity.transport.hours} h one way`}
        </dd>
      </div>
      <div>
        <dt>Time on location</dt>
        <dd>
          {opportunity.timeOnLocation === null
            ? 'Unknown'
            : `~${Math.round(opportunity.timeOnLocation)} h`}
        </dd>
      </div>
    </dl>
  );
}
