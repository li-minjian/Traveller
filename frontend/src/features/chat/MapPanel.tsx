import * as L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Check, Maximize2, Minimize2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { Itinerary, ItineraryStep } from './itinerary';
import { mappableSteps } from './itinerary';

type Props = {
  itinerary: Itinerary;
  activeStepId: string | null;
  onStepHover: (stepId: string | null) => void;
  onStepClick: (stepId: string) => void;
  saved: boolean;
  onSaveTrip: () => void;
};

type LocatedStep = ItineraryStep & { lat: number; lng: number };

const TILES = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const pinBase =
  'flex items-center justify-center rounded-full border-white font-bold leading-none text-white shadow-md transition-transform duration-150 hover:scale-110 hover:bg-forest-deep';
const pinNormal = `${pinBase} h-8 w-8 border-2 bg-forest text-[11px]`;
const pinActive = `${pinBase} h-11 w-11 border-[3px] bg-forest-deep text-sm`;

/** A numbered, circular map pin. Leaflet keeps it anchored to lat/lng. */
function pinIcon(index: number, active: boolean): L.DivIcon {
  const size = active ? 44 : 32;
  return L.divIcon({
    className: 'map-pin',
    html: `<span class="${active ? pinActive : pinNormal}">${index}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

function tooltipContent(step: LocatedStep): HTMLElement {
  const label = document.createElement('span');
  label.textContent = `${step.index}. ${step.name}`;
  return label;
}

/**
 * Right panel: an interactive Leaflet map. Every marker is placed by its
 * latitude / longitude, so pins stay on the right spot while panning and
 * zooming. Clicking a pin highlights the matching itinerary card.
 */
export function MapPanel({
  itinerary,
  activeStepId,
  onStepHover,
  onStepClick,
  saved,
  onSaveTrip,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Record<string, L.Marker>>({});
  const [expanded, setExpanded] = useState(false);
  const steps = mappableSteps(itinerary);

  // Keep the newest steps available to the marker effects without making the
  // map re-fit every time a heart is toggled.
  const stepsRef = useRef<LocatedStep[]>(steps);
  useEffect(() => {
    stepsRef.current = steps;
  }, [steps]);
  const stepKey = steps
    .map((step) => `${step.id}:${step.lat}:${step.lng}`)
    .join('|');

  // Create the map once. React StrictMode mounts effects twice in dev, so the
  // cleanup removes the Leaflet instance before the second mount.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const map = L.map(container, {
      zoomControl: false,
      attributionControl: true,
      scrollWheelZoom: true,
      zoomSnap: 0.25,
      minZoom: 3,
      maxZoom: 19,
    }).setView([41.3874, 2.1686], 13);

    L.tileLayer(TILES, {
      attribution: ATTRIBUTION,
      subdomains: 'abc',
      maxZoom: 19,
    }).addTo(map);
    L.control.zoom({ position: 'topright' }).addTo(map);
    mapRef.current = map;

    // jsdom (tests) has no ResizeObserver; the map still renders there.
    const resize =
      typeof ResizeObserver === 'function'
        ? new ResizeObserver(() => map.invalidateSize())
        : null;
    resize?.observe(container);
    const frame = requestAnimationFrame(() => map.invalidateSize());

    return () => {
      cancelAnimationFrame(frame);
      resize?.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // (Re)build the marker layer whenever the set of located steps changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const layer = L.layerGroup().addTo(map);
    const markers: Record<string, L.Marker> = {};
    const located = stepsRef.current;

    for (const step of located) {
      const marker = L.marker([step.lat, step.lng], {
        icon: pinIcon(step.index, false),
        keyboard: true,
        title: `${step.index}. ${step.name}`,
        riseOnHover: true,
      }).addTo(layer);

      marker.on('mouseover', () => onStepHover(step.id));
      marker.on('mouseout', () => onStepHover(null));
      marker.on('focus', () => onStepHover(step.id));
      marker.on('blur', () => onStepHover(null));
      marker.on('click', () => {
        onStepClick(step.id);
        map.flyTo([step.lat, step.lng], Math.max(map.getZoom(), 15), {
          duration: 0.45,
        });
      });
      markers[step.id] = marker;
    }
    markersRef.current = markers;

    if (located.length > 0) {
      const bounds = L.latLngBounds(
        located.map((step) => [step.lat, step.lng] as [number, number]),
      );
      map.fitBounds(bounds, { padding: [48, 48], maxZoom: 14 });
    }

    return () => {
      layer.remove();
      markersRef.current = {};
    };
  }, [stepKey, onStepHover, onStepClick]);

  // Reflect the active/hovered step on the map without rebuilding markers.
  useEffect(() => {
    const byId = new Map(stepsRef.current.map((step) => [step.id, step]));
    for (const [id, marker] of Object.entries(markersRef.current)) {
      const step = byId.get(id);
      if (!step) continue;
      const active = id === activeStepId;
      marker.setIcon(pinIcon(step.index, active));
      marker.setZIndexOffset(active ? 1000 : 0);
      if (active) {
        marker.bindTooltip(tooltipContent(step), {
          permanent: true,
          direction: 'right',
          className: 'map-tooltip',
          offset: [active ? 24 : 18, 0],
        });
        marker.openTooltip();
      } else {
        marker.unbindTooltip();
      }
    }
  }, [activeStepId, stepKey]);

  // Close the full-screen map with Escape.
  useEffect(() => {
    if (!expanded) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setExpanded(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expanded]);

  return (
    <aside
      className={`flex min-h-0 min-w-0 flex-col overflow-hidden bg-surface max-[1000px]:h-[70dvh] max-[1000px]:min-h-[460px] ${
        expanded ? 'fixed inset-0 z-[60] h-dvh' : 'h-full'
      }`}
    >
      <div className="flex min-h-[118px] shrink-0 items-start px-6 pt-[58px] pb-5">
        <button
          type="button"
          className={`inline-flex min-h-[38px] items-center gap-1.5 rounded-full border bg-white px-4.5 py-2 text-[0.78rem] font-semibold whitespace-nowrap text-forest-deep hover:border-[#2b7050] hover:bg-forest-soft ${
            saved
              ? 'border-forest bg-forest-soft'
              : 'border-[#b3c1b8]'
          }`}
          onClick={onSaveTrip}
        >
          {saved ? (
            <>
              <Check size={15} /> Saved to your trip
            </>
          ) : (
            'Save this itinerary to a trip'
          )}
        </button>
      </div>

      <div className="relative min-h-0 flex-1 bg-[#eef0e8]">
        <div
          className="map-soft-tiles absolute inset-0 h-full w-full bg-[#eef0e8]"
          ref={containerRef}
          role="region"
          aria-label="Trip map"
        />
        {steps.length === 0 && (
          <p className="absolute inset-0 grid place-items-center p-6 text-center text-[0.84rem] text-[#6a7872]">
            Locations will appear on the map as the itinerary is built.
          </p>
        )}
        <button
          type="button"
          className="absolute top-3.5 left-3.5 z-30 grid h-[38px] w-[38px] place-items-center rounded-lg bg-white text-forest-deep shadow-md hover:bg-[#f5f7f3]"
          onClick={() => setExpanded((value) => !value)}
          aria-label={expanded ? 'Exit full-screen map' : 'Expand map'}
          title={expanded ? 'Exit full-screen map' : 'Expand map'}
        >
          {expanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
        </button>
      </div>
    </aside>
  );
}
