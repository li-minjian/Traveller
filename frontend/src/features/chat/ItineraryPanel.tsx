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
    <span className="flex flex-wrap items-center gap-1 text-[0.78rem] leading-tight text-[#1b3a32]">
      <span className="font-semibold">{rating}</span>
      <span
        className="inline-flex items-center gap-px"
        aria-label={`${rating} out of 5 stars`}
      >
        {Array.from({ length: 5 }, (_, i) => {
          const filled = rating >= i + 0.75;
          const half = !filled && rating >= i + 0.25;
          return (
            <Star
              key={i}
              size={13}
              className={
                filled
                  ? 'fill-[#1f7a3d] text-[#1f7a3d]'
                  : half
                    ? 'fill-[#1f7a3d] text-[#1f7a3d] opacity-[0.45]'
                    : 'fill-none text-[#cdd5ce]'
              }
            />
          );
        })}
      </span>
      {reviewCount !== null && (
        <span className="text-[0.74rem] text-[#717f79]">
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
      className={`grid cursor-pointer grid-cols-[clamp(190px,34%,250px)_minmax(0,1fr)] overflow-hidden rounded-[10px] border bg-surface transition hover:border-forest-line hover:shadow-md max-[680px]:grid-cols-[116px_minmax(0,1fr)] ${
        isActive
          ? 'border-forest-line shadow-sm'
          : 'border-line'
      }`}
      data-step-id={step.id}
      onMouseEnter={() => onHover(step.id)}
      onMouseLeave={() => onHover(null)}
      onClick={() => onClick(step.id)}
    >
      {step.imageUrl && (
        <div className="relative aspect-[13/9] w-full self-start overflow-hidden bg-mist max-[680px]:aspect-[4/3]">
          <img
            src={step.imageUrl}
            alt={step.name}
            loading="lazy"
            className="h-full w-full object-cover"
          />
          <button
            type="button"
            className={`absolute top-2 right-2 grid h-8 w-8 place-items-center rounded-full bg-white/95 shadow-md transition hover:scale-105 hover:bg-white ${
              step.saved ? 'text-[#b3261e]' : 'text-forest-deep'
            }`}
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

      <div className="flex min-w-0 flex-col gap-1.5 px-4 py-3.5 max-[680px]:p-3">
        <h4 className="m-0 font-sans text-[1.04rem] font-bold leading-tight tracking-[-0.015em] text-forest-deep">
          <span className="text-forest">{step.index}.</span> {step.name}
        </h4>

        {(step.rating !== null || step.subtitle) && (
          <div className="flex flex-col gap-0.5">
            {step.rating !== null && (
              <Rating rating={step.rating} reviewCount={step.reviewCount} />
            )}
            {step.subtitle && (
              <span className="text-[0.79rem] leading-snug text-[#5f6f69]">
                {step.subtitle}
              </span>
            )}
          </div>
        )}

        {step.tags.length > 0 && (
          <div className="mt-0.5 flex flex-wrap gap-1">
            {step.tags.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center rounded bg-forest px-2 py-1 text-[0.68rem] font-semibold leading-tight whitespace-nowrap text-white"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        <div className="mt-auto flex justify-end pt-2">
          <button
            type="button"
            className="min-h-[34px] rounded-full border border-[#2b7050] bg-white px-4.5 py-1.5 text-[0.78rem] font-semibold text-forest-deep hover:border-forest hover:bg-forest-soft"
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
    <section className="pt-4 first:pt-1 [&:not(:first-child)]:mt-6">
      <div>
        <h3 className="m-0 font-sans text-[1.1rem] font-bold leading-tight tracking-[-0.01em] text-forest-deep">
          Day {day.dayNumber}
        </h3>
        {(day.theme || day.area) && (
          <p className="mt-0.5 text-[0.78rem] leading-snug text-[#6a7872]">
            {day.theme}
            {day.theme && day.area && ' '}
            {day.area && <span className="italic">({day.area})</span>}
          </p>
        )}
      </div>
      <div className="mt-6 flex flex-col gap-3.5">
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
      <section className="flex h-full min-h-0 min-w-0 flex-col items-center justify-center overflow-hidden border-r border-line bg-surface max-[1000px]:h-auto max-[1000px]:min-h-[60dvh] max-[1000px]:border-b max-[1000px]:border-r-0">
        <div className="max-w-[340px] p-10 text-center text-[#667a73]">
          <h2 className="mb-2 font-sans text-[1.8rem] font-bold text-forest-deep">
            Itinerary
          </h2>
          <p className="text-sm leading-relaxed">
            Start chatting to plan your trip. The itinerary steps will appear
            here as the agent builds your plan.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section
      className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-r border-line bg-surface max-[1000px]:h-auto max-[1000px]:min-h-[60dvh] max-[1000px]:border-b max-[1000px]:border-r-0"
      aria-label="Itinerary"
    >
      <div className="shrink-0 px-6 pt-6 pb-[46px] max-[680px]:px-4 max-[680px]:pt-[18px] max-[680px]:pb-6">
        <h2 className="m-0 font-sans text-[1.5rem] font-bold leading-[1.3] tracking-[-0.025em] text-[#0b3b2f]">
          Results for “<em className="not-italic">{itinerary.title}</em>”
        </h2>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pt-1.5 pb-10 [scrollbar-gutter:stable] max-[1000px]:overflow-visible max-[680px]:px-4 max-[680px]:pt-1 max-[680px]:pb-7">
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
        <p className="mt-6 text-center text-[0.68rem] text-[#8a958f]">
          Place photos via{' '}
          <a
            href="https://commons.wikimedia.org/"
            target="_blank"
            rel="noreferrer"
            className="text-inherit"
          >
            Wikimedia Commons
          </a>
        </p>
      </div>
    </section>
  );
}
