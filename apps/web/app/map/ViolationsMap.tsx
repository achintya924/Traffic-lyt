'use client';

import 'leaflet/dist/leaflet.css';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';

// Fix default marker icons in Next.js (leaflet uses file paths that break with bundlers)
const defaultIcon = L.icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});
L.Marker.prototype.options.icon = defaultIcon;

type Violation = {
  id: number;
  lat: number;
  lon: number;
  occurred_at: string | null;
  violation_type: string | null;
};

// NYC center
const NYC_CENTER: [number, number] = [40.7128, -74.006];
const ZOOM = 11;

export default function ViolationsMap({ violations }: { violations: Violation[] }) {
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
      {violations.map((v) => (
        <Marker key={v.id} position={[v.lat, v.lon]}>
          <Popup>
            <strong>#{v.id}</strong>
            {v.violation_type && <><br />{v.violation_type}</>}
            {v.occurred_at && <><br /><small>{v.occurred_at}</small></>}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
