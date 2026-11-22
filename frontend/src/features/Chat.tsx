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
  TripFieldsInput,
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
 *
 * The session, message history and trip state come from the same `/api/v1`
 * endpoints the status page uses. The chat itself is text-only here; the
 * compact dates/travellers form sends structured `fields` through the message
 * endpoint once the user changes something.
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

type Start = { fresh: boolean };
/** The running chat request. */
type Pending = { text: string };

type DetailsForm = {
  departure: string;
  return: string;
  travelers: string;
  oneWay: boolean;
};

const emptyDetails: DetailsForm = {
  departure: '',
  return: '',
  travelers: '',
  oneWay: false,
};

function detailsFromState(state: TripState): DetailsForm {
  return {
    departure: state.departure.value?.earliest ?? '',
    return: state.return.value?.earliest ?? '',
    travelers: state.travelers.value?.toString() ?? '',
    oneWay: state.trip_type.value === 'one_way',
  };
}

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
  const [details, setDetails] = useState<DetailsForm>(emptyDetails);
  const [detailsBusy, setDetailsBusy] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);

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

  // The compact details form mirrors the server-side trip state.
  useEffect(() => {
    setDetails(detailsFromState(trip.state));
  }, [trip.state]);

  function restart(fresh: boolean) {
    setSessionId(null);
    setError(null);
    setDetailsError(null);
    setDatesOpen(false);
    if (fresh) {
      setMessages([]);
      setTrip(emptyTrip);
      setSelectedStepId(demoItinerary.days[0]?.steps[0]?.id ?? null);
      setTripSaved(false);
      setDetails(emptyDetails);
    }
    setStart({ fresh });
  }

  /** Shows the reply and syncs the trip state used by the details form. */
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

  /**
   * Sends only the changed dates/travellers as structured fields through the
   * same message endpoint. The agent then answers and updates the trip state.
   */
  async function submitDetails(event: FormEvent) {
    event.preventDefault();
    if (!sessionId || detailsBusy) return;

    const current = detailsFromState(trip.state);
    const fields: TripFieldsInput = {};
    if (details.departure !== current.departure)
      fields.departure = details.departure || null;

    if (details.oneWay !== current.oneWay)
      fields.trip_type = details.oneWay ? 'one_way' : 'round_trip';

    if (details.oneWay) {
      if (current.return) fields.return = null;
    } else if (details.return !== current.return) {
      fields.return = details.return || null;
    }

    if (details.travelers !== current.travelers)
      fields.travelers = details.travelers.trim()
        ? Number(details.travelers)
        : null;

    if (Object.keys(fields).length === 0) {
      setDatesOpen(false);
      return;
    }

    setDetailsBusy(true);
    setDetailsError(null);
    try {
      adopt(await backend.sendMessage(sessionId, { fields }));
      setDatesOpen(false);
    } catch (reason) {
      setDetailsError(describeError(reason));
    } finally {
      setDetailsBusy(false);
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
    const card = document.querySelector<HTMLElement>(`[data-step-id="${id}"]`);
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
  const busy = pending !== null || detailsBusy;
  const activeStepId = hoveredStepId ?? selectedStepId;

  return (
    <div className="h-dvh w-full overflow-hidden bg-surface font-sans text-ink max-[1000px]:h-auto max-[1000px]:min-h-dvh max-[1000px]:overflow-visible">
      <div className="grid h-full min-h-0 grid-cols-[20vw_min(40vw,1024px)_minmax(0,1fr)] max-[1920px]:grid-cols-[20vw_min(40vw,768px)_minmax(0,1fr)] max-[1000px]:flex max-[1000px]:h-auto max-[1000px]:min-h-dvh max-[1000px]:flex-col">
        {/* ─── LEFT: chat panel ─── */}
        <section
          className="relative flex h-full min-h-0 min-w-0 flex-col border-r border-line bg-surface max-[1000px]:h-[84dvh] max-[1000px]:min-h-[540px] max-[1000px]:border-b max-[1000px]:border-r-0"
          aria-labelledby="chat-heading"
        >
          <div className="relative flex min-h-[58px] items-center gap-2 border-b border-line px-3.5 py-3">
            <button
              type="button"
              className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-lg text-[#1b2f2a] hover:bg-mist"
              aria-label="Open menu"
              aria-expanded={menuOpen}
              onClick={() => {
                setMenuOpen((open) => !open);
                setDatesOpen(false);
              }}
            >
              <Menu size={20} />
            </button>

            <h2
              id="chat-heading"
              className="min-w-0 flex-1 truncate font-sans text-base font-bold leading-tight tracking-[-0.015em] text-forest-deep"
            >
              AI Assistant
            </h2>

            <div className="flex items-center gap-0.5">
              <button
                type="button"
                className="inline-flex min-h-8 items-center gap-1.5 rounded-lg px-1.5 py-1.5 text-[0.8rem] font-semibold whitespace-nowrap text-forest-deep hover:bg-mist disabled:opacity-50 max-[1400px]:w-[34px] max-[1400px]:justify-center max-[1400px]:p-1.5"
                onClick={() => restart(true)}
                disabled={busy || opening}
                aria-label="New chat"
              >
                <Plus size={15} />
                <span className="max-[1400px]:hidden">New chat</span>
              </button>
              <button
                type="button"
                className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-lg text-[#1b2f2a] hover:bg-mist"
                onClick={() => void share()}
                aria-label="Share this itinerary"
                title="Share this itinerary"
              >
                <Share2 size={18} />
              </button>
            </div>

            {menuOpen && (
              <div
                className="absolute top-[52px] left-3 z-30 grid min-w-[178px] gap-0 rounded-[10px] border border-line bg-surface p-1.5 shadow-xl"
                role="menu"
                aria-label="Main menu"
              >
                <a
                  href="/"
                  role="menuitem"
                  className="rounded-md px-2.5 py-2 text-[0.8rem] font-semibold text-forest-deep hover:bg-forest-soft"
                  onClick={() => setMenuOpen(false)}
                >
                  Traveller home
                </a>
                <a
                  href="/status"
                  role="menuitem"
                  className="rounded-md px-2.5 py-2 text-[0.8rem] font-semibold text-forest-deep hover:bg-forest-soft"
                  onClick={() => setMenuOpen(false)}
                >
                  System status
                </a>
              </div>
            )}
          </div>

          <button
            type="button"
            className="flex min-h-[46px] w-full shrink-0 items-center gap-2 border-b border-line bg-surface px-4 py-2.5 text-left text-[0.78rem] font-semibold text-forest-deep hover:bg-[#f7f8f5]"
            aria-expanded={datesOpen}
            onClick={() => {
              setDatesOpen((open) => !open);
              setMenuOpen(false);
              setDetailsError(null);
            }}
          >
            <CalendarDays size={15} />
            <span>Dates &amp; travelers</span>
            <ChevronDown
              size={15}
              className={`ml-0.5 transition-transform ${datesOpen ? 'rotate-180' : ''}`}
            />
          </button>

          {datesOpen && (
            <form
              className="grid shrink-0 gap-2 border-b border-line bg-[#fafbf8] px-4 pt-2.5 pb-3 text-[0.74rem]"
              onSubmit={submitDetails}
            >
              <div className="grid gap-1">
                <label
                  htmlFor="chat-departure"
                  className="font-semibold text-[#64736d]"
                >
                  Departure
                </label>
                <input
                  id="chat-departure"
                  type="date"
                  value={details.departure}
                  onChange={(event) =>
                    setDetails((current) => ({
                      ...current,
                      departure: event.target.value,
                    }))
                  }
                  disabled={detailsBusy}
                  className="min-h-8 min-w-0 rounded-md border border-line bg-white px-2 py-1 text-[0.76rem] text-forest-deep outline-none focus:border-forest"
                />
              </div>
              <div className="grid gap-1">
                <label
                  htmlFor="chat-return"
                  className="font-semibold text-[#64736d]"
                >
                  Return
                </label>
                <input
                  id="chat-return"
                  type="date"
                  value={details.return}
                  onChange={(event) =>
                    setDetails((current) => ({
                      ...current,
                      return: event.target.value,
                    }))
                  }
                  disabled={detailsBusy || details.oneWay}
                  className="min-h-8 min-w-0 rounded-md border border-line bg-white px-2 py-1 text-[0.76rem] text-forest-deep outline-none focus:border-forest disabled:bg-mist disabled:opacity-60"
                />
              </div>
              <div className="flex items-end gap-2">
                <div className="grid flex-1 gap-1">
                  <label
                    htmlFor="chat-travelers"
                    className="font-semibold text-[#64736d]"
                  >
                    Travelers
                  </label>
                  <input
                    id="chat-travelers"
                    type="number"
                    min={1}
                    inputMode="numeric"
                    value={details.travelers}
                    onChange={(event) =>
                      setDetails((current) => ({
                        ...current,
                        travelers: event.target.value,
                      }))
                    }
                    disabled={detailsBusy}
                    className="min-h-8 min-w-0 rounded-md border border-line bg-white px-2 py-1 text-[0.76rem] text-forest-deep outline-none focus:border-forest"
                  />
                </div>
                <label className="flex min-h-8 items-center gap-1.5 pb-1 font-medium text-[#1d3a34]">
                  <input
                    type="checkbox"
                    checked={details.oneWay}
                    onChange={(event) =>
                      setDetails((current) => ({
                        ...current,
                        oneWay: event.target.checked,
                      }))
                    }
                    disabled={detailsBusy}
                    className="size-3.5 accent-forest"
                  />
                  One-way
                </label>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="submit"
                  disabled={detailsBusy || sessionId === null}
                  className="inline-flex min-h-8 items-center gap-1.5 rounded-full bg-forest px-3.5 py-1.5 text-[0.74rem] font-semibold text-white hover:bg-[#15543e] disabled:opacity-50"
                >
                  {detailsBusy ? (
                    <>
                      <RefreshCw size={13} className="animate-spin" /> Updating…
                    </>
                  ) : (
                    <>
                      <Check size={13} /> Update trip
                    </>
                  )}
                </button>
                {detailsError && (
                  <p
                    className="min-w-0 text-[0.7rem] leading-snug text-[#7a2e1c]"
                    role="alert"
                  >
                    {detailsError}
                  </p>
                )}
              </div>
            </form>
          )}

          <div
            className="min-h-0 flex-1 overflow-y-auto bg-surface [scrollbar-width:thin]"
            ref={list}
            tabIndex={0}
          >
            <div
              className="flex flex-col gap-3.5 px-4 pt-[18px] pb-3.5"
              role="log"
              aria-live="polite"
              aria-label="Messages"
            >
              {opening && (
                <p className="text-[0.78rem] text-muted">
                  Opening conversation…
                </p>
              )}

              {messages.length === 0 && !opening && (
                <div className="flex min-w-0 flex-col gap-1.5">
                  <p className="mb-0.5 font-sans text-[0.86rem] font-bold leading-tight text-forest-deep">
                    Day {demoDay?.dayNumber ?? 1}
                  </p>
                  <p className="max-w-full text-[0.9rem] leading-relaxed [overflow-wrap:anywhere] whitespace-pre-wrap text-[#172f2b]">
                    {demoSummary}
                  </p>
                </div>
              )}

              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex min-w-0 flex-col gap-1.5 ${
                    message.role === 'user' ? 'items-end' : ''
                  }`}
                >
                  {message.role === 'assistant' ? (
                    <>
                      <p className="max-w-full text-[0.9rem] leading-relaxed [overflow-wrap:anywhere] whitespace-pre-wrap text-[#172f2b]">
                        {message.content}
                      </p>
                      {message.result && <Results result={message.result} />}
                    </>
                  ) : (
                    <p className="max-w-[90%] self-end rounded-[14px_14px_4px_14px] bg-forest px-3 py-2 text-[0.82rem] leading-snug text-white">
                      {message.content}
                    </p>
                  )}
                </div>
              ))}

              {pending !== null && (
                <div className="flex flex-col gap-1.5">
                  <p className="max-w-[90%] self-end rounded-[14px_14px_4px_14px] bg-forest px-3 py-2 text-[0.82rem] leading-snug text-white">
                    {pending.text}
                  </p>
                  <p className="text-[0.9rem] italic text-[#6c7a74]">
                    thinking…
                  </p>
                </div>
              )}
            </div>

            <div
              className="flex flex-col gap-3.5 border-t border-line bg-surface px-4 pt-3.5 pb-[18px]"
              aria-label="Suggested replies"
            >
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
            <p
              className="mx-3 mb-2 shrink-0 rounded-lg border border-[#e1baab] bg-[#fdf4f1] px-3 py-2.5 text-[0.82rem] text-[#7a2e1c]"
              role="alert"
            >
              {error}
            </p>
          )}
          {sessionId === null && error && (
            <div className="mx-4 mb-2 flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2">
              <button
                className="inline-flex min-h-[42px] items-center justify-center gap-2 rounded-md border border-[#c9d1d1] bg-surface px-3.5 py-2.5 text-[0.79rem] font-bold text-ink hover:border-teal hover:bg-tint"
                type="button"
                onClick={() => restart(false)}
              >
                <RefreshCw size={15} /> Try again
              </button>
            </div>
          )}

          <form
            className="mx-3.5 mt-2 mb-3.5 flex shrink-0 items-center gap-1.5 rounded-2xl border-[1.5px] border-[#1e6b49] bg-white p-2 transition focus-within:border-forest focus-within:ring-2 focus-within:ring-forest/10"
            onSubmit={send}
          >
            <label htmlFor={inputId} className="sr-only">
              Message
            </label>
            <button
              type="button"
              className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-full bg-forest text-white hover:bg-[#15543e]"
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
              className="h-[34px] min-w-0 flex-1 border-0 bg-transparent px-0.5 text-[0.8rem] text-forest-deep outline-none placeholder:text-[#7a8781] disabled:opacity-60"
            />
            <button
              type="submit"
              className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-full bg-[#c8cdc7] text-white disabled:opacity-100 enabled:bg-forest enabled:hover:bg-[#15543e]"
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

        {/* ─── CENTER: itinerary panel ─── */}
        <ItineraryPanel
          itinerary={itinerary}
          activeStepId={activeStepId}
          onStepHover={handleStepHover}
          onStepClick={handleStepClick}
          onToggleSaved={handleToggleSaved}
        />

        {/* ─── RIGHT: map panel ─── */}
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
    <div className="flex flex-col gap-1.5">
      <p className="m-0 font-sans text-[0.82rem] font-bold leading-snug text-forest-deep">
        {group.question}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {group.options.map((option) => (
          <button
            key={option}
            type="button"
            className="inline-flex min-h-[34px] items-center gap-1 whitespace-nowrap rounded-full border border-[#b9c6bd] bg-white px-3 py-1.5 text-[0.79rem] font-medium text-[#173b31] transition hover:border-[#1d6a49] hover:bg-forest-soft disabled:opacity-50"
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
