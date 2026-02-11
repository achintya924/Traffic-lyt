'use client';

import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
// leaflet.heat expects L on window in UMD build
if (typeof window !== 'undefined') {
  (window as unknown as { L: typeof L }).L = L;
}
import 'leaflet.heat';
import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';

// Fix default marker icons in Next.js (leaflet uses file paths that break with bundlers)
const defaultIcon = L.icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});
L.Marker.prototype.options.icon = defaultIcon;

export type Violation = {
  id: number;
  lat: number;
  lon: number;
  occurred_at: string | null;
  violation_type: string | null;
};

export type HeatmapPoint = { lat: number; lon: number; count: number };

export type MapBounds = { south: number; north: number; west: number; east: number };

// NYC center
const NYC_CENTER: [number, number] = [40.7128, -74.006];
const ZOOM = 11;

function BoundsReporter({ onBoundsChange }: { onBoundsChange: (b: MapBounds) => void }) {
  const map = useMap();
  useEffect(() => {
    const report = () => {
      const b = map.getBounds();
      onBoundsChange({
        south: b.getSouth(),
        north: b.getNorth(),
        west: b.getWest(),
        east: b.getEast(),
      });
    };
    report();
    map.on('moveend', report);
    map.on('zoomend', report);
    return () => {
      map.off('moveend', report);
      map.off('zoomend', report);
    };
  }, [map, onBoundsChange]);
  return null;
}

function HeatmapLayer({ points }: { points: HeatmapPoint[] }) {
  const map = useMap();
  const layerRef = useRef<{ setLatLngs: (latlngs: [number, number, number][]) => void } | null>(null);
  useEffect(() => {
    const HeatLayer = (L as unknown as { heatLayer: (latlngs: [number, number, number][], options?: object) => { setLatLngs: (latlngs: [number, number, number][]) => void; addTo: (m: L.Map) => void } }).heatLayer;
    if (!HeatLayer) return;
    layerRef.current = HeatLayer([], { radius: 28, blur: 20 });
    (layerRef.current as unknown as { addTo: (m: L.Map) => void }).addTo(map);
    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current as unknown as L.Layer);
        layerRef.current = null;
      }
    };
  }, [map]);
  useEffect(() => {
    if (layerRef.current) {
      const latlngs: [number, number, number][] = points.map((p) => [p.lat, p.lon, p.count]);
      layerRef.current.setLatLngs(latlngs);
    }
  }, [points]);
  return null;
}

type ViolationsMapProps = {
  violations: Violation[];
  viewMode: 'markers' | 'heatmap';
  heatmapPoints: HeatmapPoint[];
  onBoundsChange: (b: MapBounds) => void;
};

export default function ViolationsMap({ violations, viewMode, heatmapPoints, onBoundsChange }: ViolationsMapProps) {
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
      <BoundsReporter onBoundsChange={onBoundsChange} />
      {viewMode === 'heatmap' && <HeatmapLayer points={heatmapPoints} />}
      {viewMode === 'markers' &&
        violations.map((v) => (
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
