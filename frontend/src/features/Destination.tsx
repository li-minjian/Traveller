import {
  ArrowRight,
  BedDouble,
  Compass,
  MapPin,
  Sparkles,
  TrainFront,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router';
import { useTravel } from '../app/TravelContext';
import { CriteriaBar, CriteriaDialog } from '../components/Criteria';
import { PlaceMap } from '../components/PlaceMap';
import {
  BackLink,
  DemoBadge,
  Eyebrow,
  Loading,
  Notice,
} from '../components/ui';
import { budgetLabel, field } from '../domain/travel';
import type { SearchResult } from '../domain/travel';

export function DestinationPage() {
  const { destinationId } = useParams();
  const {
    session: { intent, revision },
    service,
    submit,
  } = useTravel();
  const navigate = useNavigate();
  const location = useLocation();
  const place = service
    .destinations()
    .find((item) => item.id === destinationId);
  const [result, setResult] = useState<SearchResult & { placeId: string }>();
  const [failed, setFailed] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [editing, setEditing] = useState(false);
  const requestKey = `${destinationId}:${revision}:${attempt}`;

  useEffect(() => {
    if (!place) return;
    const controller = new AbortController();
    service
      .search({
        intent: { ...intent, destination: field(place.name) },
        revision,
        signal: controller.signal,
      })
      .then(
        (response) => {
          if (!controller.signal.aborted)
            setResult({ ...response, placeId: place.id });
        },
        () => {
          if (!controller.signal.aborted) setFailed(requestKey);
        },
      );
    return () => controller.abort();
  }, [intent, place, requestKey, revision, service]);

  if (!place)
    return (
      <div className="page">
        <Notice
          title="Destination unavailable"
          action={<BackLink to="/search">Travel search</BackLink>}
        >
          This destination isn’t in the demo catalogue.
        </Notice>
      </div>
    );
  const matching =
    result?.revision === revision && result.placeId === place.id
      ? result
      : null;
  const opportunityId =
    typeof location.state?.opportunityId === 'string'
      ? location.state.opportunityId
      : '';
  const opportunities = matching
    ? [...matching.opportunities].sort(
        (first, second) =>
          Number(second.id === opportunityId) -
          Number(first.id === opportunityId),
      )
    : [];
  const image = place.editorialImage ?? place.image;
  const from = location.state?.from === '/discover' ? '/discover' : '/search';

  return (
    <div className="page detail-page">
      <div className="detail-nav">
        <BackLink to={from}>
          {from === '/discover'
            ? 'Back to discoveries'
            : 'Back to travel search'}
        </BackLink>
        <DemoBadge />
      </div>
      <section
        className={`destination-hero ${image ? '' : 'image-placeholder'}`}
      >
        {image ? (
          <img src={image} alt="" />
        ) : (
          <MapPin className="image-emblem" aria-hidden="true" />
        )}
        <div>
          <Eyebrow>{place.region}</Eyebrow>
          <h1>{place.name}</h1>
          <p>{place.description}</p>
        </div>
      </section>
      <div className="destination-actions">
        <div className="chip-row">
          {place.tags.map((tag) => (
            <span className="tag" key={tag}>
              {tag}
            </span>
          ))}
        </div>
        <button
          type="button"
          className="button button-primary"
          onClick={() => {
            submit(`Tell me about ${place.name}`, {
              destination: field(place.name),
            });
            navigate('/discover', { state: { from: location.pathname } });
          }}
        >
          <Sparkles size={17} /> Ask AI about this destination{' '}
          <ArrowRight size={16} />
        </button>
      </div>
      <CriteriaBar onEdit={() => setEditing(true)} />
      <p className="context-note">
        This guide uses your shared criteria with {place.name} as the
        destination.
      </p>
      {failed === requestKey ? (
        <Notice
          title="We couldn’t load travel options"
          error
          action={
            <button
              className="button button-primary"
              onClick={() => setAttempt((value) => value + 1)}
            >
              Retry search
            </button>
          }
        >
          The sample service did not respond.
        </Notice>
      ) : !matching ? (
        <Loading
          stale={Boolean(result)}
          title="Checking connections and stays…"
        />
      ) : opportunities.length ? (
        <div className="detail-grid">
          <section className="section-card">
            <Eyebrow>
              <TrainFront size={15} /> Getting there
            </Eyebrow>
            <h2>Connections to consider</h2>
            <ul className="detail-list">
              {opportunities.map((item) => (
                <li key={item.id}>
                  <strong>
                    {item.transport.label} from {item.transport.origin}
                  </strong>
                  <p>
                    {item.transport.hours ?? 'Unknown'}
                    {item.transport.hours !== null && ' h one way'} ·{' '}
                    {budgetLabel(item.transport.estimate)} group transport
                    estimate
                  </p>
                </li>
              ))}
            </ul>
          </section>
          <section className="section-card">
            <Eyebrow>
              <BedDouble size={15} /> Accommodation
            </Eyebrow>
            <h2>Places to stay</h2>
            <ul className="detail-list">
              {opportunities.map((item) => (
                <li key={item.id}>
                  <strong>{item.stay.name}</strong>
                  <p>
                    {item.stay.detail}{' '}
                    {item.stay.nightly !== null &&
                      `Est. ${budgetLabel(item.stay.nightly)} / room / night.`}
                  </p>
                  {(!intent.destination.value ||
                    intent.destination.value === place.name) && (
                    <Link
                      className="text-link"
                      to={`/explore/${item.id}`}
                      state={{ from: location.pathname }}
                    >
                      Explore trip <ArrowRight size={15} />
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : (
        <Notice
          title="No sample connections fit"
          action={
            <button
              className="button button-primary"
              onClick={() => setEditing(true)}
            >
              Review criteria
            </button>
          }
        >
          {matching.conflicts.join(' ') ||
            'Adjust the criteria to see more sample connections.'}
        </Notice>
      )}
      <section className="section-card activities">
        <Eyebrow>
          <Compass size={15} /> On location
        </Eyebrow>
        <h2>Places and activities</h2>
        <div className="detail-grid">
          {place.activities.map((activity) => (
            <div key={activity.id}>
              <h3>{activity.name}</h3>
              <p>{activity.description}</p>
            </div>
          ))}
        </div>
        <PlaceMap key={place.id} places={[place, ...place.activities]} />
      </section>
      <CriteriaDialog open={editing} onClose={() => setEditing(false)} />
    </div>
  );
}
