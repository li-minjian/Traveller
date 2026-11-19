/**
 * Itinerary data model: the structured list of steps the planning agent
 * builds while chatting. Each step is a place with metadata, grouped by day.
 */

/** A single itinerary step (place to visit). */
export type ItineraryStep = {
  id: string;
  /** 1-based index across all days. */
  index: number;
  name: string;
  /** Short subtitle (neighbourhood, type of attraction). */
  subtitle: string | null;
  /** Rating on a 5-point scale. */
  rating: number | null;
  /** Number of reviews. */
  reviewCount: number | null;
  /** Descriptive tags like "First-timers welcome", "Highly rated". */
  tags: string[];
  /** URL of a representative image. */
  imageUrl: string | null;
  /** Latitude for the map marker. */
  lat: number | null;
  /** Longitude for the map marker. */
  lng: number | null;
  /** Whether the user has bookmarked / favourited this step. */
  saved: boolean;
};

/** One day of the itinerary. */
export type ItineraryDay = {
  dayNumber: number;
  /** Short theme for the day, e.g. "Historic core + tapas crawl". */
  theme: string | null;
  /** Neighbourhoods or area covered. */
  area: string | null;
  /** A short agent-written brief shown in the chat for this day. */
  summary: string | null;
  steps: ItineraryStep[];
};

/** Full itinerary built by the planning agent. */
export type Itinerary = {
  /** Search query or trip title. */
  title: string;
  days: ItineraryDay[];
};

/** An empty itinerary with no steps. */
export const emptyItinerary: Itinerary = { title: '', days: [] };

/**
 * Wikimedia Commons serves the place photos without an API key. The special
 * redirect resolves a file name to the scaled thumbnail.
 */
function commonsImage(file: string, width = 640): string {
  return `https://commons.wikimedia.org/wiki/Special:Redirect/file/${encodeURIComponent(
    file,
  )}?width=${width}`;
}

/**
 * Demo itinerary for Barcelona. In production the agent would populate this
 * from the chat; for now we use it as static data so the three-panel layout
 * is usable immediately.
 */
