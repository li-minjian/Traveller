import { delay, http, HttpResponse } from 'msw';
import { API_BASE } from '../api/client';
import type {
  ChatInput, ChatMessage, ChatTurn, DateWindow, Field, Paginated, Place, PlanningSession,
  SearchResult, TripState, TripStateResponse,
} from '../api/client';
import { emptyTripState, requiredFields } from '../features/chat/tripDraft';
import { journey } from './journey';

export type MockScenario = 'success' | 'empty' | 'backend-error' | 'api-error';
type Session = {
  summary: PlanningSession;
  trip: TripState;
  messages: ChatMessage[];
};

const createdAt = '2026-11-18T12:00:00Z';
const demoDate = journey.legs[0].departure.slice(0, 10);
const places: Place[] = [
  { name: 'Berlin', country: 'Deutschland', aliases: ['ber'] },
  { name: 'Lissabon', country: 'Portugal', aliases: ['lisbon', 'lis'] },
];

function page<T>(results: T[]): Paginated<T> {
  return { count: results.length, next: null, previous: null, results };
}

function field<T>(value: T | null): Field<T> {
  return { value, provenance: value === null ? 'unknown' : 'confirmed' };
}

function windowValue(value: string | DateWindow | null): DateWindow | null {
  return typeof value === 'string' ? { earliest: value, latest: value } : value;
}

function tripResponse(state: TripState): TripStateResponse {
  return {
    trip_state: state,
    missing_fields: requiredFields.filter(
      (key) => state[key].value === null &&
        (key !== 'return' || state.trip_type.value !== 'one_way'),
    ),
  };
}

function error(status: number, code: string, message: string) {
  return HttpResponse.json({ error: { code, message } }, { status });
}

function uuid(sequence: number, suffix = 0) {
  const group = sequence.toString(16).padStart(8, '0');
  return `${group}-0000-4000-8000-${suffix.toString(16).padStart(12, '0')}`;
}

function resultFor(state: TripState, scenario: MockScenario): SearchResult {
  const outbound = state.departure.value;
  const budget = state.budget.value;
  const eligible = scenario !== 'empty' && state.trip_type.value === 'one_way' &&
    state.origin.value?.toLowerCase() === 'berlin' &&
    state.destination.value?.toLowerCase() === 'lissabon' &&
    outbound && outbound.earliest <= demoDate && demoDate <= outbound.latest;
  const aboveBudget = eligible && budget?.currency === 'EUR' &&
    budget.amount < journey.total_price.amount *
      (budget.basis === 'trip_total' ? state.travelers.value ?? 1 : 1);
  if (!eligible || aboveBudget) {
    return {
      status: 'no_results', journeys: [], review: {}, alternative: null,
      no_results: {
        reason: aboveBudget ? 'budget' : 'no_connection',
        direction: null,
        closest_journey: aboveBudget ? journey : null,
      },
    };
  }
  return {
    status: 'ok', journeys: [journey], no_results: null, alternative: null,
    review: { [journey.id]: { tags: ['recommended'], warnings: [] } },
  };
}

