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
