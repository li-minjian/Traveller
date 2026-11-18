import type { Money } from '../../api/client';

export function formatMoney(money: Money) {
  let amount: string;
  try {
    amount = new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: money.currency,
    }).format(money.amount);
  } catch {
    // Unknown currency code.
    amount = `${money.amount} ${money.currency}`;
  }
  return `${amount} ${money.basis === 'per_person' ? 'p. P.' : 'gesamt'}`;
}

/** 235 → "3 h 55 min". */
export function formatDuration(minutes: number) {
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

export function formatStops(stops: number) {
  if (stops === 0) return 'Direct';
  return `${stops} ${stops === 1 ? 'stop' : 'stops'}`;
}

/** HH:MM as written in the ISO string, i.e. local time at that place. */
export function localTime(iso: string) {
  return iso.slice(11, 16);
}

/** DD.MM. as written in the ISO string, without time-zone conversion. */
export function localDate(iso: string) {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}.`;
}
