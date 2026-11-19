import { Asterisk, Plus } from 'lucide-react';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { journey } from '../../mocks/journey';
import { localTime } from '../chat/format';
import { MessageComposer } from './MessageComposer';
import { SignIn } from './SignIn';
import { ContextContent, ContextEditor } from './TravelContext';
import { applyTrip, displayDate, exampleLeg, newWorkspace, queueMessage, reply } from './demo';
import type { TripContext, Workspace } from './demo';
import './v1.css';

function ResultCard() {
  const price = new Intl.NumberFormat('en-IE', {
    style: 'currency',
    currency: journey.price.currency,
    maximumFractionDigits: 0,
  }).format(journey.price.amount);

  return (
    <article className="v1-result" aria-labelledby="v1-result-title">
      <p className="v1-result-kicker">Sample flight · one way</p>
      <div className="v1-result-route">
        <div>
          <h2 id="v1-result-title">{exampleLeg.origin} → Lisbon</h2>
          <p>{displayDate(exampleLeg.departure.slice(0, 10))} · {exampleLeg.carrier} · {exampleLeg.number}</p>
        </div>
        <strong className="v1-result-price" aria-label={`${price} per person`}>{price}</strong>
      </div>
      <div className="v1-result-row">
        <div>
          <strong>{localTime(exampleLeg.departure)} — {localTime(exampleLeg.arrival)}</strong><br />
          <small>Direct flight · sample itinerary</small>
        </div>
        <span className="v1-pill">Demo only</span>
      </div>
      <p className="v1-result-note">Illustrative data for layout testing. Not a real flight offer or booking.</p>
    </article>
  );
}

function ChatView({ workspace }: { workspace: Workspace }) {
  return (
    <>
      {workspace.messages.length === 0 && (
        <div className="v1-welcome">
          <Asterisk size={36} aria-hidden="true" />
          <h2>Let’s plan your trip.</h2>
          <p>Tell me what you have in mind.<br />We can figure out the details together.</p>
        </div>
      )}
      <div role="log" aria-label="Conversation history">
        {workspace.messages.map(({ role, text }, index) => (
          <div key={index} className={`v1-message v1-message-${role}`}>
            {role === 'assistant' && (
              <span className="v1-avatar"><Asterisk size={17} aria-hidden="true" /></span>
            )}
            <p><span className="v1-visually-hidden">{role === 'user' ? 'You: ' : 'Demo assistant: '}</span>{text}</p>
          </div>
        ))}
        {workspace.pending && <p className="v1-chat-notice">Preparing a demo reply…</p>}
        {workspace.outcome === 'empty' && <p className="v1-chat-notice">No example flights found in this demo scenario.</p>}
        {workspace.outcome === 'result' && <ResultCard />}
      </div>
      {workspace.outcome === 'error' && (
        <p role="alert" className="v1-chat-notice v1-chat-error">
          The simulated flight search failed. Reply “yes” to retry.
        </p>
      )}
    </>
  );
}

export function WorkspacePage() {
  const { state, pathname, search, hash } = useLocation();
  const navigate = useNavigate();
  const firstMessage: unknown = state?.message;
  const scenario = new URLSearchParams(search).get('scenario');
  const [workspace, setWorkspace] = useState(() => {
    return typeof firstMessage === 'string'
      ? queueMessage(newWorkspace(), firstMessage)
      : newWorkspace();
  });
  const [composerKey, setComposerKey] = useState(0);
  const main = useRef<HTMLElement>(null);
  const stream = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const mobileContext = useRef<HTMLDetailsElement>(null);

  useLayoutEffect(() => {
    if (composerKey) input.current?.focus({ preventScroll: true });
    else main.current?.focus({ preventScroll: true });
  }, [composerKey]);

  useLayoutEffect(() => {
    if (stream.current) stream.current.scrollTop = stream.current.scrollHeight;
  }, [workspace]);

  useEffect(() => {
    if (typeof firstMessage === 'string') {
      void navigate({ pathname, search, hash }, { replace: true, state: null });
    }
  }, [firstMessage, navigate, pathname, search, hash]);

  useEffect(() => {
    if (!workspace.pending) return;
    const timer = window.setTimeout(() => setWorkspace((current) => reply(current, scenario)), 350);
    return () => window.clearTimeout(timer);
  }, [workspace.pending, scenario]);

  function reset() {
    setWorkspace(newWorkspace());
    if (mobileContext.current) mobileContext.current.open = false;
    setComposerKey((key) => key + 1);
  }

  function edit() {
    dialog.current?.querySelector('form')?.reset();
    dialog.current?.showModal();
    dialog.current?.querySelector('input')?.focus();
  }

  function save(trip: TripContext) {
    setWorkspace((current) => applyTrip(current, trip));
  }

  const { trip, pending } = workspace;
  const journeyTitle = trip.origin && trip.destination ? `${trip.origin} to ${trip.destination}` : 'Current journey';

  return (
    <div className="v1 v1-workspace">
      <a href="#main-content" className="skip-link">Skip to conversation</a>
      <aside className="v1-sidebar" aria-label="Journey navigation">
        <Link to="/" className="v1-wordmark" aria-label="Traveller home">traveller.</Link>
        <button className="v1-side-new" type="button" onClick={reset}>
          <Plus size={12} aria-hidden="true" /> New journey
        </button>
        <div className="v1-side-current">
          <p>Your journey</p>
          <a href="#main-content" aria-current="true">{journeyTitle}</a>
        </div>
        <SignIn guest />
      </aside>
      <main id="main-content" ref={main} tabIndex={-1} className="v1-conversation">
        <h1 className="v1-visually-hidden">Planning workspace</h1>
        <details className="v1-mobile-context" ref={mobileContext}>
          <summary>Travel context</summary>
          <button className="v1-context-edit" type="button" disabled={!!pending} onClick={edit}>Edit</button>
          <ContextContent trip={trip} />
        </details>
        <div className="v1-stream" ref={stream} tabIndex={0} role="region" aria-label="Conversation">
          <div className="v1-stream-inner">
            <ChatView workspace={workspace} />
          </div>
        </div>
        <div className="v1-composer-wrap">
          <MessageComposer
            key={composerKey}
            inputRef={input}
            pending={!!pending}
            onSend={(message) => setWorkspace((current) => queueMessage(current, message))}
          />
          <p>Interactive UI concept · scripted mock responses · no real travel search</p>
        </div>
      </main>
      <aside className="v1-context" aria-labelledby="v1-context-title">
        <header>
          <h2 id="v1-context-title">Travel context</h2>
          <button className="v1-context-edit" type="button" disabled={!!pending} onClick={edit}>Edit</button>
        </header>
        <ContextContent trip={trip} />
      </aside>
      <ContextEditor trip={trip} dialogRef={dialog} onApply={save} />
    </div>
  );
}
