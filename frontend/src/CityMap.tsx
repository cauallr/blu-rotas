import { useEffect, useMemo, useRef } from 'react';
import maplibregl, { type Map as MapLibreMap } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { AccessPoint, FeatureCollection, GraphOverlay, GraphVertex, Light, Road, RoadNetwork, Selection, Snapshot, Vehicle } from './types';
import { motionAlongLane } from './vehicleMotion';

export type MapPoint = { coordinates: [number, number]; label: string; role: 'origin' | 'destination' | 'waypoint' };
type Props = {
  network: RoadNetwork; baseRoads: FeatureCollection; places: FeatureCollection;
  snapshot: Snapshot | null; selection: Selection; selectedRoadId: string | null; tool: string;
  customPoints: MapPoint[]; previewRoute: string[];
  theme: 'light' | 'dark'; showRoute: boolean; showPreviousRoute: boolean;
  routePulseToken: string | null;
  followVehicleId: string | null; onStopFollow: () => void;
  graphOverlay: GraphOverlay | null; graphShowVertices: boolean; graphShowArcs: boolean;
  graphShowIds: boolean; graphShowWeights: boolean; graphComponent: number | null;
  graphPath: string[]; graphSelectedId: string | null;
  accessPoints: AccessPoint[]; onGraphVertex: (vertex: GraphVertex) => void;
  onAccessClick: (coordinates: [number, number]) => void;
  onBuildClick: (coordinates: [number, number]) => void;
  onSignalClick: (coordinates: [number, number]) => void;
  buildPoints: [number, number][];
  onSelect: (selected: Selection) => void;
  onMapClick: (coordinates: [number, number]) => void;
  onRoadCandidates: (roads: Road[]) => void;
  onRoadSelect: (road: Road) => void;
};
const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
const collection = (features: GeoJSON.Feature[]): FeatureCollection => ({ type: 'FeatureCollection', features });
type VehiclePosition = { coordinates: [number, number]; lane?: string };
const trafficColors = { red: '#fa6877', yellow: '#ffc06b', green: '#54dfbc' };
const carPalette: [string, string][] = [['mint', '#4de1cc'], ['coral', '#f27e8b'], ['amber', '#f7c271'], ['blue', '#77a8ed'], ['violet', '#b995ef'], ['white', '#edf5f2']];
function colorKey(value: string): string {
  const match = /^#([0-9a-f]{6})$/i.exec(value);
  if (!match) return 'mint';
  return carPalette.find(([, hex]) => hex.toLowerCase() === value.toLowerCase())?.[0] || match[1].toLowerCase();
}

function addCarImage(map: MapLibreMap, key: string, color: string) {
    if (map.hasImage(`car-${key}`)) return;
    const canvas = document.createElement('canvas'); canvas.width = 72; canvas.height = 112;
    const ctx = canvas.getContext('2d')!;
    ctx.shadowColor = '#0009'; ctx.shadowBlur = 8;
    ctx.fillStyle = '#14272e'; ctx.beginPath(); ctx.roundRect(10, 4, 52, 104, 18); ctx.fill();
    ctx.shadowBlur = 0; ctx.fillStyle = color; ctx.beginPath(); ctx.roundRect(14, 9, 44, 94, 14); ctx.fill();
    ctx.fillStyle = '#203843'; ctx.beginPath(); ctx.roundRect(18, 26, 36, 19, 5); ctx.fill();
    ctx.beginPath(); ctx.roundRect(18, 72, 36, 16, 5); ctx.fill();
    ctx.fillStyle = '#f7eee1'; ctx.fillRect(19, 12, 10, 5); ctx.fillRect(43, 12, 10, 5);
    ctx.fillStyle = '#e75f62'; ctx.fillRect(19, 96, 10, 4); ctx.fillRect(43, 96, 10, 4);
    map.addImage(`car-${key}`, ctx.getImageData(0, 0, 72, 112), { pixelRatio: 3 });
}

function fitRoads(map: MapLibreMap, roads: FeatureCollection) {
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
  for (const feature of roads.features) if (feature.geometry.type === 'LineString')
    for (const point of feature.geometry.coordinates) {
      west = Math.min(west, point[0]); east = Math.max(east, point[0]);
      south = Math.min(south, point[1]); north = Math.max(north, point[1]);
    }
  if (!Number.isFinite(west)) return;
  map.fitBounds([[west, south], [east, north]], { padding: 58, maxZoom: 15.5, duration: 550 });
}

function addTrafficIcons(map: MapLibreMap) {
  for (const [key, color] of carPalette) {
    addCarImage(map, key, color);
  }
  for (const aspect of ['closed', 'open', 'attention', 'mixed']) {
    const canvas = document.createElement('canvas');
    canvas.width = 44; canvas.height = 72;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = '#10191e'; ctx.strokeStyle = '#8ca8a8'; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.roundRect(3, 3, 38, 66, 11); ctx.fill(); ctx.stroke();
    for (const [index, color] of Object.entries(trafficColors).entries()) {
      const active = aspect === 'mixed' ? color[0] !== 'yellow' :
        aspect === 'closed' ? color[0] === 'red' :
        aspect === 'open' ? color[0] === 'green' : color[0] === 'yellow';
      ctx.beginPath(); ctx.arc(22, 16 + index * 20, 7, 0, Math.PI * 2);
      ctx.fillStyle = active ? color[1] : '#304249'; ctx.fill();
    }
    map.addImage(`traffic-${aspect}`, ctx.getImageData(0, 0, 44, 72), { pixelRatio: 2 });
  }
  const arrow = document.createElement('canvas');
  arrow.width = 32; arrow.height = 24;
  const ctx = arrow.getContext('2d')!;
  ctx.strokeStyle = '#10272d'; ctx.lineWidth = 7; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.beginPath(); ctx.moveTo(3, 12); ctx.lineTo(26, 12); ctx.moveTo(19, 5); ctx.lineTo(27, 12); ctx.lineTo(19, 19); ctx.stroke();
  ctx.strokeStyle = '#c7f1e6'; ctx.lineWidth = 4;
  ctx.beginPath(); ctx.moveTo(3, 12); ctx.lineTo(26, 12); ctx.moveTo(19, 5); ctx.lineTo(27, 12); ctx.lineTo(19, 19); ctx.stroke();
  map.addImage('direction-arrow', ctx.getImageData(0, 0, 32, 24), { pixelRatio: 2 });
}

