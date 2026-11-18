import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, backend, nestedFieldErrors } from '../src/api/client';

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function stubFetch(result: Response | Error) {
  const fetchMock = vi.fn<typeof fetch>(() =>
    result instanceof Error ? Promise.reject(result) : Promise.resolve(result),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function apiError(promise: Promise<unknown>) {
  const error = await promise.then(
    () => null,
    (reason: unknown) => reason,
  );
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

afterEach(() => vi.unstubAllGlobals());

describe('Backend API client', () => {
  it('reads the health status from the versioned API path', async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, { status: 'ok', database: 'ok' }),
    );
    await expect(backend.health()).resolves.toEqual({
      status: 'ok',
      database: 'ok',
    });
    const [url, init = {}] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/v1/health/');
    expect(init.headers).toMatchObject({ Accept: 'application/json' });
  });

  it('creates a planning session with a JSON body', async () => {
    const session = {
      id: '4f9c1d3e-0000-4000-8000-000000000001',
      title: 'Weekend in Leipzig',
      created_at: '2026-11-10T10:58:14.639761Z',
    };
    const fetchMock = stubFetch(jsonResponse(201, session));
    await expect(
      backend.createPlanningSession('Weekend in Leipzig'),
    ).resolves.toEqual(session);
    const [url, init = {}] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/v1/planning-sessions/');
    expect(init.method).toBe('POST');
    expect(init.body).toBe(JSON.stringify({ title: 'Weekend in Leipzig' }));
    expect(init.headers).toMatchObject({ 'Content-Type': 'application/json' });
  });

  it('encodes the session ID in the detail path', async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, { id: 'a b', title: 'x', created_at: '' }),
    );
    await backend.getPlanningSession('a b');
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/planning-sessions/a%20b/');
  });

  it('exposes code, message and field errors of a rejected request', async () => {
    stubFetch(
      jsonResponse(400, {
        error: {
          code: 'validation_error',
          message: 'The input is invalid.',
          fields: { title: ['This field may not be blank.'] },
        },
      }),
    );
    const error = await apiError(backend.createPlanningSession(''));
    expect(error).toMatchObject({
      kind: 'http',
      status: 400,
      code: 'validation_error',
      message: 'The input is invalid.',
      fields: { title: ['This field may not be blank.'] },
    });
  });

  it('marks a 503 from the backend as temporarily unavailable', async () => {
    stubFetch(
      jsonResponse(503, {
        error: {
          code: 'service_unavailable',
          message: 'The database is not reachable.',
        },
      }),
    );
    const error = await apiError(backend.health());
    expect(error).toMatchObject({
      kind: 'unavailable',
      status: 503,
      code: 'service_unavailable',
      fields: {},
    });
  });

  it('reports a failed connection as unreachable', async () => {
    stubFetch(new TypeError('Failed to fetch'));
    const error = await apiError(backend.health());
    expect(error).toMatchObject({
      kind: 'unreachable',
      status: null,
      code: 'backend_unreachable',
    });
  });

  it('treats a server error without API body as an unreachable backend', async () => {
    // The dev proxy or a gateway answers with 5xx when Django is down.
    stubFetch(new Response('', { status: 502 }));
    const error = await apiError(backend.health());
    expect(error).toMatchObject({
      kind: 'unreachable',
      status: 502,
      code: 'backend_unreachable',
    });
  });

  it('keeps other HTTP errors without API body generic', async () => {
    stubFetch(new Response('<html>Not found</html>', { status: 404 }));
    const error = await apiError(backend.getPlanningSession('missing'));
    expect(error).toMatchObject({ kind: 'http', status: 404, code: 'http_error' });
  });

  it('rejects a successful response that is not JSON', async () => {
    stubFetch(new Response('ok', { status: 200 }));
    const error = await apiError(backend.health());
    expect(error).toMatchObject({ status: 200, code: 'invalid_response' });
  });

  it('passes aborts through instead of reporting a backend error', async () => {
    const controller = new AbortController();
    controller.abort();
    stubFetch(new DOMException('The operation was aborted.', 'AbortError'));
    const error = await backend.health(controller.signal).catch(
      (reason: unknown) => reason,
    );
    expect(error).not.toBeInstanceOf(ApiError);
    expect((error as Error).name).toBe('AbortError');
  });
});

