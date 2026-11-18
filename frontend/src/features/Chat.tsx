import { Plane, Plus, RefreshCw, Send } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError, backend, nestedFieldErrors } from '../api/client';
import type {
  ChatMessage,
  ChatTurn,
  FieldErrors,
  Place,
  TripState,
  TripStateResponse,
} from '../api/client';
import { Eyebrow } from '../components/ui';
import { Results } from './chat/Results';
import { TripForm } from './chat/TripForm';
import {
  changedFields,
  draftErrors,
  draftFromState,
  emptyTripState,
  fieldKeys,
  mergeDraft,
  requiredFields,
} from './chat/tripDraft';
import type { FieldKey, TripDraft } from './chat/tripDraft';

/**
 * Planning workspace: the chat with the planning agent on the left, the trip
 * data as an editable form on the right. One planning session per
 * conversation; whatever the form leaves open, the agent asks for.
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
    // Without the trip state the form starts empty and fills with the
    // first turn; a missing session shows up when the history is loaded.
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
/** The running request: a chat message, or form fields (`text: null`). */
type Pending = { text: string | null };

export function ChatPage() {
  const inputId = useId();
  const list = useRef<HTMLDivElement>(null);
  const [start, setStart] = useState<Start>({ fresh: false });
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [trip, setTrip] = useState<Trip>(emptyTrip);
  /** Input values of the trip form, including edits not applied yet. */
  const [draft, setDraft] = useState<TripDraft>(() =>
    draftFromState(emptyTripState),
  );
  const [text, setText] = useState('');
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  /** Cities for the From and To suggestions; `null` until loaded. */
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [placesUnavailable, setPlacesUnavailable] = useState(false);

  const base = useMemo(() => draftFromState(trip.state), [trip.state]);

  // Open the conversation: reuse the remembered session or create a new one.
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    function show(id: string, history: ChatMessage[], loaded: Trip) {
      setMessages(history);
      setTrip(loaded);
      setDraft(draftFromState(loaded.state));
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

  // Load the city list once. Without it (e.g. 503 while the journey planner
  // is down) From and To stay plain text inputs.
  useEffect(() => {
    const controller = new AbortController();
    backend
      .listPlaces(controller.signal)
      .then((page) => {
        if (page.results.length > 0) setPlaces(page.results);
        else setPlacesUnavailable(true);
      })
      .catch(() => {
        if (!controller.signal.aborted) setPlacesUnavailable(true);
      });
    return () => controller.abort();
  }, []);

  // Keep the newest message in view.
  useEffect(() => {
    const element = list.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages, pending, error]);

  function restart(fresh: boolean) {
    setSessionId(null);
    setError(null);
    if (fresh) {
      setMessages([]);
      setTrip(emptyTrip);
      setDraft(draftFromState(emptyTripState));
      setFormError(null);
      setFieldErrors({});
    }
    setStart({ fresh });
  }

  /**
   * Shows the reply and syncs the form with the new trip state. Fields the
   * user edited and has not applied keep their local value; `sent` is the
   * draft this turn applied.
   */
  function adopt(turn: ChatTurn, sent: TripDraft | null) {
    const next = toTrip(turn);
    setMessages((current) => [
      ...current,
      ...(turn.user_message ? [turn.user_message] : []),
      turn.reply,
    ]);
    setTrip(next);
    setDraft((current) =>
      mergeDraft(current, base, draftFromState(next.state), sent),
    );
  }

  const formProblem =
    'Some trip details on the right cannot be used yet. Please check the marked fields.';

  /**
   * One turn: the chat text (if any) together with every form field the user
   * changed and has not applied yet. The agent then knows the form values
   * before it reads the message, so it neither ignores them nor asks for them
   * again. Nothing is sent while the form holds values the server would
   * reject, so a message is never answered without the user's form input.
   */
  async function submit(message: string | null) {
    if (!sessionId || pending !== null) return;
    const fields = changedFields(draft, base);
    const hasFields = Object.keys(fields).length > 0;
    if (message === null && !hasFields) return;

    const local = draftErrors(draft);
    if (hasFields && Object.keys(local).length > 0) {
      setFieldErrors(local);
      setFormError(formProblem);
      if (message !== null) setError(formProblem);
      return;
    }

    setPending({ text: message });
    if (message !== null) setText('');
    setError(null);
    setFormError(null);
    setFieldErrors({});
    try {
      const input = {
        ...(message !== null ? { text: message } : {}),
        ...(hasFields ? { fields } : {}),
      };
      adopt(await backend.sendMessage(sessionId, input), hasFields ? draft : null);
    } catch (reason) {
      // The failed text goes back into the input so it can be sent again.
      if (message !== null) setText(message);
      const errors =
        reason instanceof ApiError ? nestedFieldErrors(reason, 'fields') : {};
      const known = Object.keys(errors).some((key) =>
        (fieldKeys as string[]).includes(key),
      );
      if (known) {
        setFieldErrors(errors);
        setFormError(formProblem);
        if (message !== null) setError(formProblem);
      } else if (message !== null) {
        setError(describeError(reason));
      } else {
        setFormError(describeError(reason));
      }
    } finally {
      setPending(null);
    }
  }

  function send(event: FormEvent) {
    event.preventDefault();
    const message = text.trim();
    if (message) void submit(message);
  }

  /** Sends the changed form fields on their own; the agent then replies. */
  function apply() {
    void submit(null);
  }

  function edit<K extends FieldKey>(key: K, value: TripDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setFieldErrors((current) => {
      if (!(key in current)) return current;
      const rest = { ...current };
      delete rest[key];
      return rest;
    });
  }

  function discard() {
    setDraft(base);
    setFormError(null);
    setFieldErrors({});
  }

  const opening = sessionId === null && error === null;
  const busy = pending !== null;

  return (
    <div className="page chat-page">
      <header className="system-intro">
        <Eyebrow>
          <Plane size={14} /> Flight planner
        </Eyebrow>
        <h1>Plan your trip</h1>
        <p>
          Describe your trip in the chat or fill in the details yourself.
          Whatever is still open, the agent asks for.
        </p>
      </header>

      <div className="chat-layout">
        <section
          className="section-card chat-card"
          aria-labelledby="chat-heading"
        >
          <div className="chat-head">
            <h2 id="chat-heading">Conversation</h2>
            <button
              className="button button-outline"
              type="button"
              onClick={() => restart(true)}
              disabled={busy || opening}
            >
              <Plus size={15} /> New conversation
            </button>
          </div>

          <div
            className="chat-messages"
            ref={list}
            role="log"
            aria-live="polite"
            aria-label="Messages"
            tabIndex={0}
          >
            <p className="chat-bubble chat-assistant chat-hint">
              Tell me where you want to go, e.g. »Ich will mit 2 Leuten vom 20.
              bis 27. Mai von Berlin nach Lissabon fliegen, maximal 300 € pro
              Person«
            </p>
            {messages.map((message) => (
              <Message key={message.id} message={message} />
            ))}
            {pending !== null && (
              <>
                {pending.text !== null && (
                  <p className="chat-bubble chat-user">{pending.text}</p>
                )}
                <p className="chat-bubble chat-assistant chat-thinking">
                  thinking…
                </p>
              </>
            )}
            {opening && <p className="system-meta">Opening conversation…</p>}
          </div>

          {error && (
            <p className="system-error" role="alert">
              {error}
            </p>
          )}
          {sessionId === null && error && (
            <div className="system-actions">
              <button
                className="button button-outline"
                type="button"
                onClick={() => restart(false)}
              >
                <RefreshCw size={15} /> Try again
              </button>
            </div>
          )}

          <form className="system-form chat-form" onSubmit={send}>
            <label htmlFor={inputId}>
              Message
              <input
                id={inputId}
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder="Your travel request"
                autoComplete="off"
                disabled={busy || sessionId === null}
              />
            </label>
            <button
              className="button button-primary"
              type="submit"
              disabled={busy || sessionId === null || text.trim() === ''}
            >
              <Send size={15} /> {pending?.text != null ? 'Sending…' : 'Send'}
            </button>
          </form>
        </section>

        <TripForm
          state={trip.state}
          missingFields={trip.missingFields}
          draft={draft}
          base={base}
          errors={fieldErrors}
          error={formError}
          places={places}
          placesUnavailable={placesUnavailable}
          disabled={sessionId === null}
          busy={busy}
          applying={pending !== null && pending.text === null}
          onEdit={edit}
          onApply={apply}
          onDiscard={discard}
        />
      </div>
    </div>
  );
}

function Message({ message }: { message: ChatMessage }) {
  return (
    <>
      <p className={`chat-bubble chat-${message.role}`}>{message.content}</p>
      {message.result && <Results result={message.result} />}
    </>
  );
}
