import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, backend } from '../src/api/client';

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
