import { Heart, Star } from 'lucide-react';
import type { Itinerary, ItineraryDay, ItineraryStep } from './itinerary';

type Props = {
  itinerary: Itinerary;
  /** Currently highlighted step (hovered or selected on map / in the list). */
  activeStepId: string | null;
  onStepHover: (stepId: string | null) => void;
  onStepClick: (stepId: string) => void;
  onToggleSaved: (stepId: string) => void;
};

/** Formats a number like 27331 → "27,331". */
function formatCount(n: number): string {
  return n.toLocaleString('en-US');
}

/** Renders a rating, e.g. "4.5 ★★★★★ (27,331)". */
function Rating({
  rating,
  reviewCount,
}: {
  rating: number;
  reviewCount: number | null;
}) {
  return (
    <span className="itin-rating">
      <span className="itin-rating-number">{rating}</span>
      <span className="itin-stars" aria-label={`${rating} out of 5 stars`}>
        {Array.from({ length: 5 }, (_, i) => {
          const filled = rating >= i + 0.75;
          const half = !filled && rating >= i + 0.25;
          return (
            <Star
              key={i}
              size={13}
              className={
                filled ? 'star-filled' : half ? 'star-half' : 'star-empty'
              }
            />
          );
        })}
      </span>
      {reviewCount !== null && (
        <span className="itin-review-count">
          ({formatCount(reviewCount)})
        </span>
      )}
    </span>
  );
}

function StepCard({
  step,
  isActive,
  onHover,
  onClick,
  onToggleSaved,
}: {
  step: ItineraryStep;
  isActive: boolean;
  onHover: (id: string | null) => void;
  onClick: (id: string) => void;
  onToggleSaved: (id: string) => void;
}) {
  return (
    <article
      className={`itin-step${isActive ? ' is-active' : ''}`}
      data-step-id={step.id}
      onMouseEnter={() => onHover(step.id)}
      onMouseLeave={() => onHover(null)}
      onClick={() => onClick(step.id)}
    >
      {step.imageUrl && (
        <div className="itin-step-image">
          <img src={step.imageUrl} alt={step.name} loading="lazy" />
          <button
            type="button"
            className={`itin-save-btn${step.saved ? ' is-saved' : ''}`}
            onClick={(event) => {
              event.stopPropagation();
              onToggleSaved(step.id);
            }}
            aria-label={step.saved ? 'Remove from saved' : 'Save'}
            title={step.saved ? 'Remove from saved' : 'Save'}
          >
            <Heart size={18} fill={step.saved ? 'currentColor' : 'none'} />
          </button>
        </div>
      )}

      <div className="itin-step-body">
        <h4 className="itin-step-title">
          <span className="itin-step-index">{step.index}.</span> {step.name}
        </h4>

        {(step.rating !== null || step.subtitle) && (
          <div className="itin-step-meta">
            {step.rating !== null && (
              <Rating rating={step.rating} reviewCount={step.reviewCount} />
            )}
            {step.subtitle && (
              <span className="itin-step-subtitle">{step.subtitle}</span>
            )}
          </div>
        )}

        {step.tags.length > 0 && (
          <div className="itin-step-tags">
            {step.tags.map((tag) => (
              <span key={tag} className="itin-tag">
                {tag}
              </span>
            ))}
          </div>
        )}

        <div className="itin-step-actions">
          <button
            type="button"
            className="itin-details-btn"
            onClick={(event) => {
              event.stopPropagation();
              onClick(step.id);
            }}
          >
            See details
          </button>
        </div>
      </div>
    </article>
  );
}

function DaySection({
  day,
  activeStepId,
  onStepHover,
  onStepClick,
  onToggleSaved,
}: {
  day: ItineraryDay;
  activeStepId: string | null;
  onStepHover: (id: string | null) => void;
  onStepClick: (id: string) => void;
  onToggleSaved: (id: string) => void;
}) {
  return (
    <section className="itin-day">
      <div className="itin-day-header">
        <h3>Day {day.dayNumber}</h3>
        {(day.theme || day.area) && (
          <p className="itin-day-desc">
            {day.theme}
            {day.theme && day.area && ' '}
            {day.area && <span className="itin-day-area">({day.area})</span>}
          </p>
        )}
      </div>
      <div className="itin-day-steps">
        {day.steps.map((step) => (
          <StepCard
            key={step.id}
            step={step}
            isActive={step.id === activeStepId}
            onHover={onStepHover}
            onClick={onStepClick}
            onToggleSaved={onToggleSaved}
          />
        ))}
      </div>
    </section>
  );
}

/**
 * Center panel: the itinerary grouped by day, with numbered steps that carry
 * photos, ratings and tags. Hovering a card previews its map pin; clicking
 * selects the stop.
 */
export function ItineraryPanel({
  itinerary,
  activeStepId,
  onStepHover,
  onStepClick,
  onToggleSaved,
}: Props) {
  if (itinerary.days.length === 0) {
    return (
      <section className="itin-panel itin-empty">
        <div className="itin-empty-content">
          <h2>Itinerary</h2>
          <p>
            Start chatting to plan your trip. The itinerary steps will appear
            here as the agent builds your plan.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="itin-panel" aria-label="Itinerary">
      <div className="itin-header">
        <h2>
          Results for “<em>{itinerary.title}</em>”
        </h2>
      </div>
      <div className="itin-scroll">
        {itinerary.days.map((day) => (
          <DaySection
            key={day.dayNumber}
            day={day}
            activeStepId={activeStepId}
            onStepHover={onStepHover}
            onStepClick={onStepClick}
            onToggleSaved={onToggleSaved}
          />
        ))}
        <p className="itin-credit">
          Place photos via{' '}
          <a
            href="https://commons.wikimedia.org/"
            target="_blank"
            rel="noreferrer"
          >
            Wikimedia Commons
          </a>
        </p>
      </div>
    </section>
  );
}
