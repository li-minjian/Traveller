import { Check, ChevronDown, ChevronUp, Minus, Plus } from 'lucide-react';
import { useId, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import type { FieldErrors, Money, Place, TripState } from '../../api/client';
import { PlaceInput } from './PlaceInput';
import { changedKeys, emptyDate, progress, todayIso } from './tripDraft';
import type { DateDraft, FieldKey, TripDraft } from './tripDraft';

type Status = 'unsaved' | 'needed' | 'assumed' | 'confirmed' | null;

type Props = {
  /** Trip data as the server knows it. */
  state: TripState;
  missingFields: string[];
  /** Local input values and the draft that mirrors the server state. */
  draft: TripDraft;
  base: TripDraft;
  /** Validation errors by field name, and one message for everything else. */
  errors: FieldErrors;
  error: string | null;
  /** Cities with flight data; `null` while loading or unavailable. */
  places: Place[] | null;
  /** The city list could not be loaded; From and To take free text. */
  placesUnavailable: boolean;
  /** No conversation yet. */
  disabled: boolean;
  /** A request is running. */
  busy: boolean;
  applying: boolean;
  onEdit: <K extends FieldKey>(key: K, value: TripDraft[K]) => void;
  onApply: () => void;
  onDiscard: () => void;
};

/**
 * Editable trip data next to the chat. Edits stay local until "Apply
 * changes" sends the changed fields in one request.
 */
export function TripForm({
  state,
  missingFields,
  draft,
  base,
  errors,
  error,
  places,
  placesUnavailable,
  disabled,
  busy,
  applying,
  onEdit,
  onApply,
  onDiscard,
}: Props) {
  const id = useId();
  // Only narrow screens offer the toggle; there the form starts collapsed
  // so that the chat stays in view.
  const [collapsedByUser, setCollapsed] = useState(true);
  // A problem in the form is never hidden behind the toggle.
  const hasProblem = error !== null || Object.keys(errors).length > 0;
  const collapsed = collapsedByUser && !hasProblem;

  const oneWay = draft.trip_type === 'one_way';
  const unsaved = changedKeys(draft, base);
  const { set, total } = progress(state, missingFields);

  function statusOf(key: FieldKey): Status {
    if (unsaved.includes(key)) return 'unsaved';
    if (missingFields.includes(key) && !(key === 'return' && oneWay))
      return 'needed';
    const field = state[key];
    if (field.value === null) return null;
    if (field.provenance === 'inferred') return 'assumed';
    return field.provenance === 'confirmed' ? 'confirmed' : null;
  }

  /** Props that connect an input with the error text of its field. */
  function invalid(key: FieldKey) {
    return errors[key]
      ? { 'aria-invalid': true, 'aria-describedby': `${id}-${key}-error` }
      : {};
  }

  function field(key: FieldKey) {
    return {
      status: statusOf(key),
      error: errors[key],
      errorId: `${id}-${key}-error`,
    };
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    onApply();
  }

  function setOneWay(checked: boolean) {
    onEdit('trip_type', checked ? 'one_way' : 'round_trip');
    if (checked) onEdit('return', emptyDate);
  }

  const travelers = Number(draft.travelers) || 0;
  // Countries only help when the list can turn them into cities.
  const placePlaceholder = places ? 'City or country' : 'City';
  const stopOptions = ['0', '1', '2'];

  return (
    <aside
      className="section-card chat-card trip-card"
      aria-labelledby={`${id}-heading`}
    >
      <div className="chat-head">
        <h2 id={`${id}-heading`}>Trip</h2>
        <button
          className="button button-outline trip-toggle"
          type="button"
          aria-expanded={!collapsed}
          aria-controls={`${id}-form`}
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? <ChevronDown size={15} /> : <ChevronUp size={15} />}
          {collapsed ? 'Show details' : 'Hide details'}
        </button>
      </div>

      <div className="trip-progress">
        <div
          className="trip-meter"
          role="progressbar"
          aria-label="Required trip details"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={set}
        >
          <span style={{ width: `${(set / total) * 100}%` }} />
        </div>
        <p role="status">
          {set === total
            ? `All ${total} details set – change anything here or in the chat.`
            : `${set} of ${total} details set – the agent will ask for the rest.`}
        </p>
      </div>

      <form
        id={`${id}-form`}
        className={`trip-form${collapsed ? ' is-collapsed' : ''}`}
        onSubmit={submit}
        noValidate
      >
        <p className="trip-note">
          Flights are available between the listed European cities (example
          data).
          {placesUnavailable &&
            ' The city list could not be loaded – type the city name.'}
        </p>

        <FormField label="From" htmlFor={`${id}-origin`} {...field('origin')}>
          <PlaceInput
            id={`${id}-origin`}
            value={draft.origin}
            onChange={(value) => onEdit('origin', value)}
            places={places}
            placeholder={placePlaceholder}
            disabled={disabled}
            {...invalid('origin')}
          />
        </FormField>

        <FormField
          label="To"
          htmlFor={`${id}-destination`}
          {...field('destination')}
        >
          <PlaceInput
            id={`${id}-destination`}
            value={draft.destination}
            onChange={(value) => onEdit('destination', value)}
            places={places}
            placeholder={placePlaceholder}
            disabled={disabled}
            {...invalid('destination')}
          />
        </FormField>

        <DateField
          id={`${id}-departure`}
          label="Departure"
          value={draft.departure}
          min={todayIso()}
          onChange={(value) => onEdit('departure', value)}
          disabled={disabled}
          invalid={invalid('departure')}
          {...field('departure')}
        />

        <DateField
          id={`${id}-return`}
          label="Return"
          value={draft.return}
          min={draft.departure.from || todayIso()}
          onChange={(value) => onEdit('return', value)}
          disabled={disabled || oneWay}
          invalid={invalid('return')}
          {...field('return')}
        >
          <span className="trip-check-row">
            <label className="trip-check">
              <input
                type="checkbox"
                checked={oneWay}
                onChange={(event) => setOneWay(event.target.checked)}
                disabled={disabled}
                {...invalid('trip_type')}
              />
              One-way
            </label>
            <StatusBadge status={statusOf('trip_type')} />
          </span>
          {errors.trip_type && (
            <p className="field-error" id={`${id}-trip_type-error`}>
              {errors.trip_type.join(' ')}
            </p>
          )}
        </DateField>

        <div className="trip-row">
          <FormField
            label="Travellers"
            htmlFor={`${id}-travelers`}
            {...field('travelers')}
          >
            <div className="stepper">
              <button
                type="button"
                aria-label="One traveller fewer"
                onClick={() => onEdit('travelers', String(travelers - 1))}
                disabled={disabled || travelers <= 1}
              >
                <Minus size={15} aria-hidden="true" />
              </button>
              <input
                id={`${id}-travelers`}
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                value={draft.travelers}
                onChange={(event) => {
                  // Nobody travels with 0 or a negative number of people.
                  const typed = event.target.value;
                  onEdit('travelers', typed !== '' && Number(typed) < 1 ? '1' : typed);
                }}
                placeholder="–"
                disabled={disabled}
                {...invalid('travelers')}
              />
              <button
                type="button"
                aria-label="One traveller more"
                onClick={() =>
                  onEdit('travelers', String(Math.max(travelers, 0) + 1))
                }
                disabled={disabled}
              >
                <Plus size={15} aria-hidden="true" />
              </button>
            </div>
          </FormField>

          <FormField
            label="Max. stops"
            htmlFor={`${id}-stops`}
            {...field('max_stops')}
          >
            <select
              id={`${id}-stops`}
              value={draft.max_stops}
              onChange={(event) => onEdit('max_stops', event.target.value)}
              disabled={disabled}
              {...invalid('max_stops')}
            >
              <option value="">Any</option>
              <option value="0">Direct</option>
              <option value="1">1</option>
              <option value="2">2</option>
              {draft.max_stops !== '' &&
                !stopOptions.includes(draft.max_stops) && (
                  <option value={draft.max_stops}>{draft.max_stops}</option>
                )}
            </select>
          </FormField>
        </div>

        <FormField
          label={`Max. budget (${
            draft.budget.currency === 'EUR' ? '€' : draft.budget.currency
          })`}
          htmlFor={`${id}-budget`}
          {...field('budget')}
        >
          <div className="trip-budget">
            <input
              id={`${id}-budget`}
              type="number"
              inputMode="decimal"
              min={0}
              step={10}
              value={draft.budget.amount}
              onChange={(event) =>
                onEdit('budget', { ...draft.budget, amount: event.target.value })
              }
              placeholder="No limit"
              disabled={disabled}
              {...invalid('budget')}
            />
            <label className="visually-hidden" htmlFor={`${id}-basis`}>
              Budget applies
            </label>
            <select
              id={`${id}-basis`}
              value={draft.budget.basis}
              onChange={(event) =>
                onEdit('budget', {
                  ...draft.budget,
                  basis: event.target.value as Money['basis'],
                })
              }
              disabled={disabled}
            >
              <option value="per_person">per person</option>
              <option value="trip_total">total</option>
            </select>
          </div>
          {!oneWay && (
            <p className="trip-note">For both flights together.</p>
          )}
        </FormField>

        {error && (
          <p className="system-error" role="alert">
            {error}
          </p>
        )}
        {!error && unsaved.length > 0 && (
          <p className="trip-note">
            Not applied yet – these details are also sent with your next chat
            message.
          </p>
        )}

        <div className="trip-actions">
          <button
            className="button button-primary"
            type="submit"
            disabled={disabled || busy || unsaved.length === 0}
          >
            <Check size={15} /> {applying ? 'Applying…' : 'Apply changes'}
          </button>
          {unsaved.length > 0 && (
            <button
              className="button button-outline"
              type="button"
              onClick={onDiscard}
              disabled={applying}
            >
              Discard
            </button>
          )}
        </div>
      </form>
    </aside>
  );
}

