import type { Accommodation, Destination, Mode } from '../domain/travel';

const picture = (name: string) => `/images/${name}.webp`;

export const destinations: Destination[] = [
  {
    id: 'faroe-islands', name: 'Faroe Islands', region: 'North Atlantic · Faroe Islands',
    aliases: ['faroe', 'faroes', 'färöer', 'vágar'],
    description: 'Follow the shoreline from turf-roofed villages to waterfalls and open ridges. Leave room in the day for the light to change.',
    image: picture('faroe'), editorialImage: picture('faroe-editorial'),
    reportImage: picture('faroe-report'), compareImage: picture('faroe-compare'),
    coordinates: [62.0053, -6.7737], tags: ['Coast', 'Nature', 'Quiet'],
    activities: [
      { id: 'gasadalur', name: 'Gásadalur & Múlafossur', description: 'A short village walk with a view of the waterfall and the ocean.', coordinates: [62.1086, -7.4347] },
      { id: 'saksun', name: 'Saksun lagoon', description: 'Explore the village and tidal landscape. Check local access before setting out.', coordinates: [62.2485, -7.1734] },
      { id: 'gjogv', name: 'Gjógv harbour', description: 'Spend a slow afternoon by the village’s natural harbour.', coordinates: [62.3259, -6.9416] },
    ],
  },
  {
    id: 'val-dorcia', name: 'Val d’Orcia', region: 'Tuscany · Italy',
    aliases: ['val d’orcia', "val d'orcia", 'val dorcia', 'tuscany', 'toskana', 'florence'],
    description: 'Hill towns, cypress-lined roads and long lunches set the pace in this corner of southern Tuscany.',
    image: picture('tuscany'), editorialImage: picture('tuscany-editorial'), compareImage: picture('tuscany-compare'),
    coordinates: [43.0606, 11.6145], tags: ['Countryside', 'Food', 'Quiet', 'Warm'],
    activities: [
      { id: 'pienza', name: 'Pienza', description: 'Walk the old town and pause at the valley-facing terraces.', coordinates: [43.0766, 11.6788] },
      { id: 'bagno-vignoni', name: 'Bagno Vignoni', description: 'Explore the village square and the lanes around its historic thermal pool.', coordinates: [43.0287, 11.6173] },
      { id: 'san-quirico', name: 'San Quirico d’Orcia', description: 'A village stop for gardens and a market lunch.', coordinates: [43.0574, 11.6049] },
    ],
  },
  {
    id: 'isle-of-skye', name: 'Isle of Skye', region: 'Scottish Highlands · UK',
    aliases: ['skye', 'scotland', 'schottland', 'highlands'],
    description: 'Ridges give way to lochs and small harbours. Plan one long walk and keep an indoor alternative for changing conditions.',
    image: picture('skye'), coordinates: [57.4124, -6.1962], tags: ['Mountains', 'Nature', 'Quiet'],
    activities: [
      { id: 'portree', name: 'Portree harbour', description: 'Start with the harbourfront and a short town walk.', coordinates: [57.4114, -6.1914] },
      { id: 'quiraing', name: 'Quiraing', description: 'Choose a ridge walk only when conditions suit your group.', coordinates: [57.6282, -6.278] },
      { id: 'staffin', name: 'Staffin', description: 'Spend a quieter afternoon on the coast.', coordinates: [57.6261, -6.2076] },
    ],
  },
  {
    id: 'leipzig', name: 'Leipzig', region: 'Saxony · Germany',
    aliases: ['leipzig'],
    description: 'A compact rail-connected city with market arcades, music history and neighbourhood cafés. A practical base for a short working trip.',
    coordinates: [51.3397, 12.3731], tags: ['City', 'Culture', 'Business', 'Budget'],
    activities: [
      { id: 'leipzig-centre', name: 'Market square & arcades', description: 'An easy walk between the station, the market square and the old passageways.', coordinates: [51.3404, 12.3745] },
      { id: 'leipzig-park', name: 'Clara-Zetkin-Park', description: 'Leave an hour for a canal-side walk after the meeting.', coordinates: [51.3309, 12.3519] },
    ],
  },
  {
    id: 'dresden', name: 'Dresden', region: 'Saxony · Germany',
    aliases: ['dresden'],
    description: 'An Elbe-side city break with museums, walkable neighbourhoods and room for a day away from the centre.',
    tags: ['City', 'Culture', 'Business', 'Budget'],
    activities: [
      { id: 'dresden-centre', name: 'Altstadt on foot', description: 'A self-guided walk through the historic centre. Coordinates are unavailable in this fixture.' },
      { id: 'dresden-neustadt', name: 'Neustadt cafés', description: 'An unhurried afternoon in local cafés and courtyards.' },
    ],
  },
];

