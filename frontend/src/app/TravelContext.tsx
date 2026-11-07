import { createContext, useContext, useEffect, useReducer } from 'react';
import type { Dispatch, ReactNode } from 'react';
import type { TravelIntent, TravelService } from '../domain/travel';
import { mockTravelService } from '../services/mockTravel';
import { readSession, sessionKey, sessionReducer } from './session';
import type { Session, SessionAction } from './session';

type Context = {
  session: Session;
  service: TravelService;
  dispatch: Dispatch<SessionAction>;
  submit: (text: string, context?: Partial<TravelIntent>) => boolean;
};
const TravelContext = createContext<Context | null>(null);

export function TravelProvider({
  children,
  service = mockTravelService,
}: {
  children: ReactNode;
  service?: TravelService;
}) {
  const [session, dispatch] = useReducer(
    sessionReducer,
    undefined,
    readSession,
  );
  const { active, intent, revision, simulateError, messages, selected, sort } =
    session;

  useEffect(() => {
    try {
      sessionStorage.setItem(
        sessionKey,
        JSON.stringify({ active, intent, revision, messages, selected, sort }),
      );
    } catch {
      // The current tab remains usable when storage is disabled.
    }
  }, [active, intent, revision, messages, selected, sort]);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    service
      .search({ intent, revision, simulateError, signal: controller.signal })
      .then(
        (result) => {
          if (!controller.signal.aborted) dispatch({ type: 'resolve', result });
        },
        (error: unknown) => {
          if (!controller.signal.aborted)
            dispatch({
              type: 'reject',
              revision,
              message:
                error instanceof Error
                  ? error.message
                  : 'The search did not finish.',
            });
        },
      );
    return () => controller.abort();
  }, [active, intent, revision, service, simulateError]);

  function submit(text: string, context?: Partial<TravelIntent>) {
    const prompt = text.trim();
    if (!prompt) return false;
    const parsed = service.interpret(prompt, intent);
    const changes = { ...parsed.changes, ...context };
    const understood = parsed.supported || Boolean(context);
    const message = {
      prompt,
      reply: understood
        ? 'I’ll look through the sample catalogue using your trip criteria. Review the chips to confirm or edit anything I inferred.'
        : 'This demo recognizes sample destinations, dates, budgets and simple preferences like “no flights”. Your criteria are unchanged. You can also edit them directly.',
    };
    if (understood || !active)
      dispatch({
        type: 'update',
        changes,
        message,
        simulateError: parsed.simulateError,
      });
    else dispatch({ type: 'message', message });
    return true;
  }

  return (
    <TravelContext.Provider value={{ session, service, dispatch, submit }}>
      {children}
    </TravelContext.Provider>
  );
}

export function useTravel() {
  const context = useContext(TravelContext);
  if (!context) throw new Error('TravelProvider is required.');
  return context;
}
