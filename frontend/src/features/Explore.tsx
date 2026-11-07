import {
  ArrowRight,
  BedDouble,
  CircleAlert,
  Compass,
  MapPin,
  TrainFront,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router';
import { useTravel } from '../app/TravelContext';
import { CriteriaBar, CriteriaDialog } from '../components/Criteria';
import { JourneySummary } from '../components/Journeys';
import { PlaceMap } from '../components/PlaceMap';
import {
  BackLink,
  CostBreakdown,
  DemoBadge,
  Eyebrow,
  JourneyImage,
  Loading,
  Notice,
} from '../components/ui';
import { budgetLabel } from '../domain/travel';
import type { ExploreReport } from '../domain/travel';
import { Workspace } from './Workspace';

function Report({ report }: { report: ExploreReport }) {
  const { session } = useTravel();
  const { opportunity, itinerary, transportOptions } = report;
  const { destination, stay } = opportunity;
  const business = session.intent.business.value;
  return (
    <>
      <JourneyImage opportunity={opportunity} variant="report" />
      <JourneySummary opportunity={opportunity} />
      <section className="section-card report-section">
        <Eyebrow>Why this journey</Eyebrow>
        <h2>How it fits your intent</h2>
        <p>{destination.description}</p>
        <div className="report-facts">
          {opportunity.reasons.map((reason) => (
            <p className="insight" key={reason}>
              <Compass size={16} />
              {reason}
            </p>
          ))}
        </div>
      </section>
      <section className="report-section">
        <Eyebrow>Itinerary flow · Example</Eyebrow>
        <h2>A {opportunity.days}-day outline</h2>
        {business && (
          <div className="insight business-report">
            <strong>Work trip · {business.purpose}</strong>
            <p>
              {business.meetingDate || 'Meeting date flexible'}
              {business.meetingTime && ` at ${business.meetingTime} local time`}
              .
              {business.privateNights > 0 &&
                ` Includes ${business.privateNights} private extension night(s) in the group estimate.`}
            </p>
          </div>
        )}
        <div className="itinerary-grid">
          {itinerary.map((stop) => (
            <article key={stop.title} className="section-card">
              <Eyebrow>{stop.label}</Eyebrow>
              <h3>{stop.title}</h3>
              <p>{stop.description}</p>
            </article>
          ))}
        </div>
      </section>
      <div className="detail-grid report-section">
        <section className="section-card accommodation">
          <Eyebrow>
            <BedDouble size={15} /> Accommodation
          </Eyebrow>
          <h2>{stay.name}</h2>
          {stay.image && <img src={stay.image} alt="" loading="lazy" />}
          <p>{stay.detail}</p>
          <strong>
            {stay.nightly === null
              ? 'Nightly cost unknown'
              : `Est. ${budgetLabel(stay.nightly)} / room / night`}
          </strong>
        </section>
        <section className="section-card">
          <Eyebrow>
            <TrainFront size={15} /> Getting there
          </Eyebrow>
          <h2>Sample connections</h2>
          <ul className="detail-list">
            {transportOptions.map((transport, index) => (
              <li key={index}>
                <strong>
                  {transport.label} from {transport.origin}
                </strong>
                <p>
                  {transport.hours ?? 'Unknown'}
                  {transport.hours !== null && ' h one way'} · Est.{' '}
                  {budgetLabel(transport.estimate)} for the group
                </p>
              </li>
            ))}
          </ul>
        </section>
      </div>
      <section className="report-section">
        <Eyebrow>
          <MapPin size={15} /> Geographic context
        </Eyebrow>
        <h2>Key stops along the way</h2>
        <PlaceMap
          places={destination.activities.filter((place) =>
            itinerary.some((stop) => stop.placeId === place.id),
          )}
          connect
        />
      </section>
      <div className="detail-grid report-section">
        <section className="section-card">
          <Eyebrow>Budget transparency</Eyebrow>
          <h2>Estimated costs</h2>
          <CostBreakdown costs={opportunity.costs} total={opportunity.total} />
          <p className="context-note">
            {opportunity.evidence.label} · estimates for the whole group.
          </p>
        </section>
        <section className="section-card">
          <Eyebrow>
            <CircleAlert size={15} /> Trade-offs & advice
          </Eyebrow>
          <h2>Things to consider</h2>
          <ul className="detail-list">
            {opportunity.considerations.map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ul>
          {opportunity.signals.length > 0 && (
            <div className="compare-block">
              <Eyebrow>Example constraint checks</Eyebrow>
              <ul>
                {opportunity.signals.map((signal) => (
                  <li key={signal.label}>
                    <strong>
                      {signal.label} · {signal.outcome}
                    </strong>{' '}
                    {signal.detail}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      </div>
      <section className="report-cta">
        <div>
          <Eyebrow>Explore another way</Eyebrow>
          <h2>Get to know {destination.name}.</h2>
          <p>
            See the destination guide for transport, stays and places to visit.
          </p>
        </div>
        <Link
          className="button button-light"
          to={`/destinations/${destination.id}`}
          state={{ from: '/discover', opportunityId: opportunity.id }}
        >
          Open destination guide <ArrowRight size={16} />
        </Link>
      </section>
    </>
  );
}

export function ExplorePage() {
  const { opportunityId } = useParams();
  const {
    session: { intent, revision },
    service,
  } = useTravel();
  const navigate = useNavigate();
  const location = useLocation();
  const [answer, setAnswer] = useState<{
    key: string;
    report: ExploreReport | null;
  }>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [editing, setEditing] = useState(false);
  const key = `${opportunityId}:${revision}:${attempt}`;

  useEffect(() => {
    if (!opportunityId) return;
    const controller = new AbortController();
    service
      .explore({ intent, revision, signal: controller.signal }, opportunityId)
      .then(
        (response) => {
          if (!controller.signal.aborted && response.revision === revision)
            setAnswer({ key, report: response.report });
        },
        () => {
          if (!controller.signal.aborted) setError(key);
        },
      );
    return () => controller.abort();
  }, [intent, key, opportunityId, revision, service]);

  const from = location.state?.from;
  const back =
    from === '/compare' ||
    (typeof from === 'string' && /^\/destinations\/[a-z-]+$/.test(from))
      ? from
      : '/discover';
  const backText =
    back === '/compare'
      ? 'Back to comparison'
      : back === '/discover'
        ? 'Back to discoveries'
        : 'Back to destination';
  return (
    <Workspace onRefine={() => navigate('/discover')}>
      <div className="workspace-canvas report-canvas">
        <div className="detail-nav">
          <div>
            <BackLink
              to={back}
              state={
                back === '/compare' &&
                location.state?.compareSource === '/search'
                  ? { from: '/search' }
                  : undefined
              }
            >
              {backText}
            </BackLink>
            {back === '/compare' && (
              <BackLink to="/discover">Back to discoveries</BackLink>
            )}
          </div>
          <DemoBadge />
        </div>
        <CriteriaBar onEdit={() => setEditing(true)} />
        {error === key ? (
          <Notice
            title="We couldn’t load this journey"
            error
            action={
              <button
                type="button"
                className="button button-primary"
                onClick={() => setAttempt((value) => value + 1)}
              >
                Retry report
              </button>
            }
          >
            The sample report service did not respond.
          </Notice>
        ) : answer?.key !== key ? (
          <Loading
            title="Preparing your journey report…"
            stale={Boolean(answer)}
          />
        ) : answer.report ? (
          <Report key={answer.report.opportunity.id} report={answer.report} />
        ) : (
          <Notice
            title="This journey is unavailable"
            action={
              <Link className="button button-primary" to="/discover">
                See current journeys <ArrowRight size={16} />
              </Link>
            }
          >
            The journey may be outside the sample catalogue or no longer fit
            your criteria.
          </Notice>
        )}
      </div>
      <CriteriaDialog open={editing} onClose={() => setEditing(false)} />
    </Workspace>
  );
}
