'use client';

import 'leaflet/dist/leaflet.css';
import { useEffect } from 'react';
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
} from 'react-leaflet';

export type PatrolMapMarker = {
  zone_id: number;
  name: string;
  zone_type: string;
  lat: number;
  lon: number;
  units: number;
  priority_score: number;
};

const NYC_CENTER: [number, number] = [40.7128, -74.006];
const ZOOM = 11;

function AutoFit({ markers }: { markers: PatrolMapMarker[] }) {
  const map = useMap();
  useEffect(() => {
    if (markers.length === 0) return;
    const latLngs: [number, number][] = markers.map((m) => [m.lat, m.lon]);
    if (latLngs.length === 1) {
      map.flyTo(latLngs[0], 13, { duration: 0.4 });
      return;
    }
    const bounds = latLngs.reduce(
      (acc, [lat, lon]) => {
        acc.south = Math.min(acc.south, lat);
        acc.north = Math.max(acc.north, lat);
        acc.west = Math.min(acc.west, lon);
        acc.east = Math.max(acc.east, lon);
        return acc;
      },
      { south: 90, north: -90, west: 180, east: -180 }
    );
    map.fitBounds(
      [
        [bounds.south, bounds.west],
        [bounds.north, bounds.east],
      ],
      { maxZoom: 14, padding: [40, 40], duration: 0.4 }
    );
  }, [map, markers]);
  return null;
}

function unitRadius(units: number): number {
  return Math.max(10, Math.min(40, 10 + units * 6));
}

function unitColor(units: number): string {
  if (units >= 3) return '#ef4444';
  if (units === 2) return '#f59e0b';
  return '#22c55e';
}

type PatrolMapProps = {
  markers: PatrolMapMarker[];
};

export default function PatrolMap({ markers }: PatrolMapProps) {
  return (
    <MapContainer
      center={NYC_CENTER}
      zoom={ZOOM}
      style={{ height: '100%', width: '100%' }}
      scrollWheelZoom
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <AutoFit markers={markers} />
      {markers.map((m) => (
        <CircleMarker
          key={m.zone_id}
          center={[m.lat, m.lon]}
          radius={unitRadius(m.units)}
          pathOptions={{
            color: unitColor(m.units),
            fillColor: unitColor(m.units),
            fillOpacity: 0.45,
            weight: 2,
          }}
        >
          <Tooltip direction="top" offset={[0, -5]}>
            <strong>{m.name}</strong> — {m.units} unit{m.units === 1 ? '' : 's'}
          </Tooltip>
          <Popup>
            <strong>{m.name}</strong>
            <br />
            <small>{m.zone_type}</small>
            <br />
            Units: {m.units}
            <br />
            Priority: {m.priority_score.toFixed(2)}
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