export type JourneyFixture = {
  id: string;
  destinationId: string;
  title: string;
  days: number;
  origins: Record<string, { hours: number; fare: number; arrival: string }>;
  mode: Mode;
  transit: string;
  changes: number;
  stay: Accommodation;
  daily: number | null;
  consideration: string;
};

export const journeys: JourneyFixture[] = [
  {
    id: 'faroe-coast', destinationId: 'faroe-islands', title: 'The Misty Archipelago', days: 6,
    origins: { Berlin: { hours: 6.5, fare: 480, arrival: '15:30' }, Copenhagen: { hours: 3, fare: 330, arrival: '13:30' } },
    mode: 'flight', transit: 'Flight + local transfer', changes: 1,
    stay: { name: 'A harbour cabin', kind: 'Self-catering cabin', nightly: 152, detail: 'A sample self-catering base near the shoreline.', image: picture('cabin') },
    daily: 55, consideration: 'Allow buffer time for onward transfers and leave outdoor days flexible.',
  },
  {
    id: 'tuscany-rail', destinationId: 'val-dorcia', title: 'Tuscan Hills by Rail', days: 7,
    origins: { Berlin: { hours: 15.5, fare: 350, arrival: '17:00' }, Munich: { hours: 9, fare: 230, arrival: '16:30' } },
    mode: 'rail', transit: 'Rail via Florence + local bus', changes: 2,
    stay: { name: 'A hill-town guesthouse', kind: 'Guesthouse', nightly: 110, detail: 'A sample room within walking distance of shops and cafés.', image: picture('tuscany-editorial') },
    daily: 60, consideration: 'Some countryside stops have limited onward transport. Group sights around one base.',
  },
  {
    id: 'skye-highlands', destinationId: 'isle-of-skye', title: 'The Highland Way', days: 5,
    origins: { London: { hours: 13, fare: 340, arrival: '14:00' }, Edinburgh: { hours: 7, fare: 160, arrival: '15:30' } },
    mode: 'rail', transit: 'Rail + Highland coach', changes: 2,
    stay: { name: 'A small loch-side lodge', kind: 'Lodge', nightly: 125, detail: 'A sample stay for a walking-focused trip.' },
    daily: null, consideration: 'Meals and activities are missing from this estimate. Keep a backup plan for exposed walks.',
  },
  {
    id: 'leipzig-rail', destinationId: 'leipzig', title: 'Leipzig by Morning Rail', days: 2,
    origins: { Berlin: { hours: 1.25, fare: 86, arrival: '09:15' }, Dresden: { hours: 1.5, fare: 76, arrival: '09:30' } },
    mode: 'rail', transit: 'Direct intercity train', changes: 0,
    stay: { name: 'A station-area hotel', kind: 'Hotel', nightly: 95, detail: 'A sample hotel near the station with a desk and breakfast.' },
    daily: 35, consideration: 'Allow time between the station and your meeting venue.',
  },
  {
    id: 'leipzig-coach', destinationId: 'leipzig', title: 'Leipzig on a Smaller Budget', days: 2,
    origins: { Berlin: { hours: 2.5, fare: 48, arrival: '11:30' } },
    mode: 'coach', transit: 'Direct coach', changes: 0,
    stay: { name: 'A city-centre pension', kind: 'Guesthouse', nightly: 72, detail: 'A simple sample room in the centre.' },
    daily: 35, consideration: 'The example coach arrives later in the morning.',
  },
  {
    id: 'dresden-rail', destinationId: 'dresden', title: 'An Elbe City Break', days: 3,
    origins: { Berlin: { hours: 2, fare: 98, arrival: '10:00' } },
    mode: 'rail', transit: 'Direct intercity train', changes: 0,
    stay: { name: 'An old-town guesthouse', kind: 'Guesthouse', nightly: 82, detail: 'A sample base near the historic centre.' },
    daily: 37, consideration: 'This fixture has activity descriptions but no map coordinates.',
  },
];

export const inspiration = [
  { label: 'Somewhere warm in November', prompt: 'Somewhere warm in November', icon: 'sun' },
  { label: 'A weekend escape', prompt: 'A spontaneous weekend escape by train', icon: 'calendar' },
  { label: 'Nature and quiet places', prompt: 'Nature and quiet places for 6 days around €1,800', icon: 'mountain' },
  { label: 'Surprise me', prompt: 'Surprise me', icon: 'sparkles' },
] as const;
