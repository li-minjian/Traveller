import { TriangleAlert } from 'lucide-react';
import type {
  FlightPart,
  Journey,
  JourneyReview,
  SearchResult,
} from '../../api/client';
import {
  formatDuration,
  formatMoney,
  formatStops,
  localDate,
  localTime,
} from './format';

/** Journey cards below an assistant message that carries a search result. */
export function Results({ result }: { result: SearchResult }) {
  const closest =
    result.status === 'no_results' ? result.no_results?.closest_journey : null;

  return (
    <>
      {result.journeys.length > 0 && (
        <JourneyList journeys={result.journeys} review={result.review} />
      )}
      {closest && (
        <div className="chat-block">
          <h3>Closest match (outside your criteria)</h3>
          <JourneyList journeys={[closest]} review={result.review} />
        </div>
      )}
      {result.alternative && (
        <div className="chat-block">
          <h3>Alternative</h3>
          <p>{result.alternative.description}</p>
          <JourneyList
            journeys={result.alternative.journeys}
            review={result.alternative.review}
          />
        </div>
      )}
    </>
  );
}

function JourneyList({
  journeys,
  review,
}: {
  journeys: Journey[];
  review: Record<string, JourneyReview>;
}) {
  return (
    <ul className="journey-list">
      {journeys.map((journey) => (
        <JourneyCard
          key={journey.id}
          journey={journey}
          review={review[journey.id]}
        />
      ))}
    </ul>
  );
}

function JourneyCard({
  journey,
  review,
}: {
  journey: Journey;
  review: JourneyReview | undefined;
}) {
  const { tags = [], warnings = [] } = review ?? {};
  // Results stored before return flights existed lack both fields.
  const inbound = journey.inbound ?? null;
  const total = journey.total_price ?? (inbound ? null : journey.price);

  return (
    <li className="journey-card">
      <div className="journey-head">
        <p className="journey-total">
          <strong>{total ? formatMoney(total) : 'No price'}</strong>
          {inbound && <span>both flights</span>}
        </p>
        {tags.length > 0 && (
          <p className="journey-tags">
            {tags.map((tag) => (
              <span key={tag} className="chat-badge badge-tag">
                {tag}
              </span>
            ))}
          </p>
        )}
      </div>

      {inbound ? (
        <>
          <Flight label="Outbound" part={journey} showPrice />
          <Flight label="Return" part={inbound} showPrice />
        </>
      ) : (
        <Flight part={journey} />
      )}

      {warnings.map((warning) => (
        <p key={warning} className="journey-warning">
          <TriangleAlert size={14} aria-hidden="true" />
          <span>{warning}</span>
        </p>
      ))}
    </li>
  );
}

/** One direction: date, duration, stops and the legs. */
function Flight({
  label,
  part,
  showPrice = false,
}: {
  label?: string;
  part: FlightPart;
  showPrice?: boolean;
}) {
  const first = part.legs[0];
  return (
    <div className="journey-flight">
      <p className="journey-facts">
        {label && <span className="journey-direction">{label}</span>}
        {first && <span>{localDate(first.departure)}</span>}
        <span>{formatDuration(part.duration_minutes)}</span>
        <span>{formatStops(part.stops)}</span>
        {showPrice && part.price && (
          <span className="journey-price">{formatMoney(part.price)}</span>
        )}
      </p>
      <ol className="journey-legs">
        {part.legs.map((leg, index) => (
          <li key={index}>
            <span className="journey-time">{localTime(leg.departure)}</span>{' '}
            {leg.origin} →{' '}
            <span className="journey-time">{localTime(leg.arrival)}</span>{' '}
            {leg.destination}
            {leg.number && (
              <span className="journey-number"> · {leg.number}</span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
