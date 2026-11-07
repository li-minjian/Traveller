import { describe, expect, it, vi } from 'vitest';
import { initialSession, sessionReducer } from '../src/app/session';
import { field, newIntent, validCoordinates } from '../src/domain/travel';
import {
  evaluateIntent,
  interpretPrompt,
  mockTravelService,
} from '../src/services/mockTravel';

describe('Travel intent', () => {
  it('marks prompt values as inferred or flexible and retains unknown fields', () => {
    const initial = newIntent();
    const { changes, supported } = interpretPrompt(
      'Quiet nature for 5–7 days in autumn under €1,800',
      initial,
    );
    expect(supported).toBe(true);
    expect(changes).toMatchObject({
      duration: { value: 7, provenance: 'inferred' },
      dates: { value: { season: 'Autumn' }, provenance: 'flexible' },
      budget: { value: { amount: 1800, hard: true }, provenance: 'inferred' },
      interests: { value: ['Nature', 'Quiet'], provenance: 'inferred' },
    });
    expect(changes.origin).toBeUndefined();
    expect(initial.origin.provenance).toBe('unknown');
  });

  it('recognizes a destination, explicit dates and group size', () => {
    const { changes } = interpretPrompt(
      'Tuscany from Munich 2026-11-14 to 2026-11-18 for 2 travelers',
      newIntent(),
    );
    expect(changes).toMatchObject({
      destination: { value: 'Val d’Orcia', provenance: 'inferred' },
      origin: { value: 'Munich', provenance: 'inferred' },
      dates: {
        value: { start: '2026-11-14', end: '2026-11-18' },
        provenance: 'inferred',
      },
      travelers: { value: 2, provenance: 'inferred' },
    });
  });

  it('uses no invented criteria for unsupported text', () => {
    expect(
      interpretPrompt('Can you get me concert tickets?', newIntent()),
    ).toMatchObject({ supported: false, changes: {} });
  });

  it('does not turn a hard no-flight condition into a soft rail preference', () => {
    const initial = newIntent();
    const { changes } = interpretPrompt('No flights', initial);
    const intent = { ...initial, ...changes };
    expect(
      interpretPrompt('Prefer sleeper trains', intent).changes.transport,
    ).toBeUndefined();
    expect(
      evaluateIntent(intent).opportunities.every(
        (item) => item.transport.mode !== 'flight',
      ),
    ).toBe(true);
  });
});

describe('Offline opportunities', () => {
  it('keeps partial totals unknown and omits them when a strict budget must be verified', () => {
    const initial = newIntent();
    const provisional = evaluateIntent(initial).opportunities.find(
      (item) => item.id === 'skye-highlands',
    );
    expect(provisional).toMatchObject({
      total: null,
      completeness: 'provisional',
    });
    const strict = {
      ...initial,
      budget: field({ amount: 3000, currency: 'EUR' as const, hard: true }),
    };
    expect(
      evaluateIntent(strict).opportunities.map((item) => item.id),
    ).not.toContain('skye-highlands');
  });

  it('enforces the example meeting buffer and includes optional private nights in estimates', () => {
    const initial = newIntent();
    const { changes } = interpretPrompt(
      'Business trip to Leipzig from Berlin, meeting at 10:30, max €400',
      initial,
    );
    const intent = { ...initial, ...changes };
    const { opportunities } = evaluateIntent(intent);
    expect(opportunities.map((item) => item.id)).toEqual(['leipzig-rail']);
    expect(opportunities[0].signals).toContainEqual(
      expect.objectContaining({ label: 'Meeting buffer', outcome: 'fits' }),
    );
    const business = intent.business.value!;
    const extended = evaluateIntent({
      ...intent,
      business: field({ ...business, privateNights: 1 }),
    }).opportunities[0];
    expect(extended.days).toBe(opportunities[0].days + 1);
    expect(extended.total).toBe((opportunities[0].total ?? 0) + 130);
    expect(
      evaluateIntent({
        ...intent,
        business: field({ ...business, meetingTime: '09:25' }),
      }).opportunities,
    ).toEqual([]);
  });

  it('does not remove a strict transport requirement to make a destination fit', () => {
    const initial = newIntent();
    const intent = {
      ...initial,
      ...interpretPrompt('Faroe Islands, no flights', initial).changes,
    };
    expect(evaluateIntent(intent)).toMatchObject({
      opportunities: [],
      conflicts: ['Required transport modes exclude other connections.'],
    });
  });

  it('uses the explicit date span and group size in cost estimates', () => {
    const initial = newIntent();
    const intent = {
      ...initial,
      ...interpretPrompt(
        'Leipzig from Berlin 2026-11-14 to 2026-11-16, 3 travelers, train only',
        initial,
      ).changes,
    };
    const [trip] = evaluateIntent(intent).opportunities;
    expect(trip.days).toBe(3);
    expect(trip.total).toBe(953);
  });
});

describe('Revisions', () => {
  it('retains the old result as stale and ignores late success and failure', () => {
    const initial = initialSession();
    const first = sessionReducer(initial, { type: 'activate' });
    const result = {
      revision: first.revision,
      ...evaluateIntent(first.intent),
    };
    const resolved = sessionReducer(first, { type: 'resolve', result });
    const updated = sessionReducer(resolved, {
      type: 'update',
      changes: { destination: field('Leipzig') },
    });
    expect(updated.result?.revision).not.toBe(updated.revision);
    expect(sessionReducer(updated, { type: 'resolve', result })).toBe(updated);
    expect(
      sessionReducer(updated, {
        type: 'reject',
        revision: first.revision,
        message: 'old failure',
      }),
    ).toBe(updated);
    const replacement = {
      revision: updated.revision,
      ...evaluateIntent(updated.intent),
    };
    expect(
      sessionReducer(updated, { type: 'resolve', result: replacement }).result
        ?.opportunities,
    ).toHaveLength(2);
  });

  it('cancels an outstanding service request before it completes', async () => {
    vi.useFakeTimers();
    try {
      const controller = new AbortController();
      const response = mockTravelService.search({
        revision: 1,
        intent: newIntent(),
        signal: controller.signal,
      });
      controller.abort();
      await expect(response).rejects.toMatchObject({ name: 'AbortError' });
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('Coordinates', () => {
  it('accepts only supplied finite coordinates within geographic bounds', () => {
    expect(validCoordinates([0, 0])).toBe(true);
    expect(validCoordinates([62.2, -6.7])).toBe(true);
    expect(validCoordinates()).toBe(false);
    expect(validCoordinates([Infinity, 30])).toBe(false);
    expect(validCoordinates([93, 30])).toBe(false);
    expect(validCoordinates([30, 181])).toBe(false);
  });
});
