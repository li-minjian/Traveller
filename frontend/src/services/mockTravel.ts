import {
  addDays,
  budgetLabel,
  dateSpan,
  field,
  modeNames,
  modes,
} from '../domain/travel';
import type {
  BusinessTrip,
  Cost,
  DecisionSignal,
  IntentInterpretation,
  TravelIntent,
  TravelOpportunity,
  TravelService,
} from '../domain/travel';
import { destinations, journeys } from '../mocks/fixtures';
import type { JourneyFixture } from '../mocks/fixtures';

const normalize = (value: string) => value.toLocaleLowerCase().trim();
const same = (first: string, second: string) =>
  normalize(first) === normalize(second);
const includesWord = (text: string, word: string) => {
  const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(?<![\\p{L}])${escaped}(?![\\p{L}])`, 'iu').test(text);
};

function destinationFor(query: string) {
  return destinations.find((destination) =>
    [destination.id, destination.name, ...destination.aliases].some((value) =>
      same(value, query),
    ),
  );
}

export function interpretPrompt(
  prompt: string,
  intent: TravelIntent,
): IntentInterpretation {
  const changes: Partial<TravelIntent> = {};
  const originPattern =
    /\b(?:from|ab|von)\s+(Berlin|London|Edinburgh|Munich|München|Dresden|Copenhagen)\b/i;
  const origin = prompt.match(originPattern)?.[1];
  if (origin)
    changes.origin = field(
      same(origin, 'München') ? 'Munich' : origin,
      'inferred',
    );
  const destinationText = prompt.replace(originPattern, '');
  const destination = destinations.find((item) =>
    item.aliases.some((alias) => includesWord(destinationText, alias)),
  );
  if (destination) changes.destination = field(destination.name, 'inferred');

  const price = prompt.match(/(?:€\s*)([\d.,]+)|([\d.,]+)\s*(?:€|EUR\b)/i);
  const amount = price
    ? Number(
        (price[1] || price[2])
          .replace(/(\.|,)(?=\d{3}\b)/g, '')
          .replace(',', '.'),
      )
    : 0;
  if (amount > 0 && Number.isFinite(amount)) {
    const strict = /\b(max|under|within|below|up to|höchstens|bis)\b/i.test(
      prompt,
    );
    const flexible = /\b(around|roughly|about|ca)\b/i.test(prompt);
    changes.budget = field(
      {
        amount,
        currency: 'EUR',
        hard: strict || (!flexible && Boolean(intent.budget.value?.hard)),
      },
      'inferred',
    );
  }

  const noFlight =
    /\b(no flights?|without flights?|no flying|keine flüge|ohne flug)\b/i.test(
      prompt,
    );
  const rail = /\b(train|rail|sleeper|bahn|zug)\b/i.test(prompt);
  if (noFlight) {
    const allowed = intent.transport.value?.hard
      ? intent.transport.value.modes
      : modes;
    changes.transport = field(
      { modes: allowed.filter((mode) => mode !== 'flight'), hard: true },
      'inferred',
    );
  } else if (rail) {
    const hard = /\b(only|nur)\b/i.test(prompt);
    if (hard || !intent.transport.value?.hard)
      changes.transport = field({ modes: ['rail'], hard }, 'inferred');
  }

  const dates = prompt.match(/\b\d{4}-\d{2}-\d{2}\b/g)?.filter((value) => {
    const time = Date.parse(value);
    return (
      Number.isFinite(time) &&
      new Date(time).toISOString().slice(0, 10) === value
    );
  });
  const flex = prompt.match(
    /(?:±|\+\/-|flexible (?:by )?)(\d+)\s*(?:days|tage)/i,
  );
  const season = prompt.match(
    /\b(november|october|autumn|winter|spring|summer)\b/i,
  )?.[0];
  if (dates?.length || flex || season) {
    const previous = intent.dates.value;
    const [start = '', end = ''] = dates ?? [];
    changes.dates = field(
      {
        start: dates?.length ? start : season ? '' : (previous?.start ?? ''),
        end: dates?.length
          ? end && end >= start
            ? end
            : ''
          : season
            ? ''
            : (previous?.end ?? ''),
        flexibility: flex
          ? Math.min(14, Number(flex[1]))
          : (previous?.flexibility ?? 0),
        season: dates?.length
          ? ''
          : season
            ? season[0].toUpperCase() + season.slice(1).toLowerCase()
            : (previous?.season ?? ''),
      },
      flex || season ? 'flexible' : 'inferred',
    );
  }

  const days = prompt.match(/(?:\d+\s*[–-]\s*)?(\d+)\s*(?:days?|tage)\b/i);
  if (days && !flex)
    changes.duration = field(
      Math.min(30, Math.max(1, Number(days[1]))),
      'inferred',
    );
  if (/\bweekend\b/i.test(prompt)) changes.duration = field(2, 'flexible');
  const travelers = prompt.match(
    /\b(\d+)\s*(?:travel[l]?ers?|people|personen)\b/i,
  );
  if (travelers)
    changes.travelers = field(
      Math.min(12, Math.max(1, Number(travelers[1]))),
      'inferred',
    );
  const interests = [
    [/\b(nature|natur|mountains?|coastal|coast)\b/i, 'Nature'],
    [/\b(quiet|seclusion|ruhig)\b/i, 'Quiet'],
    [/\b(warm|warmer|warmth)\b/i, 'Warm'],
    [/\b(city|culture|stadt)\b/i, 'City'],
    [/\b(food|culinary)\b/i, 'Food'],
  ] as const;
  const matched = interests
    .filter(([pattern]) => pattern.test(prompt))
    .map(([, value]) => value);
  if (matched.length)
    changes.interests = field(
      [...new Set([...matched, ...(intent.interests.value ?? [])])],
      'inferred',
    );
  const accommodation = prompt.match(
    /\b(cabin|guesthouse|hotel|lodge)\b/i,
  )?.[0];
  if (accommodation) changes.accommodation = field(accommodation, 'inferred');

  if (/\b(business trip|dienstreise|conference|meeting)\b/i.test(prompt)) {
    const meetingTime = prompt.match(/\b([01]\d|2[0-3]):[0-5]\d\b/)?.[0] ?? '';
    const previous = intent.business.value;
    const business: BusinessTrip = {
      purpose: previous?.purpose || 'Meeting',
      meetingDate: dates?.[0] ?? previous?.meetingDate ?? '',
      meetingTime: meetingTime || previous?.meetingTime || '',
      privateNights: previous?.privateNights ?? 0,
      hardMeeting: previous?.hardMeeting ?? true,
    };
    changes.business = field(business, 'inferred');
  }

  const simulateError = /^demo error$/i.test(prompt.trim());
  const supported =
    Object.keys(changes).length > 0 ||
    /^surprise me$/i.test(prompt.trim()) ||
    simulateError;
  return { changes, simulateError, supported };
}

function mockOpportunity(
  fixture: JourneyFixture,
  intent: TravelIntent,
): TravelOpportunity | null {
  const destination = destinations.find(
    (item) => item.id === fixture.destinationId,
  )!;
  const requested = intent.destination.value;
  if (requested && destinationFor(requested)?.id !== destination.id)
    return null;

  const preference = intent.transport.value;
  if (preference?.hard && !preference.modes.includes(fixture.mode)) return null;

  const business = intent.business.value;
  if (business && !destination.tags.includes('Business')) return null;
  const origin = intent.origin.value || Object.keys(fixture.origins)[0];
  const leg = Object.entries(fixture.origins).find(([city]) =>
    same(city, origin),
  )?.[1];
  if (!leg) return null;

  const dates = intent.dates.value;
  const dateDays =
    dates?.start && dates.end ? dateSpan(dates.start, dates.end) : null;
  const workDays = dateDays ?? intent.duration.value ?? fixture.days;
  const days = workDays + (business?.privateNights ?? 0);
  if (days * 24 <= 2 * leg.hours) return null;
  const travelers = intent.travelers.value ?? 1;
  const costs: Cost[] = [
    { label: 'Transport', amount: leg.fare * travelers },
    {
      label: 'Stay',
      amount:
        fixture.stay.nightly === null
          ? null
          : fixture.stay.nightly * (days - 1) * Math.ceil(travelers / 2),
    },
    {
      label: 'Meals & activities',
      amount: fixture.daily === null ? null : fixture.daily * days * travelers,
    },
  ];
  const total = costs.some((cost) => cost.amount === null)
    ? null
    : costs.reduce((sum, cost) => sum + (cost.amount ?? 0), 0);
  const budget = intent.budget.value;
  if (budget?.hard && (total === null || total > budget.amount)) return null;

  const signals: DecisionSignal[] = [];
  if (budget) {
    signals.push({
      label: 'Group budget',
      hard: budget.hard,
      detail:
        total === null
          ? 'The total is unknown.'
          : `${budgetLabel(total)} against ${budgetLabel(budget.amount)}.`,
      outcome:
        total === null
          ? 'unknown'
          : total <= budget.amount
            ? 'fits'
            : 'tradeoff',
    });
  }
  if (preference) {
    const fits = preference.modes.includes(fixture.mode);
    signals.push({
      label: 'Transport',
      detail: modeNames[fixture.mode],
      outcome: fits ? 'fits' : 'tradeoff',
      hard: preference.hard,
    });
  }
  if (business) {
    const firstDay = dates?.start || business.meetingDate;
    const lastDay =
      dates?.end || (firstDay ? addDays(firstDay, workDays - 1) : '');
    const inRange =
      !business.meetingDate ||
      (business.meetingDate >= firstDay && business.meetingDate <= lastDay);
    const arrivalDay =
      !business.meetingDate || firstDay === business.meetingDate;
    const [hour, minute] = leg.arrival.split(':').map(Number);
    const [meetingHour, meetingMinute] = business.meetingTime
      .split(':')
      .map(Number);
    const fits =
      !arrivalDay ||
      hour * 60 + minute + 30 <= meetingHour * 60 + meetingMinute;
    if (business.hardMeeting && (!inRange || (business.meetingTime && !fits)))
      return null;
    signals.push({
      label: 'Meeting buffer',
      hard: business.hardMeeting,
      outcome: !inRange
        ? 'tradeoff'
        : business.meetingTime
          ? fits
            ? 'fits'
            : 'tradeoff'
          : 'unknown',
      detail: !inRange
        ? 'The meeting falls outside the work portion of this trip.'
        : business.meetingTime
          ? `Sample arrival ${leg.arrival} on the first day. Meeting ${business.meetingTime}. Target buffer 30 min.`
          : 'Set a meeting time to check the example arrival.',
    });
  }
  const timeOnLocation = Math.max(0, days * 24 - 2 * leg.hours);
  return {
    id: fixture.id,
    destination,
    title: fixture.title,
    dates,
    days,
    transport: {
      mode: fixture.mode,
      label: fixture.transit,
      origin,
      hours: leg.hours,
      estimate: costs[0].amount,
      changes: fixture.changes,
      arrival: leg.arrival,
    },
    stay: fixture.stay,
    costs,
    total,
    timeOnLocation,
    reasons: [
      destination.tags.includes('Business')
        ? 'A compact base for a short stay, with city stops you can fit around the main purpose of your trip.'
        : `A ${destination.tags[0].toLowerCase()}-focused trip with ${fixture.stay.kind.toLowerCase()} as a base and room to set your own pace.`,
      ...signals
        .filter((item) => item.outcome === 'fits')
        .map((item) => item.detail),
    ],
    considerations: [
      fixture.consideration,
      ...signals
        .filter((item) => item.outcome === 'tradeoff')
        .map((item) => item.detail),
    ],
    signals,
    completeness: total === null ? 'provisional' : 'complete',
    evidence: { status: 'mock', label: 'Wohin demo fixture' },
  };
}

export function evaluateIntent(intent: TravelIntent) {
  const score = (opportunity: TravelOpportunity) => {
    const tags = intent.interests.value ?? [];
    const matches = (tag: string) =>
      opportunity.destination.tags.some((value) => same(value, tag));
    return (
      tags.filter(matches).length * 2 +
      Number(Boolean(tags[0] && matches(tags[0]))) +
      opportunity.signals.filter((item) => item.outcome === 'fits').length +
      Number(
        Boolean(
          intent.accommodation.value &&
          normalize(opportunity.stay.kind).includes(
            normalize(intent.accommodation.value),
          ),
        ),
      )
    );
  };
  const opportunities = journeys
    .map((fixture) => mockOpportunity(fixture, intent))
    .filter((item): item is TravelOpportunity => item !== null)
    .sort((first, second) => score(second) - score(first));
  const conflicts: string[] = [];
  if (!opportunities.length) {
    const { destination, origin, transport, budget, business } = intent;
    if (destination.value && !destinationFor(destination.value))
      conflicts.push('This destination is outside the sample catalogue.');
    if (origin.value)
      conflicts.push(
        `Only fixture connections from ${origin.value} were considered.`,
      );
    if (transport.value?.hard)
      conflicts.push('Required transport modes exclude other connections.');
    if (budget.value?.hard)
      conflicts.push(
        `A known estimate within ${budgetLabel(budget.value.amount)} is required.`,
      );
    if (
      business.value?.hardMeeting &&
      (business.value.meetingDate || business.value.meetingTime)
    )
      conflicts.push(
        'The meeting must fall within the work portion of the trip, with a 30-minute arrival buffer when a time is set.',
      );
  }
  return { opportunities, conflicts };
}

function pause(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason);
      return;
    }
    const abort = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort);
      resolve();
    }, milliseconds);
    signal.addEventListener('abort', abort, { once: true });
  });
}

export const mockTravelService: TravelService = {
  destinations: () => destinations,
  interpret: interpretPrompt,
  async search({ revision, intent, signal, simulateError }) {
    await pause(1050, signal);
    if (simulateError)
      throw new Error('The sample search service was interrupted.');
    return { revision, ...evaluateIntent(intent) };
  },
  async explore({ revision, intent, signal }, id) {
    await pause(360, signal);
    const fixture = journeys.find((item) => item.id === id);
    const opportunity = fixture && mockOpportunity(fixture, intent);
    if (!opportunity) return { revision, report: null };
    const stops = opportunity.destination.activities.slice(0, opportunity.days);
    const itinerary = stops.map((place, index) => {
      const start = Math.floor((index * opportunity.days) / stops.length) + 1;
      const end = Math.floor(((index + 1) * opportunity.days) / stops.length);
      return {
        label: end > start ? `Days ${start}–${end}` : `Day ${start}`,
        placeId: place.id,
        title: place.name,
        description: place.description,
      };
    });
    return {
      revision,
      report: {
        opportunity,
        itinerary,
        transportOptions: evaluateIntent({
          ...intent,
          destination: field(opportunity.destination.name),
        }).opportunities.map((item) => item.transport),
      },
    };
  },
};
