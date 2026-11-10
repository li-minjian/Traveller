import { Activity, Plus, RefreshCw, Search } from 'lucide-react';
import { useEffect, useId, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError, backend } from '../api/client';
import type { PlanningSession } from '../api/client';
import { Eyebrow } from '../components/ui';

/**
 * Technical page that checks the connection frontend → Django → PostgreSQL:
 * backend health, creating a planning session and loading it again.
 */
export function SystemStatusPage() {
  return (
    <div className="page system-page">
      <header className="system-intro">
        <Eyebrow>
          <Activity size={14} /> System / Developer
        </Eyebrow>
        <h1>System status</h1>
        <p>
          Technical checks for the connection between this frontend, the
          Django backend and PostgreSQL. Sessions created here are stored in
          the development database.
        </p>
      </header>
      <HealthCard />
      <SessionCards />
    </div>
  );
}

const lastSessionKey = 'traveller.lastPlanningSessionId';

function readLastSessionId() {
  try {
    return localStorage.getItem(lastSessionKey) ?? '';
  } catch {
    return '';
  }
}

function storeLastSessionId(id: string) {
  try {
    localStorage.setItem(lastSessionKey, id);
  } catch {
    // The page keeps working when storage is disabled.
  }
}

function describeError(error: unknown) {
  if (!(error instanceof ApiError))
    return 'Something unexpected went wrong. Please try again.';
  if (error.kind === 'unreachable')
    return 'The backend did not respond. Check that the Django server is running.';
  if (error.kind === 'unavailable')
    return 'The backend is running, but the database is currently not reachable.';
  if (error.code === 'validation_error')
    return 'The backend rejected the input. Please correct the highlighted field.';
  if (error.code === 'not_found')
    return 'No planning session exists with this ID.';
  return `${error.message} (HTTP ${error.status})`;
}

function formatTime(date: Date) {
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, {
        dateStyle: 'medium',
        timeStyle: 'medium',
      });
}

type Health =
  | { state: 'checking' }
  | { state: 'done'; error: unknown; checkedAt: Date };

