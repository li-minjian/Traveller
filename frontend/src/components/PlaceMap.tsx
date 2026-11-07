import { MapPin } from 'lucide-react';
import { useState } from 'react';
import { validCoordinates } from '../domain/travel';
import type { Coordinates, Place } from '../domain/travel';
import { Eyebrow } from './ui';

type Mappable = Place & { coordinates: Coordinates };
const hasCoordinates = (place: Place): place is Mappable =>
  validCoordinates(place.coordinates);

export function PlaceMap({
  places,
  activeId,
  onSelect,
  connect = false,
}: {
  places: Place[];
  activeId?: string;
  onSelect?: (id: string) => void;
  connect?: boolean;
}) {
  const [localId, setLocalId] = useState('');
  const points = places.filter(hasCoordinates);
  const selected =
    points.find((place) => place.id === (activeId ?? localId)) ?? points[0];
  if (!selected)
    return (
      <div className="map-empty">
        <MapPin size={21} />
        <p>Map unavailable. No coordinates were supplied for these places.</p>
      </div>
    );

  const lats = points.map((point) => point.coordinates[0]);
  const lons = points.map((point) => point.coordinates[1]);
  const south = Math.min(...lats);
  const west = Math.min(...lons);
  const latSpan = Math.max(...lats) - south || 1;
  const lonSpan = Math.max(...lons) - west || 1;
  const coordinates = (point: Mappable) => ({
    x:
      points.length === 1 || Math.max(...lons) === west
        ? 50
        : 12 + ((point.coordinates[1] - west) / lonSpan) * 76,
    y:
      points.length === 1 || Math.max(...lats) === south
        ? 50
        : 82 - ((point.coordinates[0] - south) / latSpan) * 64,
  });

  function select(id: string) {
    setLocalId(id);
    onSelect?.(id);
  }

  return (
    <div className="place-map">
      <div
        className="map-plot"
        aria-label="Schematic map of supplied coordinates"
      >
        <span className="map-north" aria-hidden="true">
          ↑ N
        </span>
        {connect && points.length > 1 && (
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <polyline
              points={points
                .map((point) => {
                  const { x, y } = coordinates(point);
                  return `${x},${y}`;
                })
                .join(' ')}
            />
          </svg>
        )}
        {points.map((place, index) => {
          const { x, y } = coordinates(place);
          return (
            <button
              type="button"
              key={place.id}
              className="map-pin"
              style={{ left: `${x}%`, top: `${y}%` }}
              aria-label={`Show ${place.name} on map`}
              aria-pressed={place.id === selected.id}
              onClick={() => select(place.id)}
            >
              {index + 1}
            </button>
          );
        })}
        <span className="map-caption">Schematic · no route guidance</span>
      </div>
      <div className="map-details">
        <div aria-live="polite">
          <Eyebrow>
            {selected.coordinates.map((value) => value.toFixed(3)).join(' · ')}
          </Eyebrow>
          <h3>{selected.name}</h3>
          <p>{selected.description}</p>
        </div>
        <div className="chip-row" aria-label="Map locations">
          {points.map((place) => (
            <button
              type="button"
              className="chip"
              key={place.id}
              aria-pressed={place.id === selected.id}
              onClick={() => select(place.id)}
            >
              {place.name}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
