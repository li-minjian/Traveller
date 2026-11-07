import {
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Map as MapIcon,
  MessageCircle,
  Sparkles,
} from 'lucide-react';
import { useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router';
import { useTravel } from '../app/TravelContext';
import { CriteriaBar, CriteriaDialog } from '../components/Criteria';
import { Results } from '../components/Journeys';
import { Eyebrow } from '../components/ui';

const startingPrompts = [
  'Nature and quiet places',
  'A weekend by train',
  'Business trip to Leipzig from Berlin, meeting at 10:30',
];
const refinements = [
  'No flights',
  'Flexible ±3 days',
  'Show warmer alternatives',
];

export function Workspace({
  children,
  onRefine,
}: {
  children: ReactNode;
  onRefine?: () => void;
}) {
  const { session, submit } = useTravel();
  const [prompt, setPrompt] = useState('');
  const [chatOpen, setChatOpen] = useState(false);
  const conversation = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const element = conversation.current;
    if (element && session.messages.length > 1)
      element.scrollTop = element.scrollHeight;
  }, [chatOpen, session.messages.length]);

  function send(value: string) {
    if (submit(value)) {
      setPrompt('');
      onRefine?.();
    }
  }

  return (
    <div className="workspace">
      <aside
        className={`workspace-side ${chatOpen ? 'mobile-chat-open' : ''}`}
        aria-label="Travel conversation"
      >
        <div className="side-header">
          <span className="assistant-label">
            <Sparkles size={15} /> Wohin assistant
          </span>
          <Link className="side-home" to="/">
            Home <ArrowRight size={13} />
          </Link>
          <button
            className="mobile-chat-button button button-outline"
            type="button"
            aria-expanded={chatOpen}
            aria-controls="chat-content"
            onClick={() => setChatOpen((value) => !value)}
          >
            <MessageCircle size={16} /> {chatOpen ? 'Close chat' : 'Open chat'}
          </button>
        </div>
        {!chatOpen && session.messages.length > 0 && (
          <p className="mobile-prompt">{session.messages.at(-1)?.prompt}</p>
        )}
        <div className="chat-content" id="chat-content">
          <div className="conversation" ref={conversation}>
            <Eyebrow>Travel conversation</Eyebrow>
            <div
              className="chat-messages"
              role="log"
              aria-label="Travel messages"
            >
              {session.messages.length ? (
                session.messages.map((message, index) => (
                  <div className="message-pair" key={index}>
                    <p className="chat-user">{message.prompt}</p>
                    <div className="chat-assistant">
                      <strong>
                        <Sparkles size={13} /> Wohin assistant
                      </strong>
                      <p>{message.reply}</p>
                    </div>
                  </div>
                ))
              ) : (
                <div className="chat-assistant">
                  <strong>
                    <Sparkles size={13} /> Wohin assistant
                  </strong>
                  <p>
                    Tell me a little about your trip. A destination, a date or a
                    mood is enough to start exploring the sample catalogue.
                  </p>
                </div>
              )}
            </div>
            <div className="chat-suggestions">
              <Eyebrow>
                {session.messages.length
                  ? 'Refine your trip'
                  : 'Try an example'}
              </Eyebrow>
              {(session.messages.length ? refinements : startingPrompts).map(
                (text) => (
                  <button
                    className="suggestion"
                    type="button"
                    key={text}
                    onClick={() => send(text)}
                  >
                    {text}
                    <ArrowRight size={14} />
                  </button>
                ),
              )}
            </div>
          </div>
          <form
            className="chat-form"
            onSubmit={(event) => {
              event.preventDefault();
              send(prompt);
            }}
          >
            <input
              aria-label="Refine your trip"
              placeholder="Ask anything or refine your trip…"
              maxLength={600}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
            />
            <button
              className="icon-button send-button"
              aria-label="Send travel message"
              type="submit"
              disabled={!prompt.trim()}
            >
              <ArrowUp size={18} />
            </button>
            <small>Demo assistant · limited vocabulary</small>
          </form>
        </div>
      </aside>
      <div className="workspace-content">{children}</div>
    </div>
  );
}

export function Discovery() {
  const { session, dispatch } = useTravel();
  const { state } = useLocation();
  const destinationGuide =
    typeof state?.from === 'string' &&
    /^\/destinations\/[a-z-]+$/.test(state.from)
      ? state.from
      : null;
  const [criteriaOpen, setCriteriaOpen] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);
  const hasResult =
    session.result?.revision === session.revision &&
    Boolean(session.result?.opportunities.length);
  return (
    <Workspace>
      <div className="workspace-criteria">
        {destinationGuide && (
          <Link to={destinationGuide} className="back-link">
            <ArrowLeft size={16} /> Back to destination guide
          </Link>
        )}
        <CriteriaBar onEdit={() => setCriteriaOpen(true)}>
          {hasResult && (
            <button
              className="chip"
              type="button"
              aria-pressed={mapOpen}
              onClick={() => setMapOpen((value) => !value)}
            >
              <MapIcon size={15} />
              {mapOpen ? 'Hide map' : 'View map'}
            </button>
          )}
        </CriteriaBar>
      </div>
      <div className="workspace-canvas">
        {session.active ? (
          <Results
            mode="ai"
            mapOpen={mapOpen}
            onEdit={() => setCriteriaOpen(true)}
          />
        ) : (
          <section className="discovery-welcome">
            <div className="notice-icon">
              <Sparkles size={23} />
            </div>
            <Eyebrow>Ask AI · Demo workspace</Eyebrow>
            <h1>Tell us where your mind is wandering.</h1>
            <p>
              Start with a wish or browse a few example journeys. Your travel
              criteria carry over from Travel search.
            </p>
            <div className="chip-row">
              {startingPrompts.slice(0, 2).map((text) => (
                <Starter key={text} text={text} />
              ))}
            </div>
            <button
              className="button button-outline"
              type="button"
              onClick={() => dispatch({ type: 'activate' })}
            >
              Browse example journeys <ArrowRight size={16} />
            </button>
          </section>
        )}
      </div>
      <CriteriaDialog
        open={criteriaOpen}
        onClose={() => setCriteriaOpen(false)}
      />
    </Workspace>
  );
}

function Starter({ text }: { text: string }) {
  const { submit } = useTravel();
  return (
    <button type="button" className="chip" onClick={() => submit(text)}>
      {text}
    </button>
  );
}
