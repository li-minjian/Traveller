import type { Journey } from '../api/client';

// Direct flight from docs/contracts/search-v1/response_ok.json.
export const journey = {
  "id": "dummy-berlin-lissabon-2027-05-20-direct-early",
  "legs": [
    {
      "mode": "flight",
      "origin": "Berlin",
      "destination": "Lissabon",
      "departure": "2027-05-20T06:40:00+02:00",
      "arrival": "2027-05-20T09:35:00+01:00",
      "carrier": "Example Air",
      "number": "EX 1201"
    }
  ],
  "offers": [
    {
      "id": "dummy-berlin-lissabon-2027-05-20-direct-early-a",
      "provider": "dummy",
      "price": {
        "amount": 189.0,
        "currency": "EUR",
        "basis": "per_person"
      }
    }
  ],
  "duration_minutes": 235,
  "stops": 0,
  "price": {
    "amount": 189.0,
    "currency": "EUR",
    "basis": "per_person"
  },
  "inbound": null,
  "total_price": {
    "amount": 189.0,
    "currency": "EUR",
    "basis": "per_person"
  }
} satisfies Journey;
