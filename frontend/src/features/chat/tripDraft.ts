import type {
  DateWindow,
  Money,
  TripFieldsInput,
  TripState,
  TripType,
} from '../../api/client';

/**
 * The trip form is edited locally as a draft. These helpers turn the server
 * state into a draft, find the fields that differ from the server and keep
 * unsaved edits when a new server state arrives.
 */

export type FieldKey = keyof TripState;

export const fieldKeys: FieldKey[] = [
  'origin',
  'destination',
  'departure',
  'return',
  'trip_type',
  'travelers',
  'budget',
  'max_stops',
];

/** Details a search needs; `return` only while the trip is not one-way. */
export const requiredFields: FieldKey[] = [
  'origin',
  'destination',
  'departure',
  'return',
  'travelers',
];

/** `to` is only used while `flexible` is on. */
export type DateDraft = { flexible: boolean; from: string; to: string };
export type BudgetDraft = {
  amount: string;
  basis: Money['basis'];
  currency: string;
};

/** Input values of the form, one entry per trip field. Empty text = not set. */
export type TripDraft = {
  origin: string;
  destination: string;
  departure: DateDraft;
  return: DateDraft;
  trip_type: TripType;
  travelers: string;
  budget: BudgetDraft;
  max_stops: string;
};

const unknown = { value: null, provenance: 'unknown' } as const;

export const emptyTripState: TripState = {
  origin: unknown,
  destination: unknown,
  departure: unknown,
  return: unknown,
  trip_type: unknown,
  travelers: unknown,
  budget: unknown,
  max_stops: unknown,
};

export const emptyDate: DateDraft = { flexible: false, from: '', to: '' };

function dateDraft(window: DateWindow | null): DateDraft {
  if (!window) return emptyDate;
  return {
    flexible: window.earliest !== window.latest,
    from: window.earliest,
    to: window.latest,
  };
}

const numberText = (value: number | null) =>
  value === null ? '' : String(value);

export function draftFromState(state: TripState): TripDraft {
  const budget = state.budget.value;
  return {
    origin: state.origin.value ?? '',
    destination: state.destination.value ?? '',
    departure: dateDraft(state.departure.value),
    return: dateDraft(state.return.value),
    trip_type: state.trip_type.value === 'one_way' ? 'one_way' : 'round_trip',
    travelers: numberText(state.travelers.value),
    budget: {
      amount: numberText(budget?.amount ?? null),
      basis: budget?.basis ?? 'per_person',
      currency: budget?.currency ?? 'EUR',
    },
    max_stops: numberText(state.max_stops.value),
  };
}

function dateInput(draft: DateDraft): string | DateWindow | null {
  const from = draft.from;
  const to = draft.flexible ? draft.to : draft.from;
  if (!from && !to) return null;
  if (!from || !to || from === to) return from || to;
  return { earliest: from, latest: to };
}

function numberInput(text: string): number | null {
  if (text.trim() === '') return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

/** The draft as the API expects it, with every field present. */
function toInputs(draft: TripDraft): Required<TripFieldsInput> {
  const amount = numberInput(draft.budget.amount);
  return {
    origin: draft.origin.trim() || null,
    destination: draft.destination.trim() || null,
    departure: dateInput(draft.departure),
    // A one-way trip has no return flight.
    return: draft.trip_type === 'one_way' ? null : dateInput(draft.return),
    trip_type: draft.trip_type,
    travelers: numberInput(draft.travelers),
    budget:
      amount === null
        ? null
        : {
            amount,
            currency: draft.budget.currency,
            basis: draft.budget.basis,
          },
    max_stops: numberInput(draft.max_stops),
  };
}

const same = (a: unknown, b: unknown) =>
  JSON.stringify(a) === JSON.stringify(b);

/** Fields whose draft value differs from `base`. */
export function changedKeys(draft: TripDraft, base: TripDraft): FieldKey[] {
  const now = toInputs(draft);
  const before = toInputs(base);
  return fieldKeys.filter((key) => !same(now[key], before[key]));
}

/** Request fields for the changed values only; cleared inputs become null. */
export function changedFields(
  draft: TripDraft,
  base: TripDraft,
): TripFieldsInput {
  const inputs = toInputs(draft);
  return Object.fromEntries(
    changedKeys(draft, base).map((key) => [key, inputs[key]]),
  );
}

function copyField<K extends FieldKey>(
  target: TripDraft,
  source: TripDraft,
  key: K,
) {
  target[key] = source[key];
}

/**
 * The draft after the server state moved from `base` to `next`: fields the
 * user edited keep their local value, everything else follows the server.
 * `sent` is the draft that was applied with this request; fields that still
 * equal it count as saved.
 */
export function mergeDraft(
  current: TripDraft,
  base: TripDraft,
  next: TripDraft,
  sent: TripDraft | null = null,
): TripDraft {
  const unsaved = sent
    ? changedKeys(current, sent)
    : changedKeys(current, base);
  const merged: TripDraft = { ...next };
  for (const key of unsaved) copyField(merged, current, key);
  // The "flexible" switch alone is no edit; keep it open while the user
  // has it open.
  for (const key of ['departure', 'return'] as const)
    if (!unsaved.includes(key) && current[key].flexible && !next[key].flexible)
      merged[key] = { ...next[key], flexible: true, to: next[key].from };
  return merged;
}

/** Today as YYYY-MM-DD in the user's time zone. */
export function todayIso(now = new Date()): string {
  const two = (value: number) => String(value).padStart(2, '0');
  return `${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())}`;
}

/**
 * Problems the form can see itself before anything is sent, keyed by field.
 * The server checks the same rules; checking here first means a chat message
 * is never sent together with form values that would be rejected.
 */
export function draftErrors(
  draft: TripDraft,
  today: string = todayIso(),
): Record<string, string[]> {
  const errors: Record<string, string[]> = {};
  const last = (value: DateDraft) => (value.flexible && value.to ? value.to : value.from);
  if (draft.departure.from && last(draft.departure) < today)
    errors.departure = ['This date is in the past.'];
  if (draft.trip_type !== 'one_way' && draft.return.from) {
    if (last(draft.return) < today) errors.return = ['This date is in the past.'];
    else if (draft.departure.from && last(draft.return) < draft.departure.from)
      errors.return = ['The return must not be before the departure.'];
  }
  const travelers = draft.travelers.trim();
  if (travelers && !(Number.isInteger(Number(travelers)) && Number(travelers) >= 1))
    errors.travelers = ['At least 1 traveller.'];
  return errors;
}

/** How many of the required details are set, e.g. 3 of 5. */
export function progress(state: TripState, missingFields: string[]) {
  const needed = requiredFields.filter(
    (key) => key !== 'return' || state.trip_type.value !== 'one_way',
  );
  const missing = needed.filter((key) => missingFields.includes(key));
  return { set: needed.length - missing.length, total: needed.length };
}
