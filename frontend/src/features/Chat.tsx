import {
  ArrowUp,
  CalendarDays,
  Check,
  ChevronDown,
  Menu,
  Plus,
  RefreshCw,
  Share2,
} from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError, backend } from '../api/client';
import type {
  ChatMessage,
  ChatTurn,
  TripState,
  TripStateResponse,
} from '../api/client';
import { Results } from './chat/Results';
import { ItineraryPanel } from './chat/ItineraryPanel';
import { MapPanel } from './chat/MapPanel';
import { demoItinerary } from './chat/itinerary';
import type { Itinerary } from './chat/itinerary';
import { emptyTripState, requiredFields } from './chat/tripDraft';

/**
 * Planning workspace: three-panel layout.
 *   Left   – chat with the planning agent
 *   Center – itinerary steps by day
 *   Right  – interactive map with georeferenced markers
 */

const chatSessionKey = 'traveller.chatSessionId';

function readSessionId() {
  try {
    return localStorage.getItem(chatSessionKey) ?? '';
  } catch {
    return '';
  }
}

function storeSessionId(id: string) {
  try {
    localStorage.setItem(chatSessionKey, id);
  } catch {
    // The chat keeps working when storage is disabled.
  }
}

/** Title like "Chat 2026-11-15 18:30" in local time. */
function sessionTitle(now = new Date()) {
  const two = (value: number) => String(value).padStart(2, '0');
  const date = `${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())}`;
  return `Chat ${date} ${two(now.getHours())}:${two(now.getMinutes())}`;
}

async function loadHistory(sessionId: string, signal: AbortSignal) {
  const messages: ChatMessage[] = [];
  for (let page = 1; ; page += 1) {
    const result = await backend.listMessages(sessionId, page, signal);
    messages.push(...result.results);
    if (!result.next || result.results.length === 0) return messages;
  }
}

/** What the server knows about the trip. */
type Trip = { state: TripState; missingFields: string[] };

const emptyTrip: Trip = {
  state: emptyTripState,
  missingFields: requiredFields,
};

/** Fields an older backend does not send yet count as unknown. */
function toTrip(response: TripStateResponse): Trip {
  return {
    state: { ...emptyTripState, ...response.trip_state },
    missingFields: response.missing_fields,
  };
}

async function loadTrip(sessionId: string, signal: AbortSignal) {
  try {
    return toTrip(await backend.getTripState(sessionId, signal));
  } catch (reason) {
    // Without the trip state the panel starts empty and fills with the first
    // turn; a missing session shows up when the history is loaded.
    if (reason instanceof ApiError && reason.status === 404) return emptyTrip;
    throw reason;
  }
}

/** Every text inside a (possibly nested) field error object. */
function errorTexts(value: unknown): string[] {
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return value.flatMap(errorTexts);
  if (typeof value === 'object' && value !== null)
    return Object.values(value).flatMap(errorTexts);
  return [];
}

function describeError(error: unknown) {
  if (!(error instanceof ApiError))
    return 'Something unexpected went wrong. Please try again.';
  if (error.kind === 'unreachable')
    return 'The backend is not reachable. Check that the Django server is running.';
  if (error.kind === 'unavailable')
    return 'The language model or planner is temporarily unavailable. Please try again in a moment.';
  if (error.status === 404)
    return 'This conversation no longer exists. Start a new conversation.';
  const details = errorTexts(error.fields).join(' ');
  return details ? `${error.message} ${details}` : error.message;
}

/** "2027-05-20 – 2027-05-24", or a note that the agent still needs dates. */
function formatWindow(value: TripState['departure']['value']) {
  if (!value) return 'Not set yet';
  return value.earliest === value.latest
    ? value.earliest
    : `${value.earliest} – ${value.latest}`;
}

type Start = { fresh: boolean };
/** The running request. */
type Pending = { text: string };

