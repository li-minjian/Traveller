# Frontend contract draft

**Proposed for team discussion.** The TypeScript types in [travel.ts](../frontend/src/domain/travel.ts) describe what the UI consumes. The default provider injects the [mock adapter](../frontend/src/services/mockTravel.ts). The transport protocol and service topology are team decisions.

```ts
// Excerpt from a request, omitting unrelated TravelIntent fields.
const context = {
  revision: 4,
  intent: {
    destination: { value: 'Leipzig', provenance: 'confirmed' },
    origin: { value: 'Berlin', provenance: 'confirmed' },
    budget: { value: { amount: 400, currency: 'EUR', hard: true }, provenance: 'confirmed' },
    transport: { value: { modes: ['rail'], hard: true }, provenance: 'inferred' },
    dates: { value: null, provenance: 'unknown' },
  },
};

// Excerpt from an opportunity in that revision.
const example = {
  revision: 4,
  opportunity: {
    id: 'leipzig-rail',
    title: 'Leipzig by Morning Rail',
    total: 251,
    completeness: 'complete',
    evidence: { status: 'mock', label: 'Wohin demo fixture' },
    transport: { mode: 'rail', origin: 'Berlin', hours: 1.25, changes: 0, arrival: '09:15' },
  },
};
```

| Surface | Contract |
| --- | --- |
| `destinations()` | The UI reads a loaded catalogue for names, aliases, stable IDs and optional places/coordinates. A future adapter can preload a catalogue before mounting the provider. |
| `interpret(prompt, intent)` | Local demo vocabulary returns an intent patch and a support flag synchronously. An eventual conversational API needs its own asynchronous revision handling while the workspace opens immediately. |
| `search({ intent, revision, signal })` | Returns current opportunities and explanations when hard criteria leave no results. Cancellation is local to the request. A failed request is distinct from an empty successful response. |
| `explore(request, opportunityId)` | Returns a report for a compatible stable ID in the requested revision, or a missing report. Includes itinerary items with place IDs, sample connections and the underlying opportunity. |

`confirmed` records explicit user input or confirmation. `inferred` marks a demo interpretation or default. `unknown` records missing criteria. `flexible` preserves stated date or duration leeway. The mock propagates dates and uses explicit date spans for estimates. Fixture legs have no date-specific inventory.

Unknown costs remain `null`. Group estimates combine round-trip per-traveler transport, sample room nights at two travelers per room, and daily meals and activities. Missing cost components make the total unknown and provisional. A strict budget excludes estimates whose total is unknown or above the limit. A preferred budget contributes to ranking and trade-offs. Business checks use the arrival fixture and a local meeting time, with a 30-minute buffer on the day of arrival and the private extension included in the estimate.

On a criteria change or retry, the session starts a new revision. The provider cancels superseded requests and the reducer rejects late responses. Loading replaces old results with stale feedback until the new revision resolves. The tab snapshot stores intent, prompts, sort and selected IDs. It recomputes results and reports after reload.

A future data service needs stable IDs, provenance for criteria and evidence, units and cost scope, explicit missing values, transport legs and meeting timezone context, and useful constraint explanations. Provider metadata and timestamps should be displayed only where supplied. No HTTP routes are implied by these interfaces.
