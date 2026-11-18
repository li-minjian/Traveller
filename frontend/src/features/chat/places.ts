import type { Place } from '../../api/client';

/**
 * Search key for place names: lower case, without accents and with single
 * spaces, so that "München", "munchen" and " MUENCHEN" compare as the user
 * expects ("ü" also matches "ue", "ß" also matches "ss").
 */
export function foldText(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/ß/g, 'ss')
    .replace(/[\s\-–'’.]+/g, ' ')
    .trim();
}

/** Spellings with German umlauts written out: "zürich" -> "zuerich". */
function umlautVariants(text: string): string[] {
  const lower = text.toLowerCase();
  const spelled = lower
    .replace(/ä/g, 'ae')
    .replace(/ö/g, 'oe')
    .replace(/ü/g, 'ue');
  return spelled === lower ? [foldText(text)] : [foldText(text), foldText(spelled)];
}

function keysOf(texts: string[]): string[] {
  return texts.flatMap(umlautVariants);
}

/** How well a place matches; lower is better. */
const Rank = { Name: 0, Alias: 1, Country: 2 } as const;
type Rank = (typeof Rank)[keyof typeof Rank];

function rankOf(place: Place, query: string): Rank | null {
  const starts = (keys: string[]) => keys.some((key) => key.startsWith(query));
  if (starts(keysOf([place.name]))) return Rank.Name;
  if (starts(keysOf(place.aliases))) return Rank.Alias;
  if (starts(keysOf([place.country]))) return Rank.Country;
  return null;
}

const collator = new Intl.Collator('de', { sensitivity: 'base' });

/**
 * Places whose name, alias or country starts with `query`, ignoring case and
 * accents. Name matches come first, then alias matches (both alphabetical by
 * name), then country matches (by country and name). An empty query lists
 * every place by country and name.
 */
export function matchPlaces(places: Place[], query: string): Place[] {
  const folded = foldText(query);
  const ranked: { place: Place; rank: Rank }[] = [];
  for (const place of places) {
    const rank = folded === '' ? Rank.Country : rankOf(place, folded);
    if (rank !== null) ranked.push({ place, rank });
  }
  return ranked
    .sort(
      (a, b) =>
        a.rank - b.rank ||
        (a.rank === Rank.Country
          ? collator.compare(a.place.country, b.place.country)
          : 0) ||
        collator.compare(a.place.name, b.place.name),
    )
    .map(({ place }) => place);
}

/**
 * The canonical name for text that is exactly a place name or alias, e.g.
 * "lisbon" -> "Lissabon"; `null` if nothing matches. A name wins over an
 * alias of another place.
 */
export function canonicalPlace(places: Place[], text: string): string | null {
  const folded = foldText(text);
  if (folded === '') return null;
  const byName = places.find((place) =>
    keysOf([place.name]).includes(folded),
  );
  if (byName) return byName.name;
  const byAlias = places.find((place) =>
    keysOf(place.aliases).includes(folded),
  );
  return byAlias ? byAlias.name : null;
}