function HealthCard() {
  const [health, setHealth] = useState<Health>({ state: 'checking' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    backend.health(controller.signal).then(
      () => setHealth({ state: 'done', error: null, checkedAt: new Date() }),
      (error: unknown) => {
        if (!controller.signal.aborted)
          setHealth({ state: 'done', error, checkedAt: new Date() });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  function recheck() {
    setHealth({ state: 'checking' });
    setAttempt((value) => value + 1);
  }

  let tone = 'checking';
  let label = 'Checking backend…';
  let detail = 'Requesting the health endpoint.';
  if (health.state === 'done' && !health.error) {
    tone = 'ok';
    label = 'Connected';
    detail = 'Backend and database are reachable.';
  } else if (health.state === 'done') {
    const unavailable =
      health.error instanceof ApiError && health.error.kind === 'unavailable';
    tone = unavailable ? 'warning' : 'error';
    label = unavailable ? 'Database unavailable' : 'Backend unreachable';
    detail = describeError(health.error);
  }

  return (
    <section
      className="section-card system-card"
      aria-labelledby="backend-status-heading"
    >
      <h2 id="backend-status-heading">Backend</h2>
      <div className={`system-status status-${tone}`} role="status">
        <span className="status-dot" aria-hidden="true" />
        <div>
          <strong>{label}</strong>
          <p>{detail}</p>
        </div>
      </div>
      <div className="system-actions">
        <button
          className="button button-outline"
          type="button"
          onClick={recheck}
          disabled={health.state === 'checking'}
        >
          <RefreshCw size={15} /> Check again
        </button>
        <p className="system-meta">
          <code>GET /api/v1/health/</code>
          {health.state === 'done' &&
            ` · checked at ${formatTime(health.checkedAt)}`}
        </p>
      </div>
    </section>
  );
}

type Failure = { action: 'create' | 'load'; error: unknown };

function SessionCards() {
  const titleId = useId();
  const sessionIdId = useId();
  const [title, setTitle] = useState('');
  const [sessionId, setSessionId] = useState(readLastSessionId);
  const [busy, setBusy] = useState<'create' | 'load' | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [session, setSession] = useState<PlanningSession | null>(null);

  const titleErrors =
    failure?.action === 'create' && failure.error instanceof ApiError
      ? (failure.error.fields.title ?? [])
      : [];

  async function create(event: FormEvent) {
    event.preventDefault();
    let step: Failure['action'] = 'create';
    setBusy(step);
    setFailure(null);
    try {
      const created = await backend.createPlanningSession(title);
      storeLastSessionId(created.id);
      setSessionId(created.id);
      setTitle('');
      setSession(null);
      step = 'load';
      setBusy(step);
      setSession(await backend.getPlanningSession(created.id));
    } catch (error) {
      setFailure({ action: step, error });
    } finally {
      setBusy(null);
    }
  }

  async function load(event: FormEvent) {
    event.preventDefault();
    setBusy('load');
    setFailure(null);
    setSession(null);
    try {
      setSession(await backend.getPlanningSession(sessionId.trim()));
    } catch (error) {
      setFailure({ action: 'load', error });
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <section
        className="section-card system-card"
        aria-labelledby="create-session-heading"
      >
        <h2 id="create-session-heading">Create planning session</h2>
        <p className="system-meta">
          <code>POST /api/v1/planning-sessions/</code> · The backend validates
          the title.
        </p>
        <form className="system-form" onSubmit={create} noValidate>
          <label htmlFor={titleId}>
            Title
            <input
              id={titleId}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Weekend in Leipzig"
              aria-invalid={titleErrors.length > 0 || undefined}
              aria-describedby={
                titleErrors.length > 0 ? `${titleId}-error` : undefined
              }
            />
          </label>
          <button
            className="button button-primary"
            type="submit"
            disabled={busy !== null}
          >
            <Plus size={15} />
            {busy === 'create' ? 'Creating…' : 'Create session'}
          </button>
        </form>
        {titleErrors.length > 0 && (
          <p className="field-error" id={`${titleId}-error`}>
            {titleErrors.join(' ')}
          </p>
        )}
        {failure?.action === 'create' && (
          <p className="system-error" role="alert">
            {describeError(failure.error)}
          </p>
        )}
      </section>

      <section
        className="section-card system-card"
        aria-labelledby="load-session-heading"
      >
        <h2 id="load-session-heading">Load planning session</h2>
        <p className="system-meta">
          <code>GET /api/v1/planning-sessions/&#123;id&#125;/</code> · A newly
          created session is loaded automatically. The last ID is remembered
          in this browser.
        </p>
        <form className="system-form" onSubmit={load}>
          <label htmlFor={sessionIdId}>
            Session ID
            <input
              id={sessionIdId}
              value={sessionId}
              onChange={(event) => setSessionId(event.target.value)}
              placeholder="UUID of a planning session"
              spellCheck={false}
              autoComplete="off"
            />
          </label>
          <button
            className="button button-outline"
            type="submit"
            disabled={busy !== null || sessionId.trim() === ''}
          >
            <Search size={15} />
            {busy === 'load' ? 'Loading…' : 'Load session'}
          </button>
        </form>
        {busy === 'load' && (
          <p className="system-meta" role="status">
            Loading planning session…
          </p>
        )}
        {failure?.action === 'load' && (
          <p className="system-error" role="alert">
            {describeError(failure.error)}
          </p>
        )}
        {session && (
          <dl className="session-details" aria-label="Loaded planning session">
            <dt>ID</dt>
            <dd>
              <code>{session.id}</code>
            </dd>
            <dt>Title</dt>
            <dd>{session.title}</dd>
            <dt>Created</dt>
            <dd>
              <time dateTime={session.created_at}>
                {formatTimestamp(session.created_at)}
              </time>
            </dd>
          </dl>
        )}
      </section>
    </>
  );
}