function StatusBadge({ status }: { status: Status }) {
  if (status === null) return null;
  if (status === 'confirmed')
    return (
      <span className="trip-confirmed" title="Confirmed">
        <Check size={13} aria-hidden="true" />
        <span className="visually-hidden">confirmed</span>
      </span>
    );
  return (
    <span
      className={`chat-badge badge-${status}`}
      title={
        status === 'assumed'
          ? 'The agent assumed this value.'
          : status === 'needed'
            ? 'Needed for the search.'
            : 'Not applied yet.'
      }
    >
      {status}
    </span>
  );
}

type FieldProps = {
  label: string;
  status: Status;
  error: string[] | undefined;
  errorId: string;
};

function fieldClass(status: Status) {
  return `trip-field${status === 'needed' ? ' is-needed' : ''}`;
}

function FormField({
  label,
  htmlFor,
  status,
  error,
  errorId,
  children,
}: FieldProps & { htmlFor: string; children: ReactNode }) {
  return (
    <div className={fieldClass(status)}>
      <div className="trip-label">
        <label htmlFor={htmlFor}>{label}</label>
        <StatusBadge status={status} />
      </div>
      {children}
      {error && (
        <p className="field-error" id={errorId}>
          {error.join(' ')}
        </p>
      )}
    </div>
  );
}

