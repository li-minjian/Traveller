const settings = process.env;
const subjectTokenType = 'urn:ietf:params:oauth:token-type:jwt';
const cookieName = '__Host-traveller=';

function error(status, code, message) {
  return Response.json({ error: { code, message } }, {
    status,
    headers: { 'cache-control': 'no-store' },
  });
}

async function googleToken(subject) {
  const exchange = await fetch('https://sts.googleapis.com/v1/token', {
    method: 'POST',
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:token-exchange',
      requested_token_type: 'urn:ietf:params:oauth:token-type:access_token',
      scope: 'https://www.googleapis.com/auth/cloud-platform',
      audience: settings.TRAVELLER_WIF_AUDIENCE,
      subject_token_type: subjectTokenType,
      subject_token: subject,
    }),
    signal: AbortSignal.timeout(8000),
  });
  if (!exchange.ok) {
    console.error('Traveller STS request failed', exchange.status);
    throw new Error('Token exchange failed');
  }

  const { access_token: accessToken } = await exchange.json();
  const account = encodeURIComponent(settings.TRAVELLER_CALLER_SERVICE_ACCOUNT);
  const identity = await fetch(
    `https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${account}:generateIdToken`,
    {
      method: 'POST',
      headers: {
        authorization: `Bearer ${accessToken}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({ audience: settings.TRAVELLER_BACKEND_AUDIENCE, includeEmail: true }),
      signal: AbortSignal.timeout(8000),
    },
  );
  if (!identity.ok) {
    console.error('Traveller identity token request failed', identity.status);
    throw new Error('Cloud Run identity token request failed');
  }
  const { token } = await identity.json();
  return token;
}

export default {
  async fetch(request) {
    if (settings.VERCEL_ENV !== 'preview' || !settings.TRAVELLER_BACKEND_URL) {
      return error(404, 'not_found', 'The shared DEV API is unavailable.');
    }
    const url = new URL(request.url);
    const route = url.pathname.startsWith('/api/v1/')
      ? url.pathname.slice('/api/v1/'.length)
      : url.searchParams.get('route');
    const path = route?.replace(/\/$/, '');
    if (!path || !/^[a-z0-9-]+(?:\/[a-z0-9-]+)*$/.test(path)) {
      return error(404, 'not_found', 'API route not found.');
    }
    if (request.method !== 'GET' && request.method !== 'POST') {
      return error(405, 'method_not_allowed', 'Method not allowed.');
    }
    const isPost = request.method === 'POST';
    if (isPost && request.headers.get('origin') !== url.origin) {
      return error(403, 'forbidden', 'The request must originate from this preview.');
    }

    const subject = request.headers.get('x-vercel-oidc-token');
    if (!subject) return error(503, 'service_unavailable', 'Preview identity is unavailable.');

    try {
      const token = await googleToken(subject);
      const upstreamUrl = new URL(`/api/v1/${path}/`, settings.TRAVELLER_BACKEND_URL);
      for (const [key, value] of url.searchParams) {
        if (key !== 'route') upstreamUrl.searchParams.append(key, value);
      }

      const headers = new Headers({
        accept: 'application/json',
        'x-serverless-authorization': `Bearer ${token}`,
      });
      const browserCookie = request.headers.get('cookie')?.split(';')
        .map((cookie) => cookie.trim()).find((cookie) => cookie.startsWith(cookieName));
      if (browserCookie) headers.set('cookie', browserCookie);

      let body;
      if (isPost) {
        headers.set('content-type', request.headers.get('content-type') ?? 'application/json');
        body = await request.arrayBuffer();
      }
      const upstream = await fetch(upstreamUrl, {
        method: request.method,
        headers,
        body,
        redirect: 'error',
        signal: AbortSignal.timeout(90000),
      });

      const contentType = upstream.headers.get('content-type') ?? '';
      if (!contentType.startsWith('application/json')) {
        console.error('Traveller Cloud Run response was not JSON', upstream.status);
        return error(502, 'bad_gateway', 'The shared DEV backend did not return JSON.');
      }
      const responseHeaders = new Headers({
        'cache-control': 'private, no-store',
        'content-type': contentType,
      });
      for (const cookie of upstream.headers.getSetCookie()) {
        if (cookie.startsWith(cookieName)) responseHeaders.append('set-cookie', cookie);
      }
      const paginated = path === 'reference-cases' || path.endsWith('/messages');
      if (!isPost && upstream.ok && paginated) {
        const data = await upstream.json();
        for (const key of ['next', 'previous']) {
          if (data[key]) {
            const link = new URL(data[key]);
            data[key] = new URL(link.pathname + link.search, url.origin).href;
          }
        }
        return Response.json(data, { status: upstream.status, headers: responseHeaders });
      }
      return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
    } catch {
      return error(502, 'bad_gateway', 'The shared DEV backend is unavailable.');
    }
  },
};
