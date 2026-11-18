/**
 * Central access to the Traveller backend. Every API path lives in this file;
 * components call the functions in `backend` instead of using fetch directly.
 *
 * Requests use relative URLs. During development the Vite proxy forwards
 * `/api` to Django (see vite.config.ts).
 */

export const API_BASE = '/api/v1';

export type HealthStatus = { status: 'ok'; database: 'ok' };

export type PlanningSession = {
  id: string;
  title: string;
  /** ISO 8601 timestamp in UTC. */
  created_at: string;
};

export type FieldErrors = Record<string, string[]>;

/** Every list endpoint answers with this page shape. */
export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

/** A city with flight data, e.g. Lissabon in Portugal. */
export type Place = {
  /** Canonical name; the trip form sends exactly this. */
  name: string;
  country: string;
  /** Other spellings and codes in lower case, e.g. "lisbon", "lis". */
  aliases: string[];
};

export type ReferenceSplit = 'train' | 'validation' | 'test';
export type ReferenceLevel = 'easy' | 'medium' | 'hard';

export type BenchmarkDataset = {
  slug: string;
  name: string;
  version: string;
  license: string;
  license_url: string;
  source_url: string;
  homepage_url: string;
  citation: string;
  notice: string;
};

/** Historical TravelPlanner case as listed (without the large fields). */
export type ReferenceCaseSummary = {
  id: string;
  data_kind: 'historical_benchmark';
  dataset: BenchmarkDataset;
  split: ReferenceSplit;
  level: ReferenceLevel;
  query: string;
  org: string;
  dest: string;
  days: number;
  visiting_city_number: number | null;
  date: string[];
  people_number: number | null;
  local_constraint: Record<string, unknown> | null;
  budget: { amount: number; currency: string; basis: string } | null;
  has_annotated_plan: boolean;
};

export type ReferenceCaseQuery = {
  split?: ReferenceSplit;
  level?: ReferenceLevel;
  days?: number;
  page?: number;
};

/** How the planner learned a trip value. */
export type Provenance = 'confirmed' | 'inferred' | 'unknown';
export type Field<T> = { value: T | null; provenance: Provenance };
export type Money = {
  amount: number;
  currency: string;
  basis: 'per_person' | 'trip_total';
};

/** Dates as YYYY-MM-DD; a fixed day has `earliest === latest`. */
export type DateWindow = { earliest: string; latest: string };
export type TripType = 'round_trip' | 'one_way';

export type TripState = {
  origin: Field<string>;
  destination: Field<string>;
  departure: Field<DateWindow>;
  /** Window of the return flight. */
  return: Field<DateWindow>;
  /** An unknown trip type counts as a round trip. */
  trip_type: Field<TripType>;
  travelers: Field<number>;
  /** For a round trip: price of both flights together. */
  budget: Field<Money>;
  /** Per direction. */
  max_stops: Field<number>;
};

/**
 * Trip values set directly, without chat text. Every field is optional and
 * `null` clears it.
 */
export type TripFieldsInput = {
  origin?: string | null;
  destination?: string | null;
  /** A plain YYYY-MM-DD is a fixed day. */
  departure?: string | DateWindow | null;
  return?: string | DateWindow | null;
  trip_type?: TripType | null;
  travelers?: number | null;
  /** A plain number is EUR per person. */
  budget?: number | Money | null;
  max_stops?: number | null;
};

export type TripStateResponse = {
  trip_state: TripState;
  /** Required fields the planner still needs, in asking order. */
  missing_fields: string[];
};

export type Leg = {
  mode: string;
  origin: string;
  destination: string;
  /** ISO local time with offset, e.g. 2027-05-20T06:40:00+02:00. */
  departure: string;
  arrival: string;
  carrier: string | null;
  number: string | null;
};
export type Offer = { id: string; provider: string; price: Money };
/** One direction of a journey. */
export type FlightPart = {
  id: string;
  legs: Leg[];
  offers: Offer[];
  duration_minutes: number;
  stops: number;
  price: Money | null;
};
/** The outbound flight plus, for a round trip, the return flight. */
export type Journey = FlightPart & {
  /** The return flight; null for one-way. */
  inbound: FlightPart | null;
  /** Outbound + inbound; equals `price` for one-way. */
  total_price: Money | null;
};
export type JourneyTag = 'cheapest' | 'fastest' | 'recommended';
export type JourneyReview = { tags: JourneyTag[]; warnings: string[] };

export type SearchResult = {
  status: 'ok' | 'no_results' | 'error';
  journeys: Journey[];
  /** Keyed by journey ID. */
  review: Record<string, JourneyReview>;
  no_results: {
    reason: 'budget' | 'max_stops' | 'no_connection';
    /** The direction that could not be served, if only one failed. */
    direction: 'outbound' | 'inbound' | null;
    closest_journey: Journey | null;
  } | null;
  alternative: {
    strategy: 'flexible_dates' | 'more_stops';
    description: string;
    journeys: Journey[];
    review: Record<string, JourneyReview>;
    request: unknown;
  } | null;
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  /** ISO 8601 timestamp in UTC. */
  created_at: string;
  result: SearchResult | null;
};

export type ChatTurn = {
  user_message: ChatMessage | null;
  reply: ChatMessage;
  trip_state: TripState;
  missing_fields: string[];
};

