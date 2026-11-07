import { newIntent } from '../domain/travel';
import type { SearchResult, TravelIntent } from '../domain/travel';

export type JourneySort = 'fit' | 'price' | 'time';
export type JourneyMode = 'ai' | 'search';

export type Message = { prompt: string; reply: string };
export type Session = {
  intent: TravelIntent;
  revision: number;
  active: boolean;
  messages: Message[];
  selected: string[];
  sort: Record<JourneyMode, JourneySort>;
  result: SearchResult | null;
  error: { revision: number; message: string } | null;
  simulateError: boolean;
};

export const sessionKey = 'wohin.travel.v1';

export function initialSession(): Session {
  return {
    intent: newIntent(),
    revision: 0,
    active: false,
    messages: [],
    selected: [],
    result: null,
    error: null,
    simulateError: false,
    sort: { ai: 'fit', search: 'fit' },
  };
}

export type SessionAction =
  | {
      type: 'update';
      changes: Partial<TravelIntent>;
      message?: Message;
      simulateError?: boolean;
    }
  | { type: 'message'; message: Message }
  | { type: 'activate' }
  | { type: 'retry' }
  | { type: 'resolve'; result: SearchResult }
  | { type: 'reject'; revision: number; message: string }
  | { type: 'toggle'; id: string }
  | { type: 'clear' }
  | { type: 'sort'; mode: JourneyMode; sort: JourneySort };

export function sessionReducer(state: Session, action: SessionAction): Session {
  switch (action.type) {
    case 'update':
      return {
        ...state,
        intent: { ...state.intent, ...action.changes },
        active: true,
        revision: state.revision + 1,
        error: null,
        simulateError: Boolean(action.simulateError),
        messages: action.message
          ? [...state.messages, action.message]
          : state.messages,
      };
    case 'message':
      return { ...state, messages: [...state.messages, action.message] };
    case 'activate':
      return state.active ? state : { ...state, active: true };
    case 'retry':
      return {
        ...state,
        active: true,
        revision: state.revision + 1,
        error: null,
        simulateError: false,
      };
    case 'resolve':
      return action.result.revision === state.revision
        ? { ...state, result: action.result }
        : state;
    case 'reject':
      return action.revision === state.revision
        ? {
            ...state,
            error: { revision: action.revision, message: action.message },
          }
        : state;
    case 'toggle':
      return {
        ...state,
        selected: state.selected.includes(action.id)
          ? state.selected.filter((id) => id !== action.id)
          : [...state.selected, action.id],
      };
    case 'sort':
      return { ...state, sort: { ...state.sort, [action.mode]: action.sort } };
    case 'clear':
      return { ...state, selected: [] };
  }
}

export function readSession(): Session {
  try {
    const stored = sessionStorage.getItem(sessionKey);
    return stored
      ? { ...initialSession(), ...JSON.parse(stored) }
      : initialSession();
  } catch {
    return initialSession();
  }
}
