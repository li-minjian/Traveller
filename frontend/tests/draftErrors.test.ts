import { describe, expect, it } from 'vitest';
import {
  draftErrors,
  draftFromState,
  emptyTripState,
  todayIso,
} from '../src/features/chat/tripDraft';
import type { TripDraft } from '../src/features/chat/tripDraft';

const TODAY = '2026-11-18';

function draft(changes: Partial<TripDraft>): TripDraft {
  return { ...draftFromState(emptyTripState), ...changes };
}

const day = (from: string) => ({ flexible: false, from, to: from });

describe('draftErrors', () => {
  it('accepts an empty form and valid dates', () => {
    expect(draftErrors(draft({}), TODAY)).toEqual({});
    expect(
      draftErrors(
        draft({ departure: day('2026-11-27'), return: day('2026-11-29'), travelers: '2' }),
        TODAY,
      ),
    ).toEqual({});
    expect(draftErrors(draft({ departure: day(TODAY) }), TODAY)).toEqual({});
  });

  it('marks a departure in the past', () => {
    expect(draftErrors(draft({ departure: day('2026-11-11') }), TODAY)).toEqual({
      departure: ['This date is in the past.'],
    });
  });

  it('accepts a flexible window that ends in the future', () => {
    const window = { flexible: true, from: '2026-11-10', to: '2026-11-30' };
    expect(draftErrors(draft({ departure: window }), TODAY)).toEqual({});
  });

  it('marks a return before the departure, but not for a one-way trip', () => {
    const changes = { departure: day('2026-12-20'), return: day('2026-12-15') };
    expect(draftErrors(draft(changes), TODAY)).toEqual({
      return: ['The return must not be before the departure.'],
    });
    expect(draftErrors(draft({ ...changes, trip_type: 'one_way' }), TODAY)).toEqual({});
  });

  it('marks fewer than one traveller', () => {
    expect(draftErrors(draft({ travelers: '0' }), TODAY)).toEqual({
      travelers: ['At least 1 traveller.'],
    });
  });

  it('formats today as YYYY-MM-DD', () => {
    expect(todayIso(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
});