describe('Chat messages', () => {
  it('sends a message as JSON to the encoded session path', async () => {
    const turn = {
      user_message: null,
      reply: {
        id: 'm2',
        role: 'assistant',
        content: 'Where do you want to go?',
        created_at: '2026-11-15T18:30:00Z',
        result: null,
      },
      trip_state: {},
      missing_fields: ['destination'],
    };
    const fetchMock = stubFetch(jsonResponse(201, turn));
    await expect(
      backend.sendMessage('a b', { text: 'Hallo' }),
    ).resolves.toEqual(turn);
    const [url, init = {}] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/v1/planning-sessions/a%20b/messages/');
    expect(init.method).toBe('POST');
    expect(init.body).toBe(JSON.stringify({ text: 'Hallo' }));
    expect(init.headers).toMatchObject({ 'Content-Type': 'application/json' });
  });

  it('sends structured fields without text', async () => {
    const fetchMock = stubFetch(jsonResponse(201, {}));
    await backend.sendMessage('s1', { fields: { travelers: 2 } });
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(
      JSON.stringify({ fields: { travelers: 2 } }),
    );
  });

  it('sends cleared fields as null', async () => {
    const fetchMock = stubFetch(jsonResponse(201, {}));
    await backend.sendMessage('s1', {
      fields: { return: null, budget: null, trip_type: 'one_way' },
    });
    const [url, init = {}] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/v1/planning-sessions/s1/messages/');
    expect(JSON.parse(String(init.body))).toEqual({
      fields: { return: null, budget: null, trip_type: 'one_way' },
    });
  });

  it('reads the trip state from the encoded session path', async () => {
    const body = {
      trip_state: { origin: { value: 'Berlin', provenance: 'confirmed' } },
      missing_fields: ['destination', 'departure', 'return', 'travelers'],
    };
    const fetchMock = stubFetch(jsonResponse(200, body));
    const controller = new AbortController();
    await expect(
      backend.getTripState('a b', controller.signal),
    ).resolves.toEqual(body);
    const [url, init = {}] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/v1/planning-sessions/a%20b/trip-state/');
    expect(init.method).toBeUndefined();
    expect(init.body).toBeUndefined();
    expect(init.signal).toBe(controller.signal);
  });

  it('exposes the nested field errors of rejected trip fields', async () => {
    stubFetch(
      jsonResponse(400, {
        error: {
          code: 'validation_error',
          message: 'The input is invalid.',
          fields: { fields: { travelers: ['Must be at least 1.'] } },
        },
      }),
    );
    const error = await apiError(
      backend.sendMessage('s1', { fields: { travelers: 0 } }),
    );
    expect(error.code).toBe('validation_error');
    expect(nestedFieldErrors(error, 'fields')).toEqual({
      travelers: ['Must be at least 1.'],
    });
    expect(nestedFieldErrors(error, 'text')).toEqual({});
  });

  it('lists the messages of a session', async () => {
    const page = { count: 0, next: null, previous: null, results: [] };
    const fetchMock = stubFetch(jsonResponse(200, page));
    await expect(backend.listMessages('a b')).resolves.toEqual(page);
    const [url, init = {}] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/v1/planning-sessions/a%20b/messages/');
    expect(init.method).toBeUndefined();
    expect(init.body).toBeUndefined();
  });

  it('requests a specific page of messages', async () => {
    const fetchMock = stubFetch(jsonResponse(200, {}));
    await backend.listMessages('s1', 3);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/v1/planning-sessions/s1/messages/?page=3',
    );
  });

  it('marks an unavailable language model as temporarily unavailable', async () => {
    stubFetch(
      jsonResponse(503, {
        error: { code: 'llm_unavailable', message: 'The planner is down.' },
      }),
    );
    const error = await apiError(backend.sendMessage('s1', { text: 'Hi' }));
    expect(error).toMatchObject({ kind: 'unavailable', status: 503 });
  });
});

describe('Places', () => {
  it('lists the places with flight data', async () => {
    const page = {
      count: 1,
      next: null,
      previous: null,
      results: [
        { name: 'Lissabon', country: 'Portugal', aliases: ['lisbon', 'lis'] },
      ],
    };
    const fetchMock = stubFetch(jsonResponse(200, page));
    const controller = new AbortController();
    await expect(backend.listPlaces(controller.signal)).resolves.toEqual(page);
    const [url, init = {}] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/v1/places/');
    expect(init.method).toBeUndefined();
    expect(init.signal).toBe(controller.signal);
  });

  it('reports an unreachable journey planner as unavailable', async () => {
    stubFetch(
      jsonResponse(503, {
        error: {
          code: 'planner_unavailable',
          message: 'The journey planner is not reachable.',
        },
      }),
    );
    const error = await apiError(backend.listPlaces());
    expect(error).toMatchObject({ kind: 'unavailable', status: 503 });
  });
});

describe('Reference cases', () => {
  const page = { count: 0, next: null, previous: null, results: [] };

  it('lists reference cases without filters', async () => {
    const fetchMock = stubFetch(jsonResponse(200, page));
    await expect(backend.listReferenceCases()).resolves.toEqual(page);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/reference-cases/');
  });

  it('passes only the given filters as query parameters', async () => {
    const fetchMock = stubFetch(jsonResponse(200, page));
    await backend.listReferenceCases({
      split: 'validation',
      level: 'hard',
      days: undefined,
      page: 2,
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/v1/reference-cases/?split=validation&level=hard&page=2',
    );
  });
});
