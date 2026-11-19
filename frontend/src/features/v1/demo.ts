import { journey } from '../../mocks/journey';

export type TripContext = {
  origin: string;
  destination: string;
  date: string;
  travelers: number;
};

type Message = { role: 'user' | 'assistant'; text: string };
export type Workspace = {
  trip: TripContext;
  messages: Message[];
  pending: string;
  confirming: boolean;
  outcome: 'idle' | 'result' | 'empty' | 'error';
};

export const exampleRequest = 'Berlin to Lisbon';
export const exampleLeg = journey.legs[0];

const exampleTrip: TripContext = {
  origin: exampleLeg.origin,
  destination: 'Lisbon',
  date: exampleLeg.departure.slice(0, 10),
  travelers: 1,
};

export function displayDate(date: string) {
  if (!date) return 'Not set';
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeZone: 'UTC',
  }).format(new Date(date));
}

export function newWorkspace(): Workspace {
  return {
    trip: { origin: '', destination: '', date: '', travelers: 1 },
    messages: [],
    pending: '',
    confirming: false,
    outcome: 'idle',
  };
}

export function queueMessage(workspace: Workspace, text: string): Workspace {
  const message = text.trim();
  if (!message || workspace.pending) return workspace;
  return {
    ...workspace,
    messages: [...workspace.messages, { role: 'user', text: message }],
    pending: message,
    outcome: 'idle',
  };
}

export function reply(workspace: Workspace, scenario: string | null): Workspace {
  if (!workspace.pending) return workspace;
  const next: Workspace = { ...workspace, pending: '', confirming: false };
  let text: string;

  if (workspace.confirming && /^(yes|ja|correct|yep)[.!]?$/i.test(workspace.pending)) {
    if (scenario === 'api-error' || scenario === 'backend-error') {
      return { ...next, outcome: 'error', confirming: true };
    }
    if (scenario === 'empty') return { ...next, outcome: 'empty' };
    next.outcome = 'result';
    text = `Perfect. Here is one example flight for Berlin to Lisbon on ${displayDate(exampleTrip.date)}.`;
  } else if (/\bberlin\b/i.test(workspace.pending) && /\b(lisbon|lissabon)\b/i.test(workspace.pending)) {
    next.trip = exampleTrip;
    next.confirming = true;
    text = 'I have Berlin to Lisbon. Is that correct? Reply “yes” to see the sample flight.';
  } else {
    text = 'This demo uses scripted replies. Send “Berlin to Lisbon” and then “yes” to see the sample flight.';
  }

  return { ...next, messages: [...workspace.messages, { role: 'assistant', text }] };
}

export function applyTrip(workspace: Workspace, trip: TripContext): Workspace {
  return {
    ...workspace,
    trip,
    confirming: false,
    outcome: 'idle',
    messages: [
      ...workspace.messages,
      { role: 'assistant', text: 'Travel details updated for this demo journey.' },
    ],
  };
}
