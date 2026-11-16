import { useEffect, useRef } from 'react';
import maplibregl, { type Map as MapLibreMap } from 'maplibre-gl';
import type { FeatureCollection } from './types';

export type ReplayFrame = { time: number; vehicles: { id: string; coordinates: [number, number]; angle: number; color: string; state: string; speed: number }[];
  lights: { id: string; coordinates: [number, number]; aspect: string }[]; active: number; completed: number; mean_speed: number };
const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
function showFrame(instance: MapLibreMap, frame: ReplayFrame | null) {
  (instance.getSource('cars') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: (frame?.vehicles || []).map(car => ({
    type: 'Feature', geometry: { type: 'Point', coordinates: car.coordinates }, properties: { id: car.id, color: car.color } })) });
  (instance.getSource('lights') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: (frame?.lights || []).map(light => ({
    type: 'Feature', geometry: { type: 'Point', coordinates: light.coordinates }, properties: { id: light.id, aspect: light.aspect } })) });
}

export default function ReplayMap({ roads, frame, theme }: { roads: FeatureCollection; frame: ReplayFrame | null; theme: 'dark' | 'light' }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const latestFrame = useRef(frame);
  latestFrame.current = frame;
  useEffect(() => {
    if (!container.current) return;
    const instance = new maplibregl.Map({ container: container.current, center: [-49.066, -26.917], zoom: 13.8,
      style: { version: 8, sources: {}, layers: [{ id: 'background', type: 'background',
        paint: { 'background-color': theme === 'dark' ? '#101c25' : '#e5eceb' } }] }, attributionControl: false });
    map.current = instance;
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    instance.on('load', () => {
      for (const source of ['roads', 'cars', 'lights']) instance.addSource(source, { type: 'geojson', data: empty });
      instance.addLayer({ id: 'road-casing', type: 'line', source: 'roads', layout: { 'line-cap': 'round' },
        paint: { 'line-color': theme === 'dark' ? '#29414b' : '#b1c6c8', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 2, 17, 10] } });
      instance.addLayer({ id: 'road-surface', type: 'line', source: 'roads', layout: { 'line-cap': 'round' },
        paint: { 'line-color': theme === 'dark' ? '#66818a' : '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1, 17, 6] } });
      instance.addLayer({ id: 'lights', type: 'circle', source: 'lights', paint: { 'circle-radius': 5,
        'circle-color': ['match', ['get', 'aspect'], 'closed', '#fa6877', 'attention', '#ffc06b', 'open', '#54dfbc', '#a989ed'],
        'circle-stroke-color': '#23313c', 'circle-stroke-width': 2 } });
      instance.addLayer({ id: 'cars', type: 'circle', source: 'cars', paint: { 'circle-radius': 6,
        'circle-color': ['get', 'color'], 'circle-stroke-color': '#1b3139', 'circle-stroke-width': 2 } });
      (instance.getSource('roads') as maplibregl.GeoJSONSource).setData(roads);
      showFrame(instance, latestFrame.current);
      const points = roads.features.flatMap(feature => feature.geometry.type === 'LineString' ? feature.geometry.coordinates : []);
      if (points.length) {
        const bounds = new maplibregl.LngLatBounds();
        points.forEach(point => bounds.extend(point as [number, number]));
        instance.fitBounds(bounds, { padding: 30, maxZoom: 15, duration: 0 });
      }
    });
    return () => { instance.remove(); map.current = null; };
  }, []);
  useEffect(() => {
    const instance = map.current;
    if (!instance?.getLayer('background')) return;
    const light = theme === 'light';
    instance.setPaintProperty('background', 'background-color', light ? '#e5eceb' : '#101c25');
    instance.setPaintProperty('road-casing', 'line-color', light ? '#b1c6c8' : '#29414b');
    instance.setPaintProperty('road-surface', 'line-color', light ? '#ffffff' : '#66818a');
  }, [theme]);
  useEffect(() => { (map.current?.getSource('roads') as maplibregl.GeoJSONSource | undefined)?.setData(roads); }, [roads]);
  useEffect(() => {
    const instance = map.current;
    if (!instance?.getSource('cars')) return;
    showFrame(instance, frame);
  }, [frame]);
  return <div className="replay-map" ref={container} aria-label="Replay de posições registradas pelo SUMO" />;
}
