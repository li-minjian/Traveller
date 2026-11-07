import { ArrowLeft, Compass, MapPin } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { budgetLabel, datesLabel } from '../domain/travel';
import type { Cost, TravelOpportunity } from '../domain/travel';

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="eyebrow">{children}</p>;
}

export function DemoBadge({ partial = false }: { partial?: boolean }) {
  return (
    <span className={`badge ${partial ? 'badge-warning' : ''}`}>
      {partial ? 'Provisional · Demo' : 'Demo data'}
    </span>
  );
}

export function BackLink({
  to,
  children,
  state,
}: {
  to: string;
  children: ReactNode;
  state?: { from: string };
}) {
  return (
    <Link to={to} state={state} className="back-link">
      <ArrowLeft size={16} />
      {children}
    </Link>
  );
}

export function Notice({
  title,
  children,
  action,
  error = false,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  error?: boolean;
}) {
  return (
    <section
      className={`notice ${error ? 'notice-error' : ''}`}
      role={error ? 'alert' : 'status'}
    >
      <div className="notice-icon">
        <Compass size={22} />
      </div>
      <h2>{title}</h2>
      <div className="notice-copy">{children}</div>
      {action}
    </section>
  );
}

export function Loading({
  stale = false,
  title = 'Curating travel opportunities…',
}: {
  stale?: boolean;
  title?: string;
}) {
  return (
    <div className="loading-state" role="status">
      <div className="notice-icon">
        <Compass size={23} />
      </div>
      <h2>{stale ? 'Refreshing your journeys…' : title}</h2>
      <p>
        {stale
          ? 'Earlier results are out of date while we check the latest criteria.'
          : 'Checking the sample catalogue against your travel criteria.'}
      </p>
      <div className="skeletons" aria-hidden="true">
        {[1, 2, 3].map((id) => (
          <div key={id}>
            <span />
            <span />
            <span />
          </div>
        ))}
      </div>
    </div>
  );
}

export function JourneyImage({
  opportunity,
  variant = 'card',
}: {
  opportunity: TravelOpportunity;
  variant?: 'card' | 'compare' | 'report';
}) {
  const { destination } = opportunity;
  const image =
    (variant === 'report'
      ? destination.reportImage
      : variant === 'compare'
        ? destination.compareImage
        : undefined) ?? destination.image;
  return (
    <div
      className={`journey-image journey-image-${variant} ${image ? '' : 'image-placeholder'}`}
    >
      {image ? (
        <img src={image} alt="" />
      ) : (
        <MapPin className="image-emblem" aria-hidden="true" />
      )}
      <div className="journey-image-top">
        <DemoBadge partial={opportunity.completeness === 'provisional'} />
      </div>
      <div className="journey-image-caption">
        <div>
          <Eyebrow>{destination.region}</Eyebrow>
          {variant === 'report' ? (
            <h1>{destination.name}</h1>
          ) : (
            <h3>{destination.name}</h3>
          )}
          {variant === 'report' && (
            <p>
              {opportunity.title} · {datesLabel(opportunity.dates)}
            </p>
          )}
        </div>
        {variant !== 'report' && (
          <div className="image-price">
            <span>
              {opportunity.total === null ? 'Trip total' : 'Est. trip total'}
            </span>
            <strong>{budgetLabel(opportunity.total)}</strong>
          </div>
        )}
      </div>
    </div>
  );
}

export function CostBreakdown({
  costs,
  total,
}: {
  costs: Cost[];
  total: number | null;
}) {
  return (
    <div className="cost-breakdown">
      {total !== null && total > 0 && (
        <div className="cost-bar" aria-hidden="true">
          {costs.map((cost) => (
            <span key={cost.label} style={{ flexGrow: cost.amount ?? 0 }} />
          ))}
        </div>
      )}
      <dl>
        {costs.map((cost) => (
          <div key={cost.label}>
            <dt>{cost.label}</dt>
            <dd>{budgetLabel(cost.amount)}</dd>
          </div>
        ))}
        <div className="cost-total">
          <dt>Estimated group total</dt>
          <dd>{budgetLabel(total)}</dd>
        </div>
      </dl>
    </div>
  );
}