/** With only `fields` the turn has no user message; the agent still replies. */
export type ChatInput = { text?: string; fields?: TripFieldsInput };

/**
 * - `unreachable`: no answer from Django (connection failed, or the proxy or
 *   gateway responded with a server error instead).
 * - `unavailable`: Django answered 503, e.g. because the database is down.
 * - `http`: Django or the server rejected the request with another status.
 */
export type ApiErrorKind = 'unreachable' | 'unavailable' | 'http';

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string;
  readonly fields: FieldErrors;

  constructor(options: {
    kind: ApiErrorKind;
    status: number | null;
    code: string;
    message: string;
    fields?: FieldErrors;
  }) {
    super(options.message);
    this.name = 'ApiError';
    this.kind = options.kind;
    this.status = options.status;
    this.code = options.code;
    this.fields = options.fields ?? {};
  }
}

/**
 * Field errors of a nested object. A chat turn with invalid `fields` answers
 * with `error.fields.fields = { <fieldName>: [reason] }`; this returns that
 * inner map for `name = 'fields'`.
 */
export function nestedFieldErrors(error: ApiError, name: string): FieldErrors {
  const nested: unknown = (error.fields as Record<string, unknown>)[name];
  if (typeof nested !== 'object' || nested === null || Array.isArray(nested))
    return {};
  const result: FieldErrors = {};
  for (const [key, value] of Object.entries(nested)) {
    const reasons = (Array.isArray(value) ? value : [value]).filter(
      (reason): reason is string => typeof reason === 'string',
    );
    if (reasons.length > 0) result[key] = reasons;
  }
  return result;
}

type ErrorBody = {
  error: { code: string; message: string; fields?: FieldErrors };
};

function isErrorBody(value: unknown): value is ErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value))
    return false;
  const { error } = value as { error: unknown };
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { code?: unknown }).code === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  );
}

const unreachableMessage = 'The backend could not be reached.';

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init.body === undefined
          ? {}
          : { 'Content-Type': 'application/json' }),
      },
    });
  } catch (error) {
    if (init.signal?.aborted) throw error;
    throw new ApiError({
      kind: 'unreachable',
      status: null,
      code: 'backend_unreachable',
      message: unreachableMessage,
    });
  }

  const body: unknown = await response.json().catch(() => undefined);

  if (response.ok) {
    if (body === undefined)
      throw new ApiError({
        kind: 'http',
        status: response.status,
        code: 'invalid_response',
        message: 'The backend sent a response that is not valid JSON.',
      });
    return body as T;
  }

  if (isErrorBody(body))
    throw new ApiError({
      kind: response.status === 503 ? 'unavailable' : 'http',
      status: response.status,
      code: body.error.code,
      message: body.error.message,
      fields: body.error.fields,
    });

  if (response.status >= 500)
    throw new ApiError({
      kind: 'unreachable',
      status: response.status,
      code: 'backend_unreachable',
      message: unreachableMessage,
    });

  throw new ApiError({
    kind: 'http',
    status: response.status,
    code: 'http_error',
    message: `The request failed with HTTP ${response.status}.`,
  });
}

export const backend = {
  health: (signal?: AbortSignal) =>
    request<HealthStatus>('/health/', { signal }),

  createPlanningSession: (title: string, signal?: AbortSignal) =>
    request<PlanningSession>('/planning-sessions/', {
      method: 'POST',
      body: JSON.stringify({ title }),
      signal,
    }),

  getPlanningSession: (id: string, signal?: AbortSignal) =>
    request<PlanningSession>(
      `/planning-sessions/${encodeURIComponent(id)}/`,
      { signal },
    ),

  sendMessage: (sessionId: string, input: ChatInput, signal?: AbortSignal) =>
    request<ChatTurn>(
      `/planning-sessions/${encodeURIComponent(sessionId)}/messages/`,
      { method: 'POST', body: JSON.stringify(input), signal },
    ),

  /** Messages of a session, oldest first. */
  listMessages: (sessionId: string, page?: number, signal?: AbortSignal) =>
    request<Paginated<ChatMessage>>(
      `/planning-sessions/${encodeURIComponent(sessionId)}/messages/${
        page === undefined ? '' : `?page=${page}`
      }`,
      { signal },
    ),

  /** Trip data the planner knows so far, e.g. to fill the form on load. */
  getTripState: (sessionId: string, signal?: AbortSignal) =>
    request<TripStateResponse>(
      `/planning-sessions/${encodeURIComponent(sessionId)}/trip-state/`,
      { signal },
    ),

  /**
   * Cities with flight data, all in one page, sorted by country and name.
   * Answers 503 while the journey planner is unreachable.
   */
  listPlaces: (signal?: AbortSignal) =>
    request<Paginated<Place>>('/places/', { signal }),

  listReferenceCases: (query: ReferenceCaseQuery = {}, signal?: AbortSignal) => {
    const params = new URLSearchParams();
    for (const [name, value] of Object.entries(query))
      if (value !== undefined) params.set(name, String(value));
    const search = params.toString();
    return request<Paginated<ReferenceCaseSummary>>(
      `/reference-cases/${search ? `?${search}` : ''}`,
      { signal },
    );
  },
};