/** Suggestion chips shown in the chat. */
type SuggestionGroup = {
  question: string;
  options: string[];
};

const durationSuggestions: SuggestionGroup = {
  question: 'How long is your weekend in Barcelona?',
  options: ['2 days', '3 days', '4 days'],
};

const vibeSuggestions: SuggestionGroup = {
  question: 'What vibe do you want most?',
  options: [
    'Gaudí and architecture',
    'Food and tapas',
    'Beaches and waterfront',
    'Nightlife',
    'Museums and culture',
    'Day trip outside the city',
  ],
};

const demoDay = demoItinerary.days.at(-1);
const demoSummary =
  demoDay?.summary ??
  'Tell me where you want to go and what you enjoy, and I will build the days around it.';

export function ChatPage() {
  const inputId = useId();
  const list = useRef<HTMLDivElement>(null);
  const previousMessageCount = useRef(0);
  const [start, setStart] = useState<Start>({ fresh: false });
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [trip, setTrip] = useState<Trip>(emptyTrip);
  const [text, setText] = useState('');
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** Itinerary state – starts with demo data for visual design. */
  const [itinerary, setItinerary] = useState<Itinerary>(demoItinerary);
  /** Hover previews a stop; clicking keeps it selected. */
  const [hoveredStepId, setHoveredStepId] = useState<string | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(
    demoItinerary.days[0]?.steps[0]?.id ?? null,
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const [datesOpen, setDatesOpen] = useState(false);
  const [tripSaved, setTripSaved] = useState(false);

  // Open the conversation: reuse the remembered session or create a new one.
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    function show(id: string, history: ChatMessage[], loaded: Trip) {
      setMessages(history);
      setTrip(loaded);
      setSessionId(id);
    }

    async function open() {
      const stored = start.fresh ? '' : readSessionId();
      if (stored) {
        try {
          const [history, loaded] = await Promise.all([
            loadHistory(stored, signal),
            loadTrip(stored, signal),
          ]);
          show(stored, history, loaded);
          return;
        } catch (reason) {
          // A session that no longer exists is replaced by a fresh one.
          if (!(reason instanceof ApiError && reason.status === 404))
            throw reason;
        }
      }
      const created = await backend.createPlanningSession(
        sessionTitle(),
        signal,
      );
      storeSessionId(created.id);
      show(created.id, [], await loadTrip(created.id, signal));
    }

    open().catch((reason: unknown) => {
      if (!signal.aborted) setError(describeError(reason));
    });
    return () => controller.abort();
  }, [start]);

  // Keep the newest message in view, but leave the initial briefing at the top.
  useEffect(() => {
    const changed =
      messages.length !== previousMessageCount.current ||
      pending !== null ||
      error !== null;
    previousMessageCount.current = messages.length;
    if (!changed) return;
    const element = list.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages, pending, error]);

  function restart(fresh: boolean) {
    setSessionId(null);
    setError(null);
    if (fresh) {
      setMessages([]);
      setTrip(emptyTrip);
      setSelectedStepId(demoItinerary.days[0]?.steps[0]?.id ?? null);
      setTripSaved(false);
    }
    setStart({ fresh });
  }

  /** Shows the reply and syncs the trip state used by the dates summary. */
  function adopt(turn: ChatTurn) {
    setMessages((current) => [
      ...current,
      ...(turn.user_message ? [turn.user_message] : []),
      turn.reply,
    ]);
    setTrip(toTrip(turn));
  }

  async function submit(message: string) {
    if (!sessionId || pending !== null) return;
    setPending({ text: message });
    setText('');
    setError(null);
    try {
      adopt(await backend.sendMessage(sessionId, { text: message }));
    } catch (reason) {
      // The failed text goes back into the input so it can be sent again.
      setText(message);
      setError(describeError(reason));
    } finally {
      setPending(null);
    }
  }

  function send(event: FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (message) void submit(message);
  }

  function sendSuggestion(suggestion: string) {
    void submit(suggestion);
  }

  const handleStepHover = useCallback((id: string | null) => {
    setHoveredStepId(id);
  }, []);

  const handleStepClick = useCallback((id: string) => {
    setSelectedStepId(id);
    setHoveredStepId(null);
    const card = document.querySelector<HTMLElement>(
      `[data-step-id="${id}"]`,
    );
    card?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
  }, []);

  const handleToggleSaved = useCallback((stepId: string) => {
    setItinerary((previous) => ({
      ...previous,
      days: previous.days.map((day) => ({
        ...day,
        steps: day.steps.map((step) =>
          step.id === stepId ? { ...step, saved: !step.saved } : step,
        ),
      })),
    }));
  }, []);

  const handleSaveTrip = useCallback(() => {
    setTripSaved((saved) => !saved);
  }, []);

  async function share() {
    try {
      if (typeof navigator.share === 'function') {
        await navigator.share({
          title: 'Traveller itinerary',
          text: `Results for "${itinerary.title}"`,
          url: window.location.href,
        });
        return;
      }
      await navigator.clipboard?.writeText(window.location.href);
    } catch {
      // Sharing is a convenience; a cancelled or unavailable API is fine.
    }
  }

  const opening = sessionId === null && error === null;
  const busy = pending !== null;
  const activeStepId = hoveredStepId ?? selectedStepId;

  return (
    <div className="chat-page-new">
      <div className="chat-three-panel">
        {/* ─── LEFT: Chat panel ─── */}
        <section className="chat-panel" aria-labelledby="chat-heading">
          <div className="chat-panel-header">
            <button
              type="button"
              className="chat-icon-btn chat-menu-btn"
              aria-label="Open menu"
              aria-expanded={menuOpen}
              onClick={() => {
                setMenuOpen((open) => !open);
                setDatesOpen(false);
              }}
            >
              <Menu size={20} />
            </button>

            <h2 id="chat-heading" className="chat-panel-title">
              AI Assistant
            </h2>

            <div className="chat-header-actions">
              <button
                type="button"
                className="chat-new-btn"
                onClick={() => restart(true)}
                disabled={busy || opening}
                aria-label="New chat"
              >
                <Plus size={15} /> <span className="chat-new-label">New chat</span>
              </button>
              <button
                type="button"
                className="chat-icon-btn"
                onClick={() => void share()}
                aria-label="Share this itinerary"
                title="Share this itinerary"
              >
                <Share2 size={18} />
              </button>
            </div>

            {menuOpen && (
              <div className="chat-menu" role="menu" aria-label="Main menu">
                <a
                  href="/"
                  role="menuitem"
                  onClick={() => setMenuOpen(false)}
                >
                  Traveller home
                </a>
                <a
                  href="/status"
                  role="menuitem"
                  onClick={() => setMenuOpen(false)}
                >
                  System status
                </a>
              </div>
            )}
          </div>

          <button
            type="button"
            className="chat-dates-toggle"
            aria-expanded={datesOpen}
            onClick={() => {
              setDatesOpen((open) => !open);
              setMenuOpen(false);
            }}
          >
            <CalendarDays size={15} />
            <span>Dates &amp; travelers</span>
            <ChevronDown
              size={15}
              className={`chat-chevron${datesOpen ? ' is-open' : ''}`}
            />
          </button>

          {datesOpen && (
            <div className="chat-dates-panel">
              <div>
                <span>Route</span>
                <strong>
                  {trip.state.origin.value ?? 'Not set'} →{' '}
                  {trip.state.destination.value ?? 'Not set'}
                </strong>
              </div>
              <div>
                <span>Dates</span>
                <strong>{formatWindow(trip.state.departure.value)}</strong>
              </div>
              <div>
                <span>Travelers</span>
                <strong>{trip.state.travelers.value ?? 'Not set'}</strong>
              </div>
            </div>
          )}

          <div className="chat-messages" ref={list} tabIndex={0}>
            <div
              className="chat-thread"
              role="log"
              aria-live="polite"
              aria-label="Messages"
            >
              {opening && (
                <p className="system-meta">Opening conversation…</p>
              )}

              {messages.length === 0 && !opening && (
                <div className="chat-turn chat-briefing">
                  <p className="chat-day-label">
                    Day {demoDay?.dayNumber ?? 1}
                  </p>
                  <p className="chat-bubble chat-assistant">{demoSummary}</p>
                </div>
              )}

              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`chat-turn${
                    message.role === 'user' ? ' chat-turn-user' : ''
                  }`}
                >
                  {message.role === 'assistant' ? (
                    <>
                      <p className="chat-bubble chat-assistant">
                        {message.content}
                      </p>
                      {message.result && <Results result={message.result} />}
                    </>
                  ) : (
                    <p className="chat-bubble chat-user">{message.content}</p>
                  )}
                </div>
              ))}

              {pending !== null && (
                <div className="chat-turn">
                  <p className="chat-bubble chat-user">{pending.text}</p>
                  <p className="chat-bubble chat-assistant chat-thinking">
                    thinking…
                  </p>
                </div>
              )}
            </div>

            <div className="chat-suggestions" aria-label="Suggested replies">
              <SuggestionChips
                group={durationSuggestions}
                onSelect={sendSuggestion}
                disabled={busy || sessionId === null}
              />
              <SuggestionChips
                group={vibeSuggestions}
                onSelect={sendSuggestion}
                disabled={busy || sessionId === null}
              />
            </div>
          </div>

          {error && (
            <p className="system-error chat-error" role="alert">
              {error}
            </p>
          )}
          {sessionId === null && error && (
            <div className="system-actions chat-retry">
              <button
                className="button button-outline"
                type="button"
                onClick={() => restart(false)}
              >
                <RefreshCw size={15} /> Try again
              </button>
            </div>
          )}

          <form className="chat-input-bar" onSubmit={send}>
            <label htmlFor={inputId} className="visually-hidden">
              Message
            </label>
            <button
              type="button"
              className="chat-input-attach"
              aria-label="Add an attachment"
              title="Add an attachment"
            >
              <Plus size={18} />
            </button>
            <input
              id={inputId}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder='Ask anything or type "/" to see options'
              autoComplete="off"
              disabled={busy || sessionId === null}
            />
            <button
              type="submit"
              className="chat-input-send"
              disabled={busy || sessionId === null || text.trim() === ''}
              aria-label={pending !== null ? 'Sending…' : 'Send'}
            >
              {pending !== null ? (
                <Check size={18} />
              ) : (
                <ArrowUp size={18} />
              )}
            </button>
          </form>
        </section>

        {/* ─── CENTER: Itinerary panel ─── */}
        <ItineraryPanel
          itinerary={itinerary}
          activeStepId={activeStepId}
          onStepHover={handleStepHover}
          onStepClick={handleStepClick}
          onToggleSaved={handleToggleSaved}
        />

        {/* ─── RIGHT: Map panel ─── */}
        <MapPanel
          itinerary={itinerary}
          activeStepId={activeStepId}
          onStepHover={handleStepHover}
          onStepClick={handleStepClick}
          saved={tripSaved}
          onSaveTrip={handleSaveTrip}
        />
      </div>
    </div>
  );
}

function SuggestionChips({
  group,
  onSelect,
  disabled,
}: {
  group: SuggestionGroup;
  onSelect: (text: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="chat-chip-group">
      <p className="chat-chip-question">{group.question}</p>
      <div className="chat-chip-row">
        {group.options.map((option) => (
          <button
            key={option}
            type="button"
            className="chat-chip"
            onClick={() => onSelect(option)}
            disabled={disabled}
          >
            <Plus size={13} /> {option}
          </button>
        ))}
      </div>
    </div>
  );
}
