import { describe, expect, it } from 'vitest';
import type { Place } from '../src/api/client';
import {
  canonicalPlace,
  foldText,
  matchPlaces,
} from '../src/features/chat/places';

// Sorted by country, then name, like the API answers.
const places: Place[] = [
  { name: 'Berlin', country: 'Deutschland', aliases: ['ber'] },
  { name: 'München', country: 'Deutschland', aliases: ['munich', 'muc'] },
  { name: 'Paris', country: 'Frankreich', aliases: ['cdg'] },
  { name: 'Lissabon', country: 'Portugal', aliases: ['lisbon', 'lisboa', 'lis'] },
  { name: 'Porto', country: 'Portugal', aliases: ['opo', 'oporto'] },
  { name: 'Zürich', country: 'Schweiz', aliases: ['zurich', 'zrh'] },
  { name: 'Barcelona', country: 'Spanien', aliases: ['bcn'] },
];

const names = (query: string) => matchPlaces(places, query).map((p) => p.name);

describe('foldText', () => {
  it('ignores case, accents and extra spaces', () => {
    expect(foldText('  MÜNCHEN ')).toBe('munchen');
    expect(foldText('São  Paulo')).toBe('sao paulo');
    expect(foldText('Saint-Étienne')).toBe('saint etienne');
    expect(foldText('Gießen')).toBe('giessen');
  });
});

describe('matchPlaces', () => {
  it('matches umlauts with and without accents', () => {
    expect(names('munchen')).toEqual(['München']);
    expect(names('München')).toEqual(['München']);
    expect(names('muenchen')).toEqual(['München']);
    expect(names('ZURICH')).toEqual(['Zürich']);
  });

  it('matches the start of an alias', () => {
    expect(names('lisbon')).toEqual(['Lissabon']);
    expect(names('munic')).toEqual(['München']);
    expect(names('bcn')).toEqual(['Barcelona']);
  });

  it('lists every city of a country', () => {
    expect(names('Portugal')).toEqual(['Lissabon', 'Porto']);
    expect(names('port')).toEqual(['Porto', 'Lissabon']);
    expect(names('deutsch')).toEqual(['Berlin', 'München']);
  });

  it('matches only the start, not the middle', () => {
    expect(names('bon')).toEqual([]);
    expect(names('erlin')).toEqual([]);
  });

  it('puts name matches before alias and country matches', () => {
    // "p": Paris and Porto by name, Lissabon only by its country.
    expect(names('p')).toEqual(['Paris', 'Porto', 'Lissabon']);
    // "b": names alphabetically, no alias-only hit here.
    expect(names('b')).toEqual(['Barcelona', 'Berlin']);
    // "o": Porto only through the alias "oporto"/"opo".
    expect(names('o')).toEqual(['Porto']);
  });

  it('lists all places by country and name for an empty query', () => {
    expect(names('')).toEqual(places.map((place) => place.name));
    expect(names('   ')).toEqual(places.map((place) => place.name));
  });

  it('finds nothing for an unknown place', () => {
    expect(names('Tokio')).toEqual([]);
    expect(matchPlaces([], 'Berlin')).toEqual([]);
  });
});

describe('canonicalPlace', () => {
  it('normalizes an exact name or alias to the canonical name', () => {
    expect(canonicalPlace(places, 'lissabon')).toBe('Lissabon');
    expect(canonicalPlace(places, 'Lisbon')).toBe('Lissabon');
    expect(canonicalPlace(places, ' LIS ')).toBe('Lissabon');
    expect(canonicalPlace(places, 'munchen')).toBe('München');
    expect(canonicalPlace(places, 'Muenchen')).toBe('München');
    expect(canonicalPlace(places, 'zurich')).toBe('Zürich');
  });

  it('leaves partial input, countries and unknown places alone', () => {
    expect(canonicalPlace(places, 'Lissa')).toBeNull();
    expect(canonicalPlace(places, 'Portugal')).toBeNull();
    expect(canonicalPlace(places, 'Tokio')).toBeNull();
    expect(canonicalPlace(places, '')).toBeNull();
  });

  it('prefers a city name over an alias of another city', () => {
    const tricky: Place[] = [
      { name: 'Alpha', country: 'X', aliases: ['beta'] },
      { name: 'Beta', country: 'Y', aliases: [] },
    ];
    expect(canonicalPlace(tricky, 'beta')).toBe('Beta');
  });
});