export function createMockHandlers({
  scenario = 'success',
  responseDelay = 0,
  storage,
}: {
  scenario?: MockScenario;
  responseDelay?: number;
  storage?: Storage;
} = {}) {
  const storageKey = `traveller.mock.${scenario}`;
  const sessions: Record<string, Session> = JSON.parse(storage?.getItem(storageKey) ?? '{}');
  const save = () => storage?.setItem(storageKey, JSON.stringify(sessions));
  const api = `*${API_BASE}`;
  const collection = `${api}/planning-sessions`;
  const sessionPath = `${collection}/:id`;
  const notFound = () => error(404, 'not_found', 'The requested resource was not found.');

  return [
    http.get(`${api}/health/`, () => HttpResponse.json({ status: 'ok', database: 'ok' })),
    http.get(`${api}/places/`, () => HttpResponse.json(page(places))),
    http.get(`${api}/reference-cases/`, () => HttpResponse.json(page([]))),
    http.post(`${collection}/`, async ({ request }) => {
      const { title } = await request.json() as Pick<PlanningSession, 'title'>;
      if (!title?.trim()) return error(400, 'validation_error', 'The input is invalid.');
      const summary = { id: uuid(Object.keys(sessions).length + 1), title, created_at: createdAt };
      sessions[summary.id] = { summary, trip: emptyTripState, messages: [] };
      save();
      return HttpResponse.json(summary, { status: 201 });
    }),
    http.get<{ id: string }>(`${sessionPath}/`, ({ params }) => {
      const session = sessions[params.id];
      return session ? HttpResponse.json(session.summary) : notFound();
    }),
    http.get<{ id: string }>(`${sessionPath}/trip-state/`, ({ params }) => {
      const session = sessions[params.id];
      return session ? HttpResponse.json(tripResponse(session.trip)) : notFound();
    }),
    http.get<{ id: string }>(`${sessionPath}/messages/`, ({ params }) => {
      const session = sessions[params.id];
      return session ? HttpResponse.json(page(session.messages)) : notFound();
    }),
    http.post<{ id: string }, ChatInput>(`${sessionPath}/messages/`, async ({ params, request }) => {
      const session = sessions[params.id];
      if (!session) return notFound();
      if (responseDelay) await delay(responseDelay);
      if (scenario === 'backend-error') {
        return error(503, 'service_unavailable', 'The language model is temporarily unavailable.');
      }
      const { text, fields = {} } = await request.json();
      const message = text?.trim();
      if (scenario === 'api-error' || (!message && Object.keys(fields).length === 0)) {
        return error(400, 'validation_error', 'The input is invalid.');
      }

      const state = { ...session.trip };
      // The only scripted natural-language input seeds the demo route.
      if (message?.toLowerCase() === 'berlin to lissabon') {
        state.origin = field('Berlin');
        state.destination = { value: 'Lissabon', provenance: 'inferred' };
        state.departure = field(windowValue(demoDate));
        state.return = emptyTripState.return;
        state.trip_type = field('one_way');
        state.travelers = field(1);
      }
      if (fields.origin !== undefined) state.origin = field(fields.origin);
      if (fields.destination !== undefined) state.destination = field(fields.destination);
      if (fields.departure !== undefined) state.departure = field(windowValue(fields.departure));
      if (fields.trip_type !== undefined) state.trip_type = field(fields.trip_type);
      if (fields.return !== undefined) state.return = field(windowValue(fields.return));
      if (fields.return) state.trip_type = field('round_trip');
      if (state.trip_type.value === 'one_way') state.return = emptyTripState.return;
      if (fields.travelers !== undefined) state.travelers = field(fields.travelers);
      if (fields.budget !== undefined) {
        state.budget = field(typeof fields.budget === 'number'
          ? { amount: fields.budget, currency: 'EUR', basis: 'per_person' }
          : fields.budget);
      }
      if (fields.max_stops !== undefined) state.max_stops = field(fields.max_stops);
      if (message?.toLowerCase() === 'yes' && state.destination.provenance === 'inferred') {
        state.destination = field(state.destination.value);
      }

      const response = tripResponse(state);
      const [missing] = response.missing_fields;
      const needsConfirmation = state.destination.provenance === 'inferred';
      const result = missing || needsConfirmation ? null : resultFor(state, scenario);
      const content = missing ? `Still needed: ${missing}.`
        : needsConfirmation ? 'Did you mean Lissabon? Reply “yes” to confirm.'
        : result?.status === 'ok' ? 'I found a sample flight.'
        : 'No flights match this demo search.';
      const makeMessage = (role: ChatMessage['role'], content: string, result: SearchResult | null): ChatMessage => {
        // Keep message IDs unique within and across mock sessions.
        const id = uuid(parseInt(session.summary.id.slice(0, 8), 16), session.messages.length + 1);
        const record = { id, role, content, created_at: createdAt, result };
        session.messages.push(record);
        return record;
      };

      const turn: ChatTurn = {
        ...response,
        user_message: message ? makeMessage('user', message, null) : null,
        reply: makeMessage('assistant', content, result),
      };
      session.trip = state;
      save();
      return HttpResponse.json(turn, { status: 201 });
    }),
    http.all(`${api}/*`, notFound),
  ];
}
