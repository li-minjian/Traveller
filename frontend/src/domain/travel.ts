export type Provenance = 'confirmed' | 'inferred' | 'unknown' | 'flexible';
export type Field<T> = { value: T | null; provenance: Provenance };
export type Mode = 'rail' | 'coach' | 'flight' | 'car';
export type CostKind = 'Transport' | 'Stay' | 'Meals & activities';
export type TripDates = { start: string; end: string; flexibility: number; season: string };
export type Budget = { amount: number; currency: 'EUR'; hard: boolean };
export type TransportPreference = { modes: Mode[]; hard: boolean };
export type BusinessTrip = {
  purpose: string;
  meetingDate: string;
  meetingTime: string;
  privateNights: number;
  hardMeeting: boolean;
};

export type TravelIntent = {
  origin: Field<string>;
  destination: Field<string>;
  dates: Field<TripDates>;
  duration: Field<number>;
  travelers: Field<number>;
  budget: Field<Budget>;
  transport: Field<TransportPreference>;
  accommodation: Field<string>;
  interests: Field<string[]>;
  business: Field<BusinessTrip>;
};

export function field<T>(value: T | null, provenance: Provenance = 'confirmed'): Field<T> {
  return { value, provenance: value === null ? 'unknown' : provenance };
}

export function newIntent(): TravelIntent {
  return {
    origin: field<string>(null), destination: field<string>(null), dates: field<TripDates>(null),
    duration: field<number>(null), travelers: field(1, 'inferred'), budget: field<Budget>(null),
    transport: field<TransportPreference>(null), accommodation: field<string>(null),
    interests: field<string[]>(null), business: field<BusinessTrip>(null),
  };
}

export const modes: Mode[] = ['rail', 'coach', 'flight', 'car'];
export const modeNames: Record<Mode, string> = { rail: 'Train', coach: 'Coach', flight: 'Flight', car: 'Car' };
export const budgetLabel = (amount: number | null) =>
  amount === null ? 'Unknown' : new Intl.NumberFormat('en-IE', {
    style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
  }).format(amount);

export type Coordinates = readonly [latitude: number, longitude: number];
export type Place = { id: string; name: string; description: string; coordinates?: Coordinates };
export type Destination = Place & {
  region: string;
  aliases: string[];
  image?: string;
  editorialImage?: string;
  reportImage?: string;
  compareImage?: string;
  tags: string[];
  activities: Place[];
};

export type Evidence = { status: 'mock'; label: string };
export type TransportOption = {
  mode: Mode;
  label: string;
  hours: number | null;
  changes: number | null;
  estimate: number | null;
  arrival: string | null;
  origin: string;
};
export type Accommodation = { name: string; kind: string; nightly: number | null; detail: string; image?: string };
export type Cost = { label: CostKind; amount: number | null };
export type DecisionSignal = { label: string; detail: string; outcome: 'fits' | 'tradeoff' | 'unknown'; hard: boolean };

export type TravelOpportunity = {
  id: string;
  destination: Destination;
  title: string;
  dates: TripDates | null;
  days: number;
  transport: TransportOption;
  stay: Accommodation;
  costs: Cost[];
  total: number | null;
  timeOnLocation: number | null;
  reasons: string[];
  considerations: string[];
  signals: DecisionSignal[];
  completeness: 'complete' | 'provisional';
  evidence: Evidence;
};

export type ExploreReport = {
  opportunity: TravelOpportunity;
  itinerary: { label: string; title: string; description: string }[];
  transportOptions: TransportOption[];
};

export type SearchResult = { revision: number; opportunities: TravelOpportunity[]; conflicts: string[] };
export type SearchRequest = {
  revision: number;
  intent: TravelIntent;
  signal: AbortSignal;
  simulateError?: boolean;
};
export interface TravelService {
  destinations(): Destination[];
  search(request: SearchRequest): Promise<SearchResult>;
  explore(request: SearchRequest, opportunityId: string): Promise<{ revision: number; report: ExploreReport | null }>;
}

export function validCoordinates(point?: Coordinates): point is Coordinates {
  return Boolean(point && Number.isFinite(point[0]) && Number.isFinite(point[1])
    && Math.abs(point[0]) <= 90 && Math.abs(point[1]) <= 180);
}

export function dateSpan(start: string, end: string) {
  return Math.round((Date.parse(end) - Date.parse(start)) / 86_400_000) + 1;
}

export function datesLabel(dates: TripDates | null) {
  if (!dates) return 'Any time';
  if (dates.season) return dates.season + (dates.flexibility ? ` · ±${dates.flexibility} days` : '');
  if (!dates.start) return dates.flexibility ? `Flexible ±${dates.flexibility} days` : 'Any time';
  const format = (date: string) => new Intl.DateTimeFormat('en-GB', {
    month: 'short', day: 'numeric', timeZone: 'UTC',
  }).format(new Date(date));
  const range = dates.end && dates.end !== dates.start ? `${format(dates.start)} – ${format(dates.end)}` : format(dates.start);
  return range + (dates.flexibility ? ` · ±${dates.flexibility} days` : '');
}
