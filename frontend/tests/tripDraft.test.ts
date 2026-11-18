import { describe, expect, it } from 'vitest';
import type { TripState } from '../src/api/client';
import {
  changedFields,
  draftFromState,
  emptyTripState,
  mergeDraft,
  progress,
} from '../src/features/chat/tripDraft';

const confirmed = <T>(value: T) => ({ value, provenance: 'confirmed' as const });

const state: TripState = {
  ...emptyTripState,
  origin: confirmed('Berlin'),
  departure: confirmed({ earliest: '2027-05-20', latest: '2027-05-20' }),
  return: confirmed({ earliest: '2027-05-26', latest: '2027-05-28' }),
  budget: confirmed({ amount: 300, currency: 'EUR', basis: 'per_person' }),
};
const base = draftFromState(state);

describe('Trip form draft', () => {
  it('fills the draft from the trip state', () => {
    expect(base).toMatchObject({
      origin: 'Berlin',
      destination: '',
      departure: { flexible: false, from: '2027-05-20' },
      return: { flexible: true, from: '2027-05-26', to: '2027-05-28' },
      trip_type: 'round_trip',
      travelers: '',
      budget: { amount: '300', basis: 'per_person', currency: 'EUR' },
      max_stops: '',
    });
  });

  it('sends nothing while the draft equals the server state', () => {
    expect(changedFields(base, base)).toEqual({});
  });

  it('sends only changed fields and clears emptied ones with null', () => {
    const draft = {
      ...base,
      origin: '',
      destination: ' Lissabon ',
      departure: { flexible: true, from: '2027-05-20', to: '2027-05-22' },
      travelers: '2',
      budget: { ...base.budget, amount: '' },
    };
    expect(changedFields(draft, base)).toEqual({
      origin: null,
      destination: 'Lissabon',
      departure: { earliest: '2027-05-20', latest: '2027-05-22' },
      travelers: 2,
      budget: null,
    });
  });

  it('sends a fixed day as a plain date and one-way without return', () => {
    const draft = {
      ...base,
      departure: { flexible: false, from: '2027-05-21', to: '' },
      trip_type: 'one_way' as const,
    };
    expect(changedFields(draft, base)).toEqual({
      departure: '2027-05-21',
      return: null,
      trip_type: 'one_way',
    });
  });

  it('keeps unsaved edits when a chat turn changes the state', () => {
    const current = { ...base, travelers: '3' };
    const next = draftFromState({
      ...state,
      destination: confirmed('Lissabon'),
      travelers: confirmed(2),
    });
    expect(mergeDraft(current, base, next)).toMatchObject({
      destination: 'Lissabon',
      travelers: '3',
    });
  });

  it('follows the server for fields that were just applied', () => {
    const sent = { ...base, origin: 'berlin', travelers: '3' };
    const current = { ...sent, max_stops: '1' };
    const next = draftFromState({
      ...state,
      origin: confirmed('Berlin (BER)'),
      travelers: confirmed(3),
    });
    expect(mergeDraft(current, base, next, sent)).toMatchObject({
      origin: 'Berlin (BER)',
      travelers: '3',
      max_stops: '1',
    });
  });

  it('counts the return flight only for round trips', () => {
    const missing = ['destination', 'return', 'travelers'];
    expect(progress(state, missing)).toEqual({ set: 2, total: 5 });
    const oneWay = { ...state, trip_type: confirmed('one_way' as const) };
    expect(progress(oneWay, ['destination', 'travelers'])).toEqual({
      set: 2,
      total: 4,
    });
  });
});
