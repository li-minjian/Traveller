# Wohin frontend scope

The Project VS course notes identify a runnable, distributed LLM-based multi-agent travel-planning prototype with constraints as the eventual course project (CR-01, CR-03, CR-04). They also capture agile work and course assessment (CR-02, CR-05, CR-06). This delivery is the frontend milestone. The business and reimbursement examples in the course notes are examples whose required scope is open. [Project VS](https://app.notion.com/p/3f95f33c39bb809e8e74ee185aeeea51) · [Course requirements](https://app.notion.com/p/3fe5f33c39bb81859c9cff9a90193679)

The PRD, workflow, product backlog and frontend backlog are discussion drafts. The v3 brief adds two connected entry modes to the AI-focused drafts. The implementation uses their behaviors as scope references. [PRD](https://app.notion.com/p/3ff5f33c39bb817d83b7ded909528ffd) · [User journey](https://app.notion.com/p/3ff5f33c39bb818bb924d771eec1228f) · [Product backlog](https://app.notion.com/p/40c5f33c39bb8178a093de7a7e300a48) · [Frontend backlog](https://app.notion.com/p/40f5f33c39bb816ba6caf65eb1c2cbbd)

| Surface | Frontend scope |
| --- | --- |
| Landing | Editorial hero, free-text entry, one-click inspiration and destination guides. Figma frame 1:2. |
| Discovery | Conversation and editable criteria, immediate loading canvas, results, map, selections and status feedback. Figma frames 1:2384 and 1:2017. |
| Compare | Per-journey estimates, transit, stays, fit and trade-offs, plus a comparison matrix. Figma frame 1:3015. |
| Explore | An itinerary, sample transport and stay, budget, location map and destination link. Figma frame 1:2492. |
| Travel search | Manual destination, origin, dates, flexibility, travelers, budget and preferences. The same journey cards support sorting and comparison. Added for v3. |
| Destination guide | Getting there, accommodation, activities and map, with a handoff to Ask AI. Added for v3. |
| Business trip | Optional purpose, meeting date/time, arrival buffer, private extension and shared strict/soft constraints. Example checks use fixture values. |

[Figma Draft v1](https://www.figma.com/design/qEliBgQGcQ2jYBEjbsRKlT/Draft-v1?node-id=0-1)

| Draft reference | What the demo covers |
| --- | --- |
| FR-01–03 · WF-01–03 | Free text and inspiration submit immediately. Refinements remain optional. Unsupported text leaves existing criteria intact. |
| FR-04 · WF-04 | Typed intent with field provenance, shared editing and explicit confirmation of inferences. |
| FR-05–07 · WF-05 | Bounded European catalogue with six journey fixtures, partial totals, empty/error feedback and retry. |
| FR-08 · WF-06 | Strict filtering, preference ranking, budget and transport trade-offs, business buffer and multi-selection comparison. |
| FR-09–10 · WF-07 | Fixture-based Explore reports and interactive schematic maps using supplied coordinates. |
| FR-11 · WF-04 | Aborted superseded requests, revision-checked responses and visible stale feedback. |

Accounts, booking and payment, live inventory, company approvals and expense reimbursement are outside this frontend milestone.