export const demoItinerary: Itinerary = {
  title: 'weekend trip nach barcelona',
  days: [
    {
      dayNumber: 1,
      theme: 'Historic core + tapas crawl',
      area: 'Gothic Quarter, El Born, La Rambla',
      summary:
        'Start in the Gothic Quarter and let the alleys pull you toward the cathedral, then graze your way through La Boqueria and finish with tapas around Plaça Reial.',
      steps: [
        {
          id: 'step-1',
          index: 1,
          name: 'Barrio Gótico (Barri Gòtic)',
          subtitle: null,
          rating: null,
          reviewCount: null,
          tags: ['First-timers welcome', 'Highly rated'],
          imageUrl: commonsImage('Barri Gotic, Barcelona (P1170658).jpg'),
          lat: 41.3833,
          lng: 2.1761,
          saved: false,
        },
        {
          id: 'step-2',
          index: 2,
          name: 'Mercat de la Boqueria',
          subtitle: 'Shopping · Farmers Markets',
          rating: 4.5,
          reviewCount: 27331,
          tags: ['First-timers welcome', 'Highly rated'],
          imageUrl: commonsImage('La Boqueria.JPG'),
          lat: 41.3816,
          lng: 2.1719,
          saved: false,
        },
        {
          id: 'step-3',
          index: 3,
          name: 'Catedral de Barcelona',
          subtitle: null,
          rating: 4.4,
          reviewCount: 10101,
          tags: [],
          imageUrl: commonsImage('Catedral de Barcelona - 50270508626.jpg'),
          lat: 41.3839,
          lng: 2.1763,
          saved: false,
        },
        {
          id: 'step-4',
          index: 4,
          name: 'Plaça Reial',
          subtitle: 'Historical landmark',
          rating: 4.6,
          reviewCount: 8923,
          tags: ['Highly rated'],
          imageUrl: commonsImage('Plaça Reial, Barcelona.jpg'),
          lat: 41.3799,
          lng: 2.1751,
          saved: false,
        },
      ],
    },
    {
      dayNumber: 2,
      theme: 'Gaudí masterpieces',
      area: 'Eixample, Park Güell',
      summary:
        'Give Gaudí a full day: the Sagrada Família in the morning, Casa Batlló on Passeig de Gràcia, and Park Güell for the late-afternoon light.',
      steps: [
        {
          id: 'step-5',
          index: 5,
          name: 'Basílica de la Sagrada Família',
          subtitle: 'Architectural landmark',
          rating: 4.8,
          reviewCount: 198543,
          tags: ['First-timers welcome', 'Highly rated'],
          imageUrl: commonsImage('Sagrada Familia 03.jpg'),
          lat: 41.4036,
          lng: 2.1744,
          saved: false,
        },
        {
          id: 'step-6',
          index: 6,
          name: 'Casa Batlló',
          subtitle: 'Architecture · Museum',
          rating: 4.7,
          reviewCount: 45287,
          tags: ['Highly rated'],
          imageUrl: commonsImage(
            'Casa Batllo Overview Barcelona Spain cut.jpg',
          ),
          lat: 41.3916,
          lng: 2.1649,
          saved: false,
        },
        {
          id: 'step-7',
          index: 7,
          name: 'Park Güell',
          subtitle: 'Park · Gaudí',
          rating: 4.5,
          reviewCount: 95314,
          tags: ['First-timers welcome'],
          imageUrl: commonsImage('Park Güell 01.jpg'),
          lat: 41.4145,
          lng: 2.1527,
          saved: false,
        },
      ],
    },
    {
      dayNumber: 3,
      theme: 'Big views day',
      area: 'Montjuïc, Barceloneta',
      summary:
        'Make Day 3 your "big views" day: go up Montjuïc, take your time with one major museum if you\'re in the mood, then aim for sunset viewpoints. This day feels different from the city-core days, which is exactly what you want on a weekend.',
      steps: [
        {
          id: 'step-8',
          index: 8,
          name: 'Montjuïc Castle',
          subtitle: 'Fortress · Viewpoint',
          rating: 4.3,
          reviewCount: 18764,
          tags: [],
          imageUrl: commonsImage(
            'Barcelona - Montjuïc - Castell de Montjuïc 1799 - Carretera de Montjuïc - Panorama View of the Castle 03.jpg',
          ),
          lat: 41.3633,
          lng: 2.1661,
          saved: false,
        },
        {
          id: 'step-9',
          index: 9,
          name: 'Barceloneta Beach',
          subtitle: 'Beach · Waterfront',
          rating: 4.4,
          reviewCount: 32156,
          tags: ['Beaches and waterfront'],
          imageUrl: commonsImage('Platja de la Barceloneta 02.jpg'),
          lat: 41.3785,
          lng: 2.192,
          saved: false,
        },
        {
          id: 'step-10',
          index: 10,
          name: "Museu Nacional d'Art de Catalunya",
          subtitle: 'Art museum',
          rating: 4.6,
          reviewCount: 21489,
          tags: ['Museums and culture', 'Highly rated'],
          imageUrl: commonsImage(
            '(Barcelona) Palau Nacional - National Museum of Art of Catalunya.jpg',
          ),
          lat: 41.3685,
          lng: 2.1535,
          saved: false,
        },
        {
          id: 'step-11',
          index: 11,
          name: 'Lluis Companys Olympic Stadium',
          subtitle: 'Sports venue',
          rating: 4.2,
          reviewCount: 5678,
          tags: [],
          imageUrl: commonsImage(
            'Estadi Olímpic Lluís Companys Mai 2013.jpg',
          ),
          lat: 41.3647,
          lng: 2.1555,
          saved: false,
        },
        {
          id: 'step-12',
          index: 12,
          name: 'Port Olímpic',
          subtitle: 'Marina · Dining',
          rating: 4.3,
          reviewCount: 11234,
          tags: ['Beaches and waterfront'],
          imageUrl: commonsImage(
            '22 01 21 Port Olímpic 0501 RalfR wp.jpg',
          ),
          lat: 41.3882,
          lng: 2.199,
          saved: false,
        },
      ],
    },
  ],
};

/** All steps across all days, in order. */
export function allSteps(itinerary: Itinerary): ItineraryStep[] {
  return itinerary.days.flatMap((day) => day.steps);
}

/** All steps that have coordinates. */
export function mappableSteps(
  itinerary: Itinerary,
): (ItineraryStep & { lat: number; lng: number })[] {
  return allSteps(itinerary).filter(
    (step): step is ItineraryStep & { lat: number; lng: number } =>
      step.lat !== null && step.lng !== null,
  );
}
