# Wohin journeys and design system

- Home `/` → Ask AI `/discover` → results in the same workspace → `/compare` or `/explore/:opportunityId` → back to discovery.
- Home → Travel search `/search` → destination `/destinations/:destinationId` → Ask AI with destination and criteria → back to destination or travel search.
- Comparison and exploration are optional. Selected journeys and both entry modes share a tab-local travel context. Public destination and opportunity identifiers may appear in URLs.

## Visual system

Draft v1 supplies the dark teal `#071e24`, warm canvas `#faf9f9`, mist surfaces, thin borders, editorial EB Garamond headings and Plus Jakarta Sans controls. Both variable fonts are served locally. The shared stylesheet sets a 1440px page width, responsive gutters, small control and card radii, subtle shadows, visible focus and restrained loading motion that respects reduced-motion preferences.

Shared components include the main navigation, journey image and card, criteria chips and native dialog, comparison selection bar, price breakdown, status notices and coordinate map. The editorial landing and destination guides use large imagery. The AI workspace pairs a conversation rail with a results or report canvas and collapses chat into an explicit toggle below 780px. Travel search gives its structured form the main column. Comparison cards stack below 550px and the factor matrix scrolls inside its own keyboard-focusable region.

## State and continuity

- A valid prompt opens Discovery synchronously. Its result canvas shows loading or an explicit refresh notice. Partial prices show **Unknown** and **Provisional · Demo**. Failed searches offer retry. Empty results explain active requirements and expose criteria editing.
- The criteria chips show field provenance. Manual edits, optional confirmation of inferred values and supported prompts update the same intent. The latest revision controls visible results and reports. Date flexibility is displayed alongside date criteria.
- A selected journey stays selected across compare, Explore, mode switching and reload. Choices outside current criteria remain saved and cannot be compared until they fit again. Sort order is saved separately for each results view. Router scroll restoration handles revisiting paths.
- Map pins and location chips select the same details. Results maps link back to the corresponding card. No coordinates yields an empty map state.
- Desktop and narrow screenshots cover Landing, both Discovery states, Compare, Explore, Travel search entry and results, and destination detail. The browser suite also checks tablet matrix containment, keyboard entry and dialog dismissal.
