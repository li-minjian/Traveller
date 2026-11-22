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
    <div className="mt-1 flex min-w-0 flex-col gap-2">
      {result.journeys.length > 0 && (
        <JourneyList journeys={result.journeys} review={result.review} />
      )}
      {closest && (
        <div className="flex min-w-0 flex-col gap-1.5">
          <h3 className="m-0 font-sans text-[0.8rem] font-bold text-forest-deep">
            Closest match (outside your criteria)
          </h3>
          <JourneyList journeys={[closest]} review={result.review} />
        </div>
      )}
      {result.alternative && (
        <div className="flex min-w-0 flex-col gap-1.5">
          <h3 className="m-0 font-sans text-[0.8rem] font-bold text-forest-deep">
            Alternative
          </h3>
          <p className="text-[0.72rem] leading-snug text-muted">
            {result.alternative.description}
          </p>
          <JourneyList
            journeys={result.alternative.journeys}
            review={result.alternative.review}
          />
        </div>
      )}
    </div>
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
    <ul className="flex min-w-0 flex-col gap-2 p-0">
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
    <li className="min-w-0 list-none rounded-lg border border-line bg-white p-2.5 text-[0.72rem]">
      <div className="flex flex-wrap items-start justify-between gap-1.5">
        <p className="m-0 text-[0.85rem] font-bold text-forest-deep">
          <strong>{total ? formatMoney(total) : 'No price'}</strong>
          {inbound && (
            <span className="ml-1 text-[0.68rem] font-normal text-muted">
              both flights
            </span>
          )}
        </p>
        {tags.length > 0 && (
          <p className="m-0 flex flex-wrap gap-1">
            {tags.map((tag) => (
              <span
                key={tag}
                className="rounded bg-forest-soft px-1.5 py-0.5 text-[0.64rem] font-semibold text-forest"
              >
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
        <p
          key={warning}
          className="mt-1.5 flex items-start gap-1 text-[0.68rem] leading-snug text-[#7a2e1c]"
        >
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
    <div className="mt-2 border-t border-line pt-2">
      <p className="m-0 flex flex-wrap gap-x-2 gap-y-0.5 text-[0.68rem] text-muted">
        {label && (
          <span className="font-semibold text-forest">{label}</span>
        )}
        {first && <span>{localDate(first.departure)}</span>}
        <span>{formatDuration(part.duration_minutes)}</span>
        <span>{formatStops(part.stops)}</span>
        {showPrice && part.price && (
          <span className="font-semibold text-forest-deep">
            {formatMoney(part.price)}
          </span>
        )}
      </p>
      <ol className="mt-1 ml-4 list-disc space-y-0.5 p-0 text-[0.68rem] leading-snug text-ink">
        {part.legs.map((leg, index) => (
          <li key={index}>
            <span className="font-semibold text-forest-deep">
              {localTime(leg.departure)}
            </span>{' '}
            {leg.origin} →{' '}
            <span className="font-semibold text-forest-deep">
              {localTime(leg.arrival)}
            </span>{' '}
            {leg.destination}
            {leg.number && (
              <span className="text-muted"> · {leg.number}</span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
