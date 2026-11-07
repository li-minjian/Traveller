import {
  ArrowRight,
  BedDouble,
  CircleAlert,
  CircleCheck,
  GitCompareArrows,
  TrainFront,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { useTravel } from '../app/TravelContext';
import { CriteriaBar, CriteriaDialog } from '../components/Criteria';
import { budgetLabel, datesLabel } from '../domain/travel';
import type { TravelOpportunity } from '../domain/travel';
import {
  BackLink,
  CostBreakdown,
  DemoBadge,
  Eyebrow,
  JourneyImage,
  Loading,
  Notice,
} from '../components/ui';
import { Workspace } from './Workspace';

const factors: { title: string; value: (item: TravelOpportunity) => string }[] =
  [
    {
      title: 'Estimated group total',
      value: (item) => budgetLabel(item.total),
    },
    { title: 'Dates', value: (item) => datesLabel(item.dates) },
    {
      title: 'Travel time, one way',
      value: (item) =>
        item.transport.hours === null ? 'Unknown' : `${item.transport.hours} h`,
    },
    {
      title: 'Connections',
      value: (item) =>
        item.transport.changes === null
          ? 'Unknown'
          : item.transport.changes === 0
            ? 'Direct'
            : `${item.transport.changes} change(s)`,
    },
    {
      title: 'Time on location',
      value: (item) =>
        item.timeOnLocation === null
          ? 'Unknown'
          : `About ${Math.round(item.timeOnLocation)} h`,
    },
    {
      title: 'Data completeness',
      value: (item) =>
        item.completeness === 'provisional'
          ? 'Provisional'
          : 'Cost components supplied',
    },
  ];

function CompareCard({
  item,
  source,
}: {
  item: TravelOpportunity;
  source: '/discover' | '/search';
}) {
  const { dispatch } = useTravel();
  return (
    <article className="comparison-card section-card">
      <JourneyImage opportunity={item} variant="compare" />
      <div className="compare-card-head">
        <h3>{item.title}</h3>
        <button
          className="text-button"
          type="button"
          onClick={() => dispatch({ type: 'toggle', id: item.id })}
          aria-label={`Remove ${item.title} from comparison`}
        >
          Remove
        </button>
      </div>
      <div className="compare-block">
        <Eyebrow>Indicative budget</Eyebrow>
        <CostBreakdown costs={item.costs} total={item.total} />
      </div>
      <div className="compare-block">
        <Eyebrow>
          <TrainFront size={14} /> Transit complexity
        </Eyebrow>
        <strong>{item.transport.label}</strong>
        <p>
          From {item.transport.origin} · {factors[2].value(item)} ·{' '}
          {factors[3].value(item)}
        </p>
      </div>
      <div className="compare-block">
        <Eyebrow>
          <BedDouble size={14} /> Accommodation
        </Eyebrow>
        <strong>{item.stay.name}</strong>
        <p>{item.stay.detail}</p>
      </div>
      <div className="compare-block">
        <Eyebrow>
          <CircleCheck size={14} /> Key advantages
        </Eyebrow>
        <ul>
          {item.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>
      <div className="compare-block tradeoff">
        <Eyebrow>
          <CircleAlert size={14} /> Trade-offs
        </Eyebrow>
        <ul>
          {item.considerations.map((detail) => (
            <li key={detail}>{detail}</li>
          ))}
        </ul>
      </div>
      {item.signals.length > 0 && (
        <div className="compare-block">
          <Eyebrow>Example constraint checks</Eyebrow>
          <ul>
            {item.signals.map((signal) => (
              <li key={signal.label}>
                <strong>
                  {signal.label} · {signal.outcome} ·{' '}
                  {signal.hard ? 'Required' : 'Preferred'}
                </strong>{' '}
                {signal.detail}
              </li>
            ))}
          </ul>
        </div>
      )}
      <Link
        to={`/explore/${item.id}`}
        state={{ from: '/compare', compareSource: source }}
        className="button button-primary"
        aria-label={`Explore ${item.title}`}
      >
        Explore full journey <ArrowRight size={16} />
      </Link>
    </article>
  );
}

export function ComparePage() {
  const { session, dispatch } = useTravel();
  const navigate = useNavigate();
  const location = useLocation();
  const [editing, setEditing] = useState(false);
  const { result, selected, revision, error } = session;
  const items =
    result?.revision === revision
      ? selected.flatMap((id) =>
          result.opportunities.filter((item) => item.id === id),
        )
      : [];
  const back = location.state?.from === '/search' ? '/search' : '/discover';

  return (
    <Workspace onRefine={() => navigate('/discover')}>
      <div className="workspace-canvas report-canvas">
        <div className="detail-nav">
          <BackLink to={back}>
            {back === '/search'
              ? 'Back to travel search'
              : 'Back to discoveries'}
          </BackLink>
          <DemoBadge />
        </div>
        <div className="section-heading report-heading">
          <div>
            <Eyebrow>
              <GitCompareArrows size={15} /> Journey comparison
            </Eyebrow>
            <h1>See the differences.</h1>
            <p>
              Put costs, transit and trade-offs side by side before choosing
              where to go.
            </p>
          </div>
        </div>
        <CriteriaBar onEdit={() => setEditing(true)} />
        {error?.revision === revision ? (
          <Notice
            title="We couldn’t refresh your comparison"
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
        ) : session.active && result?.revision !== revision ? (
          <Loading stale={Boolean(result)} />
        ) : items.length < 2 ? (
          <Notice
            title="Select at least two journeys"
            action={
              <Link className="button button-primary" to={back}>
                Find journeys <ArrowRight size={16} />
              </Link>
            }
          >
            {selected.length >= 2
              ? 'Some selections are outside your current criteria. They’ll reappear if they fit a later search.'
              : 'Use Compare on the result cards to choose journeys.'}
          </Notice>
        ) : (
          <>
            {selected.length > items.length && (
              <p className="context-note" role="status">
                Some selections are outside your current criteria.
              </p>
            )}
            <div className="comparison-grid">
              {items.map((item) => (
                <CompareCard key={item.id} item={item} source={back} />
              ))}
            </div>
            <section className="section-card matrix">
              <Eyebrow>Factor by factor</Eyebrow>
              <h2>Comparison matrix</h2>
              <div
                className="table-scroll"
                tabIndex={0}
                role="region"
                aria-label="Scrollable comparison matrix"
              >
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Factor</th>
                      {items.map((item) => (
                        <th key={item.id} scope="col">
                          {item.title}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {factors.map((factor) => (
                      <tr key={factor.title}>
                        <th scope="row">{factor.title}</th>
                        {items.map((item) => (
                          <td key={item.id}>{factor.value(item)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
      <CriteriaDialog open={editing} onClose={() => setEditing(false)} />
    </Workspace>
  );
}