function lineDistance(map: MapLibreMap, point: maplibregl.Point, feature: GeoJSON.Feature): number {
  if (feature.geometry.type !== 'LineString') return Infinity;
  let best = Infinity;
  const coords = feature.geometry.coordinates;
  for (let index = 0; index < coords.length - 1; index++) {
    const a = map.project(coords[index] as [number, number]);
    const b = map.project(coords[index + 1] as [number, number]);
    const dx = b.x - a.x, dy = b.y - a.y;
    const ratio = Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / Math.max(1, dx * dx + dy * dy)));
    best = Math.min(best, Math.hypot(point.x - a.x - ratio * dx, point.y - a.y - ratio * dy));
  }
  return best;
}

export default function CityMap(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const animation = useRef<number | null>(null);
  const previous = useRef<{ time: number; runId: number }>({ time: -1, runId: -1 });
  const rendered = useRef(new Map<string, VehiclePosition>());
  const followLast = useRef<string | null>(null);
  const followStartedAt = useRef(0);
  const fittedCity = useRef<string | null | undefined>(undefined);
  const latest = useRef(props);
  latest.current = props;
  const laneShapes = useMemo(() => new Map((props.network.lanes?.features || [])
    .filter(lane => lane.id != null && lane.geometry.coordinates.length > 1)
    .map(lane => [String(lane.id), lane.geometry.coordinates])), [props.network.lanes]);

  useEffect(() => {
    if (!container.current) return;
    const instance = new maplibregl.Map({ container: container.current,
      center: [-49.0745, -26.9135], zoom: 14.3, minZoom: 11, maxZoom: 19,
      style: { version: 8, glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
        sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#101c25' } }] },
      attributionControl: false });
    map.current = instance;
    const resizeObserver = new ResizeObserver(() => instance.resize());
    resizeObserver.observe(container.current);
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-left');
    instance.on('load', () => {
      addTrafficIcons(instance);
      for (const source of ['base', 'roads', 'lanes', 'places', 'vehicles', 'lights', 'signal-movements', 'signal-approaches', 'selected-movement', 'route', 'previous-route', 'route-pins', 'selected-car', 'congestion', 'blocked', 'partial', 'selected-road', 'hover-road', 'custom-route', 'custom-points', 'graph-vertices', 'graph-arcs', 'graph-path', 'graph-selected', 'access-points', 'build-preview', 'build-points']) {
        instance.addSource(source, { type: 'geojson', data: empty });
      }
      instance.addSource('vehicles-clusters', { type: 'geojson', data: empty, cluster: true, clusterRadius: 44, clusterMaxZoom: 14 });
      (instance.getSource('base') as maplibregl.GeoJSONSource).setData(latest.current.baseRoads);
      (instance.getSource('roads') as maplibregl.GeoJSONSource).setData(collection(latest.current.network.features));
      (instance.getSource('lanes') as maplibregl.GeoJSONSource).setData(latest.current.network.lanes || empty);
      (instance.getSource('places') as maplibregl.GeoJSONSource).setData(latest.current.places);
      if (latest.current.baseRoads.features.length) {
        fitRoads(instance, latest.current.baseRoads);
        fittedCity.current = latest.current.snapshot?.city_id ?? null;
      }
      instance.addLayer({ id: 'road-casing', type: 'line', source: 'base', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#29414b', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1.8, 17, 10] } });
      instance.addLayer({ id: 'road-surface', type: 'line', source: 'base', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': ['case', ['boolean', ['get', 'fictional'], false], '#ac8de8', ['match', ['get', 'highway'], 'primary', '#688795', 'secondary', '#5f7e8a', 'trunk', '#71929c', '#526c77']], 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1, 17, 6] } });
      instance.addLayer({ id: 'bridge-accent', type: 'line', source: 'base', filter: ['==', ['get', 'bridge'], 'yes'],
        paint: { 'line-color': '#eabf78', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1, 17, 2.5], 'line-opacity': 0.9 } });
      instance.addLayer({ id: 'lane-surface', type: 'line', source: 'lanes', minzoom: 14.5, layout: { 'line-join': 'round' },
        paint: {
          'line-color': latest.current.theme === 'light' ? '#ffffff' : '#688795',
          'line-opacity': ['interpolate', ['linear'], ['zoom'], 14.5, 0.55, 16, 1],
          'line-width': ['interpolate', ['exponential', 2], ['zoom'], 14.5, 1,
            16, ['*', ['number', ['get', 'width_m'], 3.2], 0.88],
            19, ['*', ['number', ['get', 'width_m'], 3.2], 7.04]],
        } });
      instance.addLayer({ id: 'congestion-lines', type: 'line', source: 'congestion', minzoom: 13,
        paint: { 'line-color': ['get', 'color'], 'line-width': ['interpolate', ['linear'], ['zoom'], 13, 2, 17, 5], 'line-opacity': 0.8 } });
      instance.addLayer({ id: 'road-direction', type: 'symbol', source: 'roads', minzoom: 15.5,
        layout: { 'symbol-placement': 'line', 'symbol-spacing': 90, 'icon-image': 'direction-arrow',
          'icon-rotation-alignment': 'map', 'icon-keep-upright': false,
          'icon-size': ['interpolate', ['linear'], ['zoom'], 15.5, 0.75, 18, 1.2] } });
      instance.addLayer({ id: 'roads-hit', type: 'line', source: 'roads', paint: { 'line-color': '#ffffff', 'line-width': 20, 'line-opacity': 0.01 } });
      instance.addLayer({ id: 'road-hover', type: 'line', source: 'hover-road', paint: { 'line-color': '#a6d3d3', 'line-width': 8, 'line-opacity': 0.55 } });
      instance.addLayer({ id: 'selected-road', type: 'line', source: 'selected-road', paint: { 'line-color': '#f4b36b', 'line-width': 8, 'line-opacity': 0.95 } });
      instance.addLayer({ id: 'partial-line', type: 'line', source: 'partial', paint: { 'line-color': '#f5b96f', 'line-width': 7, 'line-dasharray': [1.2, 0.8] } });
      instance.addLayer({ id: 'previous-route-line', type: 'line', source: 'previous-route', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#bb95f7', 'line-width': 7, 'line-opacity': 0.85, 'line-dasharray': [1.3, 0.8] } });
      instance.addLayer({ id: 'route-casing', type: 'line', source: 'route', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#12363b', 'line-width': 11 } });
      instance.addLayer({ id: 'route-line', type: 'line', source: 'route', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#58ddc5', 'line-width': 7, 'line-color-transition': { duration: 450 }, 'line-width-transition': { duration: 450 } } });
      instance.addLayer({ id: 'custom-route-line', type: 'line', source: 'custom-route', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#9ee7d6', 'line-width': 5, 'line-dasharray': [2, 0.8] } });
      instance.addLayer({ id: 'blocked-glow', type: 'line', source: 'blocked', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#ff334e', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 15, 17, 26], 'line-opacity': 0.28 } });
      instance.addLayer({ id: 'blocked-casing', type: 'line', source: 'blocked', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#7d1428', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 9, 17, 17], 'line-opacity': 0.98 } });
      instance.addLayer({ id: 'blocked-line', type: 'line', source: 'blocked', layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#ff334e', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 6, 17, 12], 'line-opacity': 1 } });
      instance.addLayer({ id: 'road-labels', type: 'symbol', source: 'base', minzoom: 15, layout: { 'symbol-placement': 'line', 'text-field': ['get', 'name'], 'text-size': 10, 'text-font': ['Open Sans Regular'] }, paint: { 'text-color': '#9db5bb', 'text-halo-color': '#101c25', 'text-halo-width': 2 } });
      instance.addLayer({ id: 'places-labels', type: 'symbol', source: 'places', layout: { 'text-field': ['get', 'name'], 'text-size': 15, 'text-font': ['Open Sans Regular'] }, paint: { 'text-color': '#a4c1c0', 'text-halo-color': '#101c25', 'text-halo-width': 3 } });
      instance.addLayer({ id: 'lights-dots', type: 'circle', source: 'lights', maxzoom: 15,
        filter: ['!=', ['get', 'aspect'], 'mixed'],
        paint: { 'circle-radius': 5, 'circle-color': ['match', ['get', 'aspect'],
          'closed', '#fa6877', 'open', '#54dfbc', 'attention', '#ffc06b', '#fa6877'],
          'circle-stroke-color': '#122126', 'circle-stroke-width': 2 } });
      instance.addLayer({ id: 'lights-mixed-red', type: 'circle', source: 'lights', maxzoom: 15,
        filter: ['==', ['get', 'aspect'], 'mixed'],
        paint: { 'circle-radius': 3.5, 'circle-color': '#fa6877', 'circle-translate': [-3.5, 0],
          'circle-stroke-color': '#122126', 'circle-stroke-width': 1 } });
      instance.addLayer({ id: 'lights-mixed-half', type: 'circle', source: 'lights', maxzoom: 15,
        filter: ['==', ['get', 'aspect'], 'mixed'],
        paint: { 'circle-radius': 3.5, 'circle-color': '#54dfbc', 'circle-translate': [3.5, 0],
          'circle-stroke-color': '#122126', 'circle-stroke-width': 1 } });
      instance.addLayer({ id: 'lights-icon', type: 'symbol', source: 'lights', minzoom: 15, maxzoom: 16,
        layout: { 'icon-image': ['concat', 'traffic-', ['get', 'aspect']], 'icon-allow-overlap': true, 'icon-size': ['interpolate', ['linear'], ['zoom'], 13.7, 0.75, 16, 1] } });
      instance.addLayer({ id: 'signal-approaches', type: 'line', source: 'signal-approaches', minzoom: 16,
        layout: { 'line-cap': 'round' }, paint: { 'line-color': ['match', ['get', 'aspect'],
          'closed', '#fa6877', 'attention', '#ffc06b', '#54dfbc'],
          'line-width': ['interpolate', ['linear'], ['zoom'], 16, 3, 18, 7], 'line-opacity': 0.9 } });
      instance.addLayer({ id: 'signal-movements', type: 'circle', source: 'signal-movements', minzoom: 16,
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 16, 5, 18, 8],
          'circle-color': ['match', ['get', 'aspect'], 'closed', '#fa6877', 'attention', '#ffc06b', '#54dfbc'],
          'circle-stroke-color': '#102126', 'circle-stroke-width': 2 } });
      instance.addLayer({ id: 'selected-movement', type: 'circle', source: 'selected-movement', minzoom: 16,
        paint: { 'circle-radius': 12, 'circle-color': '#ffffff', 'circle-opacity': 0,
          'circle-stroke-color': '#ffffff', 'circle-stroke-width': 3 } });
      instance.addLayer({ id: 'vehicles-cluster-bubbles', type: 'circle', source: 'vehicles-clusters', maxzoom: 14.5,
        filter: ['has', 'point_count'], paint: { 'circle-radius': ['step', ['get', 'point_count'], 11, 10, 15, 50, 21],
          'circle-color': '#4dd9c3', 'circle-opacity': 0.85, 'circle-stroke-color': '#15343b', 'circle-stroke-width': 2 } });
      instance.addLayer({ id: 'vehicles-cluster-counts', type: 'symbol', source: 'vehicles-clusters', maxzoom: 14.5,
        filter: ['has', 'point_count'], layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 11, 'text-allow-overlap': true },
        paint: { 'text-color': '#10262b' } });
      instance.addLayer({ id: 'vehicles-distant', type: 'circle', source: 'vehicles-clusters', maxzoom: 14.5,
        filter: ['!', ['has', 'point_count']], paint: { 'circle-radius': 4, 'circle-color': ['get', 'color'],
          'circle-stroke-color': '#183037', 'circle-stroke-width': 1.5 } });
      instance.addLayer({ id: 'vehicles-circle', type: 'circle', source: 'vehicles', minzoom: 14.5, maxzoom: 17,
        paint: { 'circle-radius': 3,
          'circle-color': ['get', 'color'], 'circle-stroke-width': 1,
          'circle-stroke-color': ['match', ['get', 'state'], 'at_signal', '#ffc06b', 'congested', '#fa6877', '#132a2e'] } });
      instance.addLayer({ id: 'vehicles-car', type: 'symbol', source: 'vehicles', minzoom: 17,
        layout: { 'icon-image': ['concat', 'car-', ['get', 'colorKey']], 'icon-size': ['interpolate', ['exponential', 2], ['zoom'], 17, 0.25, 19, 1],
          'icon-anchor': 'top', 'icon-rotate': ['get', 'angle'], 'icon-rotation-alignment': 'map', 'icon-allow-overlap': true } });
      instance.addLayer({ id: 'selected-car-halo', type: 'circle', source: 'selected-car',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 9, 17, 17], 'circle-color': '#ffffff', 'circle-opacity': 0.08, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 3 } });
      instance.addLayer({ id: 'route-pins-circle', type: 'circle', source: 'route-pins',
        paint: { 'circle-radius': 10, 'circle-color': ['match', ['get', 'role'], 'origin', '#58ddc5', '#f2878d'], 'circle-stroke-color': '#113038', 'circle-stroke-width': 3 } });
      instance.addLayer({ id: 'route-pins-label', type: 'symbol', source: 'route-pins',
        layout: { 'text-field': ['get', 'label'], 'text-size': 12, 'text-offset': [0, -2.1], 'text-font': ['Open Sans Regular'], 'text-allow-overlap': true },
        paint: { 'text-color': '#ffffff', 'text-halo-color': '#10262b', 'text-halo-width': 2 } });
      if (latest.current.theme === 'light') {
        instance.setPaintProperty('background', 'background-color', '#e5eceb');
        instance.setPaintProperty('road-casing', 'line-color', '#b1c6c8');
        instance.setPaintProperty('road-surface', 'line-color', ['case', ['boolean', ['get', 'fictional'], false], '#ad8fe8', '#ffffff']);
        instance.setPaintProperty('road-labels', 'text-color', '#46616a');
        instance.setPaintProperty('road-labels', 'text-halo-color', '#ffffff');
        instance.setPaintProperty('places-labels', 'text-color', '#415f66');
        instance.setPaintProperty('places-labels', 'text-halo-color', '#e5eceb');
      }
      instance.addLayer({ id: 'custom-points-circle', type: 'circle', source: 'custom-points', paint: { 'circle-radius': 9,
        'circle-color': ['match', ['get', 'role'], 'origin', '#56dfba', 'destination', '#f27e8b', '#f7c271'],
        'circle-stroke-color': '#10262b', 'circle-stroke-width': 3 } });
      instance.addLayer({ id: 'custom-points-label', type: 'symbol', source: 'custom-points', layout: { 'text-field': ['get', 'label'], 'text-size': 11, 'text-offset': [0, -2], 'text-font': ['Open Sans Regular'] }, paint: { 'text-color': '#f1f6f3', 'text-halo-color': '#10262b', 'text-halo-width': 2 } });
      instance.addLayer({ id: 'graph-arcs-line', type: 'line', source: 'graph-arcs', minzoom: 14,
        paint: { 'line-color': '#9f87ea', 'line-width': 1.5, 'line-opacity': 0.6 } });
      instance.addLayer({ id: 'graph-weights', type: 'symbol', source: 'graph-arcs', minzoom: 17,
        layout: { 'symbol-placement': 'line-center', 'text-field': ['to-string', ['get', 'weight_s']], 'text-size': 9, 'text-font': ['Open Sans Regular'] },
        paint: { 'text-color': '#d5c5ff', 'text-halo-color': '#253144', 'text-halo-width': 2 } });
      instance.addLayer({ id: 'graph-path-line', type: 'line', source: 'graph-path',
        paint: { 'line-color': '#f8c674', 'line-width': 8, 'line-opacity': 0.9 } });
      instance.addLayer({ id: 'graph-vertex-dots', type: 'circle', source: 'graph-vertices', minzoom: 15.5,
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'],
          14, ['case', ['==', ['get', 'intersection_type'], 'ponto de acesso'], 8, 2],
          17, ['case', ['==', ['get', 'intersection_type'], 'ponto de acesso'], 8, 5]],
          'circle-color': ['case', ['==', ['get', 'intersection_type'], 'ponto de acesso'], '#ffcc67',
            ['match', ['%', ['get', 'component'], 4], 0, '#9c88ea', 1, '#f3af73', 2, '#7bd9c3', '#ed89a2']],
          'circle-stroke-color': '#1b2940', 'circle-stroke-width': 1 } });
      instance.addLayer({ id: 'graph-vertex-ids', type: 'symbol', source: 'graph-vertices', minzoom: 17,
        layout: { 'text-field': ['get', 'id'], 'text-size': 10, 'text-offset': [0, -1.2], 'text-font': ['Open Sans Regular'] },
        paint: { 'text-color': '#e7dcff', 'text-halo-color': '#18253b', 'text-halo-width': 2 } });
      instance.addLayer({ id: 'graph-selected-ring', type: 'circle', source: 'graph-selected',
        paint: { 'circle-radius': 10, 'circle-color': '#ffffff', 'circle-opacity': 0,
          'circle-stroke-color': '#ffffff', 'circle-stroke-width': 3 } });
      instance.addLayer({ id: 'access-point-dots', type: 'circle', source: 'access-points',
        paint: { 'circle-radius': 8, 'circle-color': '#f7c271', 'circle-stroke-color': '#392a1e', 'circle-stroke-width': 2 } });
      instance.addLayer({ id: 'access-point-labels', type: 'symbol', source: 'access-points', minzoom: 15,
        layout: { 'text-field': ['get', 'name'], 'text-size': 11, 'text-offset': [0, -1.8], 'text-font': ['Open Sans Regular'] },
        paint: { 'text-color': '#ffe9b9', 'text-halo-color': '#2c2b33', 'text-halo-width': 2 } });
      instance.addLayer({ id: 'build-preview-line', type: 'line', source: 'build-preview',
        paint: { 'line-color': '#bd90f7', 'line-width': 6, 'line-dasharray': [1, 0.7] } });
      instance.addLayer({ id: 'build-preview-points', type: 'circle', source: 'build-points',
        paint: { 'circle-radius': 10, 'circle-color': '#d7b5ff', 'circle-stroke-color': '#342645', 'circle-stroke-width': 3 } });

      const roadAt = (point: maplibregl.Point) => {
        const box: [[number, number], [number, number]] = [[point.x - 12, point.y - 12], [point.x + 12, point.y + 12]];
        const hits = instance.queryRenderedFeatures(box, { layers: ['roads-hit'] }) as unknown as GeoJSON.Feature[];
        const unique = new Map<string, GeoJSON.Feature>();
        for (const feature of hits) unique.set(String(feature.properties?.id), feature);
        return [...unique.values()].filter(feature => lineDistance(instance, point, feature) <= 9)
          .sort((a, b) => lineDistance(instance, point, a) - lineDistance(instance, point, b)).slice(0, 6);
      };
      instance.on('mousemove', event => {
        const tool = latest.current.tool;
        if (tool !== 'road' && tool !== 'select') return;
        const hit = roadAt(event.point)[0];
        (instance.getSource('hover-road') as maplibregl.GeoJSONSource).setData(hit ? collection([hit]) : empty);
        instance.getCanvas().style.cursor = hit ? 'pointer' : '';
      });
      instance.on('click', event => {
        const state = latest.current;
        if (state.tool === 'car') { state.onMapClick([event.lngLat.lng, event.lngLat.lat]); return; }
        if (state.tool === 'point') { state.onAccessClick([event.lngLat.lng, event.lngLat.lat]); return; }
        if (state.tool === 'build') { state.onBuildClick([event.lngLat.lng, event.lngLat.lat]); return; }
        if (state.tool === 'new_signal') { state.onSignalClick([event.lngLat.lng, event.lngLat.lat]); return; }
        const box: [[number, number], [number, number]] = [[event.point.x - 11, event.point.y - 11], [event.point.x + 11, event.point.y + 11]];
        if (state.tool === 'graph') {
          const vertexHit = instance.queryRenderedFeatures(box, { layers: ['graph-vertex-dots'] })[0];
          if (vertexHit) {
            const vertex = state.graphOverlay?.vertices.features.find(item => item.properties?.id === vertexHit.properties?.id);
            if (vertex) state.onGraphVertex({ ...vertex.properties, coordinates: (vertex.geometry as GeoJSON.Point).coordinates } as GraphVertex);
          }
          return;
        }
        const clusterHit = instance.queryRenderedFeatures(box, { layers: ['vehicles-cluster-bubbles'] })[0];
        if ((state.tool === 'vehicle' || state.tool === 'select') && clusterHit) {
          const coordinates = (clusterHit.geometry as GeoJSON.Point).coordinates as [number, number];
          instance.easeTo({ center: coordinates, zoom: Math.min(16, instance.getZoom() + 2), duration: 450 });
          return;
        }
        const vehicleHit = instance.queryRenderedFeatures(box, { layers: ['vehicles-car', 'vehicles-circle', 'vehicles-distant'] })[0];
        const movementHit = instance.queryRenderedFeatures(box, { layers: ['signal-movements'] })[0];
        const lightHit = instance.queryRenderedFeatures(box, { layers: ['lights-icon', 'lights-mixed-half', 'lights-mixed-red', 'lights-dots'] })[0];
        const roadHits = roadAt(event.point);
        if ((state.tool === 'vehicle' || state.tool === 'select') && vehicleHit) {
          const value = state.snapshot?.vehicles.find((item: Vehicle) => item.id === vehicleHit.properties?.id);
          if (value) { state.onSelect({ kind: 'vehicle', value }); return; }
        }
        if ((state.tool === 'light' || state.tool === 'select') && movementHit) {
          const value = state.snapshot?.lights.find((item: Light) => item.id === movementHit.properties?.tls_id);
          if (value) { state.onSelect({ kind: 'light', value, movement_id: movementHit.properties?.id }); return; }
        }
        if ((state.tool === 'light' || state.tool === 'select') && lightHit) {
          const value = state.snapshot?.lights.find((item: Light) => item.id === lightHit.properties?.id);
          if (value) { state.onSelect({ kind: 'light', value }); return; }
        }
        if ((state.tool === 'road' || state.tool === 'select') && roadHits.length) {
          const options = roadHits.map(feature => feature.properties as Road);
          state.onRoadCandidates(options);
          if (state.tool === 'road') state.onRoadSelect(options[0]);
          else state.onSelect({ kind: 'road', value: options[0] });
        }
      });
      instance.on('dragstart', () => latest.current.onStopFollow());
      instance.getCanvas().addEventListener('wheel', () => latest.current.onStopFollow(), { passive: true });
      instance.getContainer().querySelectorAll('.maplibregl-ctrl-zoom-in, .maplibregl-ctrl-zoom-out')
        .forEach(button => button.addEventListener('click', () => latest.current.onStopFollow()));
    });
    return () => { resizeObserver.disconnect(); if (animation.current !== null) cancelAnimationFrame(animation.current); instance.remove(); map.current = null; };
  }, []);

  useEffect(() => { (map.current?.getSource('base') as maplibregl.GeoJSONSource | undefined)?.setData(props.baseRoads); }, [props.baseRoads]);
  useEffect(() => {
    const cityId = props.snapshot?.city_id ?? null;
    if (!map.current?.getSource('base') || !props.baseRoads.features.length || fittedCity.current === cityId) return;
    fitRoads(map.current, props.baseRoads);
    fittedCity.current = cityId;
  }, [props.snapshot?.city_id, props.baseRoads]);
  useEffect(() => {
    (map.current?.getSource('roads') as maplibregl.GeoJSONSource | undefined)?.setData(collection(props.network.features));
    (map.current?.getSource('lanes') as maplibregl.GeoJSONSource | undefined)?.setData(props.network.lanes || empty);
  }, [props.network]);
  useEffect(() => {
    const instance = map.current;
    if (!props.routePulseToken || !instance?.getLayer('route-line')) return;
    instance.setPaintProperty('route-line', 'line-color', '#f7c271');
    instance.setPaintProperty('route-line', 'line-width', 10);
    const timer = window.setTimeout(() => {
      if (!map.current?.getLayer('route-line')) return;
      map.current.setPaintProperty('route-line', 'line-color', '#58ddc5');
      map.current.setPaintProperty('route-line', 'line-width', 7);
    }, 1300);
    return () => window.clearTimeout(timer);
  }, [props.routePulseToken]);
  useEffect(() => { (map.current?.getSource('places') as maplibregl.GeoJSONSource | undefined)?.setData(props.places); }, [props.places]);
  useEffect(() => {
    const instance = map.current;
    // O fundo existe antes de as camadas do mapa terminarem de carregar.
    if (!instance?.getLayer('custom-route-line')) return;
    instance.setPaintProperty('custom-route-line', 'line-color', props.tool === 'vehicle' ? '#f7c271' : '#9ee7d6');
    const light = props.theme === 'light';
    instance.setPaintProperty('background', 'background-color', light ? '#e5eceb' : '#101c25');
    instance.setPaintProperty('road-casing', 'line-color', light ? '#b1c6c8' : '#29414b');
    instance.setPaintProperty('road-surface', 'line-color', light ? ['case', ['boolean', ['get', 'fictional'], false], '#ad8fe8', '#ffffff'] : ['case', ['boolean', ['get', 'fictional'], false], '#ac8de8', ['match', ['get', 'highway'], 'primary', '#688795', 'secondary', '#5f7e8a', 'trunk', '#71929c', '#526c77']]);
    instance.setPaintProperty('lane-surface', 'line-color', light ? '#ffffff' : '#688795');
    instance.setPaintProperty('road-labels', 'text-color', light ? '#46616a' : '#9db5bb');
    instance.setPaintProperty('road-labels', 'text-halo-color', light ? '#ffffff' : '#101c25');
    instance.setPaintProperty('places-labels', 'text-color', light ? '#415f66' : '#a4c1c0');
    instance.setPaintProperty('places-labels', 'text-halo-color', light ? '#e5eceb' : '#101c25');
  }, [props.theme, props.baseRoads]);
  useEffect(() => {
    if (!map.current || !props.followVehicleId || followLast.current === props.followVehicleId) { followLast.current = props.followVehicleId; return; }
    const vehicle = props.snapshot?.vehicles.find(item => item.id === props.followVehicleId);
    if (vehicle) map.current.easeTo({ center: vehicle.coordinates, zoom: Math.max(16, map.current.getZoom()), duration: 550 });
    followStartedAt.current = performance.now();
    followLast.current = props.followVehicleId;
  }, [props.followVehicleId, props.snapshot?.run_id]);
  useEffect(() => {
    const instance = map.current;
    if (!instance?.getSource('vehicles')) return;
    const vehicles = (props.snapshot?.vehicles || []).map(vehicle => ({ type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: vehicle.coordinates },
      properties: { id: vehicle.id, lane: vehicle.lane_id, state: vehicle.state, angle: vehicle.angle, color: vehicle.color || '#4de1cc', colorKey: colorKey(vehicle.color || '#4de1cc') } }));
    for (const vehicle of vehicles) addCarImage(instance, vehicle.properties.colorKey, vehicle.properties.color);
    (instance.getSource('vehicles-clusters') as maplibregl.GeoJSONSource).setData(collection(vehicles));
    const source = instance.getSource('vehicles') as maplibregl.GeoJSONSource;
    if (!props.snapshot?.connected) {
      if (animation.current !== null) cancelAnimationFrame(animation.current);
      source.setData(empty);
      rendered.current.clear();
      previous.current = { time: -1, runId: -1 };
    } else if (props.snapshot.sim_time !== previous.current.time || props.snapshot.run_id !== previous.current.runId) {
      if (animation.current !== null) cancelAnimationFrame(animation.current);
      const reset = props.snapshot.run_id !== previous.current.runId || props.snapshot.sim_time < previous.current.time;
      const start = performance.now();
      const elapsedSim = Math.max(0, props.snapshot.sim_time - previous.current.time);
      const frameMs = props.snapshot.running ? Math.max(80, Math.min(550, elapsedSim * 1000 / Math.max(0.25, props.snapshot.speed))) : 0;
      const trajectories = vehicles.map(feature => {
        const from = reset ? undefined : rendered.current.get(feature.properties.id);
        const lane = feature.properties.lane;
        const shape = lane && from?.lane === lane ? laneShapes.get(lane) : undefined;
        // Na troca de faixa, a posição confirmada pelo SUMO mantém o carro sobre a pista.
        return frameMs && shape && from ? motionAlongLane(shape, from.coordinates, feature.geometry.coordinates) : null;
      });
      const frame = (now: number) => {
        const fraction = frameMs ? Math.min(1, (now - start) / frameMs) : 1;
        const positions = new Map<string, VehiclePosition>();
        const features = vehicles.map((feature, index) => {
          const position = trajectories[index]?.(fraction);
          const coordinates = position?.coordinates || feature.geometry.coordinates;
          positions.set(feature.properties.id, { coordinates, lane: feature.properties.lane });
          return position ? { ...feature, geometry: { type: 'Point' as const, coordinates },
            properties: { ...feature.properties, angle: position.angle } } : feature;
        });
        rendered.current = positions;
        source.setData(collection(features));
        const follow = latest.current.followVehicleId;
        const followedPosition = follow ? positions.get(follow) : undefined;
        if (followedPosition && now - followStartedAt.current > 600) instance.setCenter(followedPosition.coordinates);
        const selectedId = latest.current.selection?.kind === 'vehicle' ? latest.current.selection.value.id : null;
        const selectedPosition = selectedId ? positions.get(selectedId) : undefined;
        (instance.getSource('selected-car') as maplibregl.GeoJSONSource).setData(selectedPosition
          ? collection([{ type: 'Feature', geometry: { type: 'Point', coordinates: selectedPosition.coordinates }, properties: {} }]) : empty);
        if (fraction < 1) animation.current = requestAnimationFrame(frame);
      };
      animation.current = requestAnimationFrame(frame);
      previous.current = { time: props.snapshot.sim_time, runId: props.snapshot.run_id };
    }
    const lights = (props.snapshot?.lights || []).map(light => ({ type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: light.coordinates },
      properties: { id: light.id, aspect: light.aspect } }));
    (instance.getSource('lights') as maplibregl.GeoJSONSource).setData(collection(lights));
    const movements = (props.snapshot?.lights || []).flatMap(light => light.movements.map(movement => ({
      type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: movement.coordinates },
      properties: { id: movement.id, tls_id: light.id, aspect: movement.aspect } })));
    (instance.getSource('signal-movements') as maplibregl.GeoJSONSource).setData(collection(movements));
    const usedLanes = new Set<string>();
    const approaches = (props.snapshot?.lights || []).flatMap(light => light.movements.filter(movement => {
      if (!movement.show_approach || usedLanes.has(movement.incoming_lane)) return false;
      usedLanes.add(movement.incoming_lane); return true;
    }).map(movement => ({ type: 'Feature' as const,
      geometry: { type: 'LineString' as const, coordinates: movement.approach },
      properties: { aspect: movement.aspect } })));
    (instance.getSource('signal-approaches') as maplibregl.GeoJSONSource).setData(collection(approaches));
    const selectedMovementId = props.selection?.kind === 'light' ? props.selection.movement_id : undefined;
    const chosenMovement = selectedMovementId
      ? movements.find(movement => movement.properties.id === selectedMovementId) : null;
    (instance.getSource('selected-movement') as maplibregl.GeoJSONSource).setData(chosenMovement ? collection([chosenMovement]) : empty);
    const features = props.network.features;
    const activeRoute = props.selection?.kind === 'vehicle' ? props.selection.value.route : [];
    const previousRoute = props.selection?.kind === 'vehicle' ? props.selection.value.previous_route : [];
    const filtered = (ids: string[]) => {
      if (!ids.length) return empty;
      const wanted = new Set(ids);
      return collection(features.filter(feature => wanted.has(String(feature.properties?.id))));
    };
    (instance.getSource('route') as maplibregl.GeoJSONSource).setData(filtered(props.showRoute ? activeRoute : []));
    (instance.getSource('previous-route') as maplibregl.GeoJSONSource).setData(filtered(props.showPreviousRoute ? previousRoute : []));
    const selectedVehicle = props.selection?.kind === 'vehicle' ? props.selection.value : null;
    const selectedPosition = selectedVehicle && rendered.current.get(selectedVehicle.id);
    (instance.getSource('selected-car') as maplibregl.GeoJSONSource).setData(selectedPosition
      ? collection([{ type: 'Feature', geometry: { type: 'Point', coordinates: selectedPosition.coordinates }, properties: {} }]) : empty);
    (instance.getSource('route-pins') as maplibregl.GeoJSONSource).setData(selectedVehicle && props.showRoute
      ? collection([{ type: 'Feature', geometry: { type: 'Point', coordinates: selectedVehicle.origin_coordinates }, properties: { role: 'origin', label: 'Partida' } },
          { type: 'Feature', geometry: { type: 'Point', coordinates: selectedVehicle.destination_coordinates }, properties: { role: 'destination', label: 'Destino' } }]) : empty);
    const slowIds = new Map((props.snapshot?.congestion || []).filter(item => item.count > 0).map(item => [item.id, item]));
    (instance.getSource('congestion') as maplibregl.GeoJSONSource).setData(collection(features.filter(feature => slowIds.has(String(feature.properties?.id))).map(feature => {
      const item = slowIds.get(String(feature.properties?.id))!;
      const limit = Number(feature.properties?.speed_kmh || 50) / 3.6;
      const ratio = item.speed / Math.max(1, limit);
      return { ...feature, properties: { ...feature.properties, color: ratio < 0.35 ? '#ef6b76' : ratio < 0.65 ? '#eeb566' : '#54dfbc' } };
    })));
    (instance.getSource('custom-route') as maplibregl.GeoJSONSource).setData(filtered(props.previewRoute));
    (instance.getSource('blocked') as maplibregl.GeoJSONSource).setData(filtered(props.snapshot?.blocked || []));
    (instance.getSource('partial') as maplibregl.GeoJSONSource).setData(filtered(props.snapshot?.partial || []));
    (instance.getSource('selected-road') as maplibregl.GeoJSONSource).setData(filtered(props.selectedRoadId ? [props.selectedRoadId] : []));
    (instance.getSource('custom-points') as maplibregl.GeoJSONSource).setData(collection(props.customPoints.map(point => ({
      type: 'Feature', geometry: { type: 'Point', coordinates: point.coordinates }, properties: { role: point.role, label: point.label } }))));
  }, [props.snapshot, props.selection, props.selectedRoadId, props.network, props.customPoints, props.previewRoute, props.showRoute, props.showPreviousRoute, laneShapes]);
  useEffect(() => {
    const instance = map.current;
    if (!instance?.getSource('graph-vertices')) return;
    const chosen = props.graphComponent;
    const vertexFeatures = props.graphOverlay?.vertices.features || [];
    const arcFeatures = props.graphOverlay?.arcs.features || [];
    (instance.getSource('graph-vertices') as maplibregl.GeoJSONSource).setData(collection(
      chosen === null ? vertexFeatures : vertexFeatures.filter(feature => feature.properties?.component === chosen)));
    (instance.getSource('graph-arcs') as maplibregl.GeoJSONSource).setData(collection(
      chosen === null ? arcFeatures : arcFeatures.filter(feature => feature.properties?.component === chosen)));
    (instance.getSource('graph-selected') as maplibregl.GeoJSONSource).setData(collection(
      vertexFeatures.filter(feature => feature.properties?.id === props.graphSelectedId)));
    const paths = new Set(props.graphPath);
    (instance.getSource('graph-path') as maplibregl.GeoJSONSource).setData(collection(
      props.network.features.filter(feature => paths.has(String(feature.properties?.id)))));
    (instance.getSource('access-points') as maplibregl.GeoJSONSource).setData(collection(props.accessPoints.map(point => ({
      type: 'Feature', geometry: { type: 'Point', coordinates: point.coordinates }, properties: { id: point.id, name: point.name } }))));
    (instance.getSource('build-points') as maplibregl.GeoJSONSource).setData(collection(props.buildPoints.map((coordinates, index) => ({
      type: 'Feature', geometry: { type: 'Point', coordinates }, properties: { index } }))));
    (instance.getSource('build-preview') as maplibregl.GeoJSONSource).setData(props.buildPoints.length >= 2
      ? collection([{ type: 'Feature', geometry: { type: 'LineString', coordinates: props.buildPoints }, properties: {} }]) : empty);
    for (const [layer, visible] of [['graph-vertex-dots', props.graphShowVertices], ['graph-vertex-ids', props.graphShowVertices && props.graphShowIds],
      ['graph-arcs-line', props.graphShowArcs], ['graph-weights', props.graphShowArcs && props.graphShowWeights]] as [string, boolean][]) {
      if (instance.getLayer(layer)) instance.setLayoutProperty(layer, 'visibility', visible ? 'visible' : 'none');
    }
  }, [props.graphOverlay, props.graphShowVertices, props.graphShowArcs, props.graphShowIds, props.graphShowWeights,
      props.graphComponent, props.graphPath, props.graphSelectedId, props.accessPoints, props.buildPoints, props.network]);
  return <div ref={container} className="city-map" aria-label="Mapa de Blumenau" />;
}