/** A fixed day, or with "Flexible" a window of two dates. */
function DateField({
  id,
  label,
  value,
  min,
  onChange,
  disabled,
  invalid,
  status,
  error,
  errorId,
  children,
}: FieldProps & {
  id: string;
  value: DateDraft;
  min?: string;
  onChange: (value: DateDraft) => void;
  disabled: boolean;
  invalid: object;
  children?: ReactNode;
}) {
  return (
    <div
      className={fieldClass(status)}
      role="group"
      aria-labelledby={`${id}-label`}
    >
      <div className="trip-label">
        <span id={`${id}-label`}>{label}</span>
        <StatusBadge status={status} />
        <label className="trip-check trip-flexible">
          <input
            type="checkbox"
            checked={value.flexible}
            onChange={(event) =>
              onChange({
                flexible: event.target.checked,
                from: value.from,
                to: value.from,
              })
            }
            disabled={disabled}
          />
          Flexible
        </label>
      </div>
      <div className="trip-dates">
        <label htmlFor={`${id}-from`}>
          <span className={value.flexible ? undefined : 'visually-hidden'}>
            {value.flexible ? 'From' : `${label} date`}
          </span>
          <input
            id={`${id}-from`}
            type="date"
            value={value.from}
            min={min || undefined}
            onChange={(event) =>
              onChange({ ...value, from: event.target.value })
            }
            disabled={disabled}
            {...invalid}
          />
        </label>
        {value.flexible && (
          <label htmlFor={`${id}-to`}>
            <span>To</span>
            <input
              id={`${id}-to`}
              type="date"
              value={value.to}
              min={value.from || min || undefined}
              onChange={(event) =>
                onChange({ ...value, to: event.target.value })
              }
              disabled={disabled}
              {...invalid}
            />
          </label>
        )}
      </div>
      {error && (
        <p className="field-error" id={errorId}>
          {error.join(' ')}
        </p>
      )}
      {children}
    </div>
  );
}
