import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, CarFront, Clock3, CloudRain, CloudSun, GitBranch, MapPin, MousePointer2, Pause, Play, Plus, RotateCcw, Route, Signal, SlidersHorizontal, TrafficCone, Zap, ChevronLeft, ChevronRight } from 'lucide-react';
import CityMap, { type MapPoint } from './CityMap';
import HelpTip from './HelpTip';
import type { AccessPoint, FeatureCollection, GraphOverlay, GraphVertex, Road, RouteOption, Selection, Snapshot } from './types';

type Act = (path: string, body?: object, reload?: boolean) => Promise<Snapshot | Record<string, unknown> | null>;
type Props = { network: FeatureCollection; baseRoads: FeatureCollection; places: FeatureCollection;
  snapshot: Snapshot | null; act: Act; busy: boolean; seed: number; theme: 'dark' | 'light'; setNotice: (message: string) => void;
  refreshCity: () => Promise<void> };
type Pick = 'origin' | 'destination' | 'waypoint' | 'none';
type Snapped = { coordinates: [number, number]; edge_id: string; name: string; position: number; distance_m: number };
type UrbanRoad = { id: string; name: string; origin_coordinates: [number, number]; destination_coordinates: [number, number];
  via?: [number, number][]; direction?: 'both' | 'forward' | 'reverse';
  oneway: boolean; speed_kmh: number; lanes: number; capacity_estimate: number; hypothetical_cost: number; length_m: number };
type UrbanNetwork = { active: string | null; scenarios: { id: string; name: string; network_version: string; roads: UrbanRoad[];
  road_edits?: { way_id: string; direction: string; lanes_forward: number; lanes_backward: number }[];
  signals?: { node_id: string; coordinates: [number, number] }[] }[] };
type RouteKey = RouteOption['key'];
const routeKeys: RouteKey[] = ['best', 'secondary', 'longer'];
const duration = (seconds = 0) => `${String(Math.floor(seconds / 3600)).padStart(2, '0')}:${String(Math.floor(seconds % 3600 / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
const clock = (hour = 0) => `${String(Math.floor(hour)).padStart(2, '0')}:${String(Math.floor((hour % 1) * 60)).padStart(2, '0')}`;
const number = (value = 0, digits = 0) => Number(value).toLocaleString('pt-BR', { maximumFractionDigits: digits });
const statusNames: Record<string, string> = { moving: 'Em trânsito', congested: 'Preso no trânsito', at_signal: 'Parado no semáforo', departing: 'Saindo', arrived: 'Chegou' };
const signalNames: Record<string, string> = { open: 'Verde', closed: 'Vermelho', attention: 'Amarelo', mixed: 'Misto' };

export default function CityView({ network, baseRoads, places, snapshot, act, busy, seed, theme, setNotice, refreshCity }: Props) {
  const [tool, setTool] = useState('select');
  const [selection, setSelection] = useState<Selection>(null);
  const [roadSelection, setRoadSelection] = useState<Road | null>(null);
  const [roadCandidates, setRoadCandidates] = useState<Road[]>([]);
  const [pick, setPick] = useState<Pick>('origin');
  const [origin, setOrigin] = useState<Snapped | null>(null);
  const [destination, setDestination] = useState<Snapped | null>(null);
  const [waypoints, setWaypoints] = useState<Snapped[]>([]);
  const [routeOptions, setRouteOptions] = useState<RouteOption[]>([]);
  const [routeChoice, setRouteChoice] = useState<RouteKey>('best');
  const [routeGroupCounts, setRouteGroupCounts] = useState<Record<RouteKey, number>>({ best: 1, secondary: 0, longer: 0 });
  const [routeGroupColors, setRouteGroupColors] = useState<Record<RouteKey, string>>({ best: '#4de1cc', secondary: '#77a8ed', longer: '#f7c271' });
  const [vehicleRouteOptions, setVehicleRouteOptions] = useState<RouteOption[]>([]);
  const [vehiclePreviewChoice, setVehiclePreviewChoice] = useState<RouteKey | null>(null);
  const [previewMessage, setPreviewMessage] = useState('');
  const [createdId, setCreatedId] = useState('');
  const [carColor, setCarColor] = useState('#4de1cc');
  const [carSpeedFactor, setCarSpeedFactor] = useState(1);
  const [carStrategy, setCarStrategy] = useState<'dynamic' | 'static'>('dynamic');
  const [carGpsInterval, setCarGpsInterval] = useState(30);
  const [carGpsBenefit, setCarGpsBenefit] = useState(12);
  const [spawnCount, setSpawnCount] = useState(10);
  const [roadSpeed, setRoadSpeed] = useState(20);
  const [editName, setEditName] = useState('');
  const [editDirection, setEditDirection] = useState<'both' | 'selected' | 'opposite'>('both');
  const [editLanesSelected, setEditLanesSelected] = useState(1);
  const [editLanesOpposite, setEditLanesOpposite] = useState(1);
  const [editSpeed, setEditSpeed] = useState(40);
  const [phaseDuration, setPhaseDuration] = useState(30);
  const [globalInterval, setGlobalInterval] = useState(30);
  const [globalBenefit, setGlobalBenefit] = useState(12);
  const [globalDynamic, setGlobalDynamic] = useState(50);
  const [loopStart, setLoopStart] = useState(6);
  const [loopBase, setLoopBase] = useState(6);
  const [loopPeak, setLoopPeak] = useState(3);
  const [clockInput, setClockInput] = useState('06:00');
  const [showRoute, setShowRoute] = useState(true);
  const [showPreviousRoute, setShowPreviousRoute] = useState(false);
  const [followVehicle, setFollowVehicle] = useState(false);
  const [panelMode, setPanelMode] = useState<'wide' | 'compact' | 'hidden'>('wide');
  const [routePulse, setRoutePulse] = useState<{ vehicleId: string; count: number } | null>(null);
  const lastRoute = useRef<{ vehicleId: string; count: number } | null>(null);
  const [graphOverlay, setGraphOverlay] = useState<GraphOverlay | null>(null);
  const [graphShowVertices, setGraphShowVertices] = useState(true);
  const [graphShowArcs, setGraphShowArcs] = useState(false);
  const [graphShowIds, setGraphShowIds] = useState(false);
  const [graphShowWeights, setGraphShowWeights] = useState(false);
  const [graphComponent, setGraphComponent] = useState<number | null>(null);
  const [graphSelected, setGraphSelected] = useState<GraphVertex | null>(null);
  const [graphStart, setGraphStart] = useState('');
  const [graphEnd, setGraphEnd] = useState('');
  const [graphPath, setGraphPath] = useState<string[]>([]);
  const [accessPoints, setAccessPoints] = useState<AccessPoint[]>([]);
  const [accessName, setAccessName] = useState('Novo ponto');
  const [buildOrigin, setBuildOrigin] = useState<Snapped | null>(null);
  const [buildDestination, setBuildDestination] = useState<Snapped | null>(null);
  const [buildWaypoints, setBuildWaypoints] = useState<[number, number][]>([]);
  const [buildPick, setBuildPick] = useState<'origin' | 'via' | 'destination'>('origin');
  const [buildName, setBuildName] = useState('Nova conexão');
  const [buildScenarioName, setBuildScenarioName] = useState('Blumenau experimental');
  const [buildDirection, setBuildDirection] = useState<'both' | 'forward' | 'reverse'>('both');
  const [buildSpeed, setBuildSpeed] = useState(40);
  const [buildLanes, setBuildLanes] = useState(1);
  const [buildCapacity, setBuildCapacity] = useState(900);
  const [buildCost, setBuildCost] = useState(0);
  const [replaceRoadId, setReplaceRoadId] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [urbanNetworks, setUrbanNetworks] = useState<UrbanNetwork | null>(null);
  const [signalCandidate, setSignalCandidate] = useState<{ id: string; coordinates: [number, number]; type: string; distance_m: number } | null>(null);
  const [cityMaps, setCityMaps] = useState<{ active: string | null; cities: { id: string | null; name: string; region: string; source: string; bounds: number[]; network_version: string; drivable_edges?: number }[] } | null>(null);
  const [mapName, setMapName] = useState('');
  const [mapRegion, setMapRegion] = useState('');
  const [mapFile, setMapFile] = useState<File | null>(null);
  const [mapCrop, setMapCrop] = useState(false);
  const [mapBounds, setMapBounds] = useState({ west: -49.077, south: -26.928, east: -49.055, north: -26.906 });
  const [mapImporting, setMapImporting] = useState(false);
  const previewOption = routeOptions.find(option => option.key === routeChoice);
  const previewRoute = previewOption?.route || [];
  const previewSeconds = previewOption?.seconds ?? null;

  const active = Boolean(snapshot?.connected);
  const running = Boolean(snapshot?.running);
  const selected = useMemo<Selection>(() => {
    if (!selection || !snapshot) return selection;
    if (selection.kind === 'vehicle') {
      const car = snapshot.vehicles?.find(item => item.id === selection.value.id);
      return car ? { kind: 'vehicle', value: car } : null;
    }
    if (selection.kind === 'light') return { kind: 'light', value: snapshot.lights?.find(light => light.id === selection.value.id) || selection.value,
      movement_id: selection.movement_id };
    return selection;
  }, [selection, snapshot]);
  useEffect(() => {
    if (selection?.kind === 'vehicle' && snapshot?.vehicles &&
        !snapshot.vehicles.some(car => car.id === selection.value.id)) {
      setSelection(null);
      setFollowVehicle(false);
    }
  }, [selection, snapshot]);
  useEffect(() => {
    setSelection(null); setRoadSelection(null); setFollowVehicle(false);
    setOrigin(null); setDestination(null); setWaypoints([]); setPick('origin');
  }, [snapshot?.run_id]);
  useEffect(() => {
    if (followVehicle && selection?.kind === 'vehicle' && snapshot?.connected &&
        !snapshot.vehicles.some(car => car.id === selection.value.id)) setFollowVehicle(false);
  }, [followVehicle, selection, snapshot]);
  useEffect(() => {
    if (!createdId || !snapshot) return;
    const car = snapshot.vehicles?.find(item => item.id === createdId);
    if (car) { setSelection({ kind: 'vehicle', value: car }); setTool('vehicle'); setCreatedId(''); }
  }, [createdId, snapshot]);
  useEffect(() => {
    if (tool !== 'graph' || graphOverlay) return;
    fetch('/api/graph/overlay').then(response => response.json()).then(setGraphOverlay).catch(error => setNotice(error.message));
  }, [tool, graphOverlay, setNotice]);
  useEffect(() => {
    fetch('/api/access-points').then(response => response.json()).then(data => setAccessPoints(data.points || [])).catch(() => {});
  }, []);
  useEffect(() => {
    if (tool === 'build') fetch('/api/urban/networks').then(response => response.json()).then(setUrbanNetworks).catch(error => setNotice(error.message));
  }, [tool, snapshot?.network_scenario_id, setNotice]);
  useEffect(() => {
    if (tool === 'road' || tool === 'new_signal')
      fetch('/api/urban/networks').then(response => response.json()).then(setUrbanNetworks).catch(() => {});
  }, [tool, snapshot?.network_scenario_id]);
  useEffect(() => {
    if (!roadSelection) return;
    const oppositeId = roadSelection.id.startsWith('-') ? roadSelection.id.slice(1) : `-${roadSelection.id}`;
    const opposite = network.features.find(feature => String(feature.properties?.id) === oppositeId);
    setEditDirection(opposite ? 'both' : 'selected');
    setEditLanesSelected(roadSelection.lanes || 1);
    setEditLanesOpposite(Number(opposite?.properties?.lanes) || 1);
    setEditSpeed(Math.round(roadSelection.speed_kmh || 40));
    setEditName(roadSelection.name === 'Via sem nome' ? '' : roadSelection.name || '');
  }, [roadSelection?.id, network]);
  useEffect(() => {
    const vehicle = selected?.kind === 'vehicle' ? selected.value : null;
    if (!vehicle) { lastRoute.current = null; setRoutePulse(null); return; }
    const previous = lastRoute.current;
    if (previous?.vehicleId === vehicle.id && vehicle.reroutes > previous.count) {
      setRoutePulse({ vehicleId: vehicle.id, count: vehicle.reroutes });
      setShowPreviousRoute(true);
    }
    lastRoute.current = { vehicleId: vehicle.id, count: vehicle.reroutes };
  }, [selected?.kind === 'vehicle' ? selected.value.id : null, selected?.kind === 'vehicle' ? selected.value.reroutes : null]);
  useEffect(() => {
    if (!routePulse) return;
    const timer = window.setTimeout(() => setRoutePulse(null), 5500);
    return () => window.clearTimeout(timer);
  }, [routePulse]);
  useEffect(() => {
    if (tool === 'maps') fetch('/api/maps').then(response => response.json()).then(setCityMaps).catch(error => setNotice(error.message));
  }, [tool, snapshot?.city_id, setNotice]);
  useEffect(() => {
    if (selected?.kind !== 'vehicle') return;
    setCarColor(selected.value.color || '#4de1cc');
    setCarSpeedFactor(selected.value.speed_factor || 1);
    setCarStrategy(selected.value.strategy);
    setCarGpsInterval(selected.value.gps_interval || 30);
    setCarGpsBenefit(Math.round((selected.value.gps_benefit || 0.12) * 100));
  }, [selected?.kind === 'vehicle' ? selected.value.id : null]);
  useEffect(() => {
    setVehicleRouteOptions([]); setVehiclePreviewChoice(null);
    const vehicleId = selected?.kind === 'vehicle' ? selected.value.id : null;
    if (!vehicleId) return;
    let stale = false;
    fetch(`/api/vehicles/${encodeURIComponent(vehicleId)}/route-options`)
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(data => { if (!stale) setVehicleRouteOptions(data.options || []); })
      .catch(() => {});
    return () => { stale = true; };
  }, [selected?.kind === 'vehicle' ? selected.value.id : null]);

  const points: MapPoint[] = [
    ...(origin ? [{ coordinates: origin.coordinates, label: 'A · Origem', role: 'origin' as const }] : []),
    ...waypoints.map((point, index) => ({ coordinates: point.coordinates, label: `${index + 1} · Passagem`, role: 'waypoint' as const })),
    ...(destination ? [{ coordinates: destination.coordinates, label: 'B · Destino', role: 'destination' as const }] : [])
  ];
  const customBody = () => ({ origin: { coordinates: origin!.coordinates }, destination: { coordinates: destination!.coordinates },
    waypoints: waypoints.map(point => ({ coordinates: point.coordinates })), color: carColor, strategy: carStrategy,
    gps_interval: carGpsInterval, gps_benefit: carGpsBenefit / 100, speed_factor: carSpeedFactor,
    route_choice: routeChoice });
  useEffect(() => {
    if (!origin || !destination) { setRouteOptions([]); setPreviewMessage(''); return; }
    let stale = false;
    fetch('/api/route/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(customBody()) })
      .then(async response => { const data = await response.json(); if (!response.ok) throw new Error(data.detail); return data; })
      .then(data => { if (!stale) { setRouteOptions(data.options || []); setPreviewMessage(''); } })
      .catch(error => { if (!stale) { setRouteOptions([]); setPreviewMessage(error.message); } });
    return () => { stale = true; };
  }, [origin, destination, waypoints]);

  const pickMapPoint = async (coordinates: [number, number]) => {
    if (pick === 'none') { setNotice('Escolha Origem, Destino ou Ponto de passagem no painel antes de clicar.'); return; }
    try {
      const response = await fetch(`/api/nearest-road?lon=${coordinates[0]}&lat=${coordinates[1]}`);
      const point = await response.json() as Snapped & { detail?: string };
      if (!response.ok) throw new Error(point.detail || 'Não foi possível localizar uma via');
      if (pick === 'origin') { setOrigin(point); setPick('destination'); }
      else if (pick === 'destination') { setDestination(point); setPick('none'); }
      else { setWaypoints(items => [...items, point]); setPick('none'); }
    } catch (error) { setNotice((error as Error).message); }
  };
  const chooseTool = (name: string) => {
    if (name === 'road' && selection?.kind === 'road') setRoadSelection(selection.value);
    setTool(name);
    if (name === 'car' && !origin) setPick('origin');
  };
  const addAccessPoint = async (coordinates: [number, number]) => {
    try {
      const response = await fetch('/api/access-points', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ coordinates, name: accessName }) });
      const point = await response.json();
      if (!response.ok) throw new Error(point.detail);
      setAccessPoints(items => [...items, point]);
      setGraphOverlay(null);
      setNotice(`Ponto ${point.name} registrado no grafo sobre ${point.edge_id}. Pode ser usado como origem ou destino.`);
    } catch (error) { setNotice((error as Error).message); }
  };
  const removeAccessPoint = async (id: string) => {
    const response = await fetch(`/api/access-points/${id}`, { method: 'DELETE' });
    if (response.ok) { setAccessPoints(items => items.filter(point => point.id !== id)); setGraphOverlay(null); }
  };
  const selectGraphVertex = (vertex: GraphVertex) => {
    setGraphSelected(vertex);
    if (!graphStart || (graphStart && graphEnd)) { setGraphStart(vertex.id); setGraphEnd(''); setGraphPath([]); }
    else setGraphEnd(vertex.id);
  };
  const calculateGraphPath = async () => {
    try {
      const response = await fetch('/api/graph/path', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start: graphStart, end: graphEnd }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail);
      setGraphPath(data.path);
      if (!data.path.length) setNotice('Não há caminho dirigível entre os vértices escolhidos.');
    } catch (error) { setNotice((error as Error).message); }
  };
  const pickBuildPoint = async (coordinates: [number, number]) => {
    if (buildPick === 'via') { setBuildWaypoints(points => [...points, coordinates].slice(0, 12)); return; }
    try {
      const response = await fetch(`/api/nearest-road?lon=${coordinates[0]}&lat=${coordinates[1]}`);
      const point = await response.json() as Snapped & { detail?: string };
      if (!response.ok) throw new Error(point.detail);
      if (buildPick === 'origin') { setBuildOrigin(point); setBuildDestination(null); setBuildWaypoints([]); setBuildPick('via'); }
      else { setBuildDestination(point); setBuildPick('via'); }
    } catch (error) { setNotice((error as Error).message); }
  };
  const pickSignalPoint = async (coordinates: [number, number]) => {
    try {
      const response = await fetch(`/api/urban/junction?lon=${coordinates[0]}&lat=${coordinates[1]}`);
      const point = await response.json();
      if (!response.ok) throw new Error(point.detail);
      setSignalCandidate(point);
    } catch (error) { setNotice((error as Error).message); }
  };
  const urbanAction = async (path: string, method = 'POST', body?: object) => {
    setBuilding(true);
    try {
      const response = await fetch(`/api${path}`, { method, headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail);
      await refreshCity();
      setUrbanNetworks(await (await fetch('/api/urban/networks')).json());
      setGraphOverlay(null); setGraphPath([]); setGraphSelected(null); setSelection(null); setRoadSelection(null);
      setBuildOrigin(null); setBuildDestination(null); setBuildWaypoints([]); setBuildPick('origin');
      setSignalCandidate(null); setReplaceRoadId(null);
      setNotice('Rede SUMO reconstruída e validada. A simulação foi reiniciada em pausa; clique em Iniciar.');
    } catch (error) { setNotice((error as Error).message); }
    finally { setBuilding(false); }
  };
  const createRoad = () => {
    if (!buildOrigin || !buildDestination) return;
    urbanAction('/urban/roads', 'POST', { origin: buildOrigin.coordinates, destination: buildDestination.coordinates,
      via: buildWaypoints, name: buildName, direction: buildDirection, oneway: buildDirection !== 'both', speed_kmh: buildSpeed, lanes: buildLanes,
      capacity_estimate: buildCapacity, hypothetical_cost: buildCost,
      scenario_name: buildScenarioName, replace_road_id: replaceRoadId });
  };
  const importMap = async () => {
    if (!mapFile || !mapName.trim()) return;
    setMapImporting(true);
    try {
      const query = new URLSearchParams({ name: mapName, region: mapRegion });
      if (mapCrop) Object.entries(mapBounds).forEach(([key, value]) => query.set(key, String(value)));
      const response = await fetch(`/api/maps/import?${query}`, { method: 'POST', headers: { 'Content-Type': 'application/xml' }, body: mapFile });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail);
      setCityMaps(await (await fetch('/api/maps')).json());
      setNotice(`${data.name} importada: ${data.drivable_edges} trechos SUMO trafegáveis. Ative-a na lista.`);
      setMapFile(null);
    } catch (error) { setNotice((error as Error).message); }
    finally { setMapImporting(false); }
  };
  const activateMap = async (cityId: string | null) => {
    setMapImporting(true);
    try {
      const response = await fetch(cityId ? `/api/maps/${cityId}/activate` : '/api/maps/base/activate', { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail);
      await refreshCity(); setCityMaps(await (await fetch('/api/maps')).json());
      setGraphOverlay(null); setGraphPath([]); setSelection(null); setRoadSelection(null);
      setNotice('Mapa ativado. A rede SUMO foi carregada em pausa; clique em Iniciar.');
    } catch (error) { setNotice((error as Error).message); }
    finally { setMapImporting(false); }
  };
  const createCustom = async () => {
    if (!origin || !destination) return;
    const groups = routeKeys.filter(key => routeGroupCounts[key] > 0 && routeOptions.some(option => option.key === key))
      .map(choice => ({ choice, count: routeGroupCounts[choice], color: routeGroupColors[choice] }));
    if (!groups.length) { setNotice('Defina ao menos um carro em uma rota disponível.'); return; }
    const response = await act('/spawn/groups', { ...customBody(), groups });
    if (response && 'vehicle_ids' in response) {
      const ids = response.vehicle_ids as string[];
      if (ids.length) setCreatedId(ids[0]);
      setOrigin(null); setDestination(null); setWaypoints([]); setPick('origin');
      setNotice(`${ids.length} carros lançados no mesmo horário simulado, divididos pelas rotas escolhidas.`);
    }
  };
  const chooseSelectedRoute = async (choice: RouteKey) => {
    if (selected?.kind !== 'vehicle') return;
    const result = await act(`/vehicles/${encodeURIComponent(selected.value.id)}/route`, { choice });
    if (result) { setShowPreviousRoute(true); setVehiclePreviewChoice(null); setCarStrategy('static'); }
  };
  const refreshSelectedRoutes = async () => {
    if (selected?.kind !== 'vehicle') return;
    try {
      const response = await fetch(`/api/vehicles/${encodeURIComponent(selected.value.id)}/route-options`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail);
      setVehicleRouteOptions(data.options || []);
    } catch (error) { setNotice((error as Error).message); }
  };
  const setCarGps = () => selected?.kind === 'vehicle' && act(`/vehicles/${selected.value.id}/gps`,
    { strategy: carStrategy, interval: carGpsInterval, benefit: carGpsBenefit / 100 });
  const setCarStyle = () => selected?.kind === 'vehicle' && act(`/vehicles/${selected.value.id}/style`,
    { color: carColor, speed_factor: carSpeedFactor });
  const loopAction = (enabled: boolean) => act('/loop', { enabled, start_hour: loopStart,
    base_per_minute: loopBase, peak_multiplier: loopPeak });
  const chosenHour = () => { const [hours, minutes] = clockInput.split(':').map(Number); return hours + minutes / 60; };
  const setClock = () => { const hour = chosenHour(); setLoopStart(hour); if (active) act('/clock', { hour }); };

  const tools = [
    { key: 'select', label: 'Explorar', icon: MousePointer2, hint: 'Clique em um carro, semáforo ou trecho para inspecionar.' },
    { key: 'car', label: 'Criar carro', icon: CarFront, hint: pick === 'none' ? 'Escolha um ponto no painel e clique no mapa.' : `Clique no mapa para definir ${pick === 'origin' ? 'a origem' : pick === 'destination' ? 'o destino' : 'um ponto de passagem'}.` },
    { key: 'vehicle', label: 'Inspecionar carro', icon: Activity, hint: 'Clique em um carro no mapa ou escolha na lista lateral.' },
    { key: 'light', label: 'Semáforos', icon: Signal, hint: 'Aproxime o mapa para ver o sinal de cada faixa. Clique nele para identificar a via.' },
    { key: 'road', label: 'Obras e vias', icon: TrafficCone, hint: 'Clique perto de uma rua. As setas mostram o sentido ao aproximar.' },
    { key: 'graph', label: 'Grafo viário', icon: GitBranch, hint: 'Aproxime para ver os vértices reais do roteador. Clique em dois para traçar o caminho mínimo.' },
    { key: 'point', label: 'Adicionar ponto', icon: MapPin, hint: 'Clique sobre uma via para criar um ponto de acesso persistente.' },
    { key: 'build', label: 'Construir estrada', icon: Route, hint: buildPick === 'via' ? 'Clique nas curvas da rua ou escolha Destino para conectar a outra via.' : `Clique no mapa para definir ${buildPick === 'origin' ? 'a origem' : 'o destino'}.` },
    { key: 'new_signal', label: 'Adicionar semáforo', icon: Signal, hint: 'Clique próximo de um cruzamento existente para instalar um semáforo físico.' },
    { key: 'maps', label: 'Gerenciar mapas', icon: MapPin, hint: 'Importe um arquivo OSM XML de Blumenau ou outra cidade e ative a malha correspondente.' },
    { key: 'weather', label: 'Clima', icon: CloudRain, hint: 'Escolha o clima e veja os parâmetros aplicados aos veículos.' },
    { key: 'gps', label: 'GPS geral', icon: GitBranch, hint: 'Configure o GPS dos motoristas gerados automaticamente.' },
    { key: 'clock', label: 'Relógio', icon: Clock3, hint: 'Escolha a hora da cidade antes ou durante a simulação.' },
    { key: 'loop', label: 'Loop diário', icon: RotateCcw, hint: 'Ative carros contínuos e ajuste os horários de pico.' }
  ];
  const currentTool = tools.find(item => item.key === tool) || tools[0];
  const toolGroups = [
    { label: 'Explorar', icon: MousePointer2, keys: ['select'], start: 'select' },
    { label: 'Carros e GPS', icon: CarFront, keys: ['car', 'vehicle', 'gps'], start: 'car' },
    { label: 'Ruas e grafo', icon: TrafficCone, keys: ['road', 'build', 'point', 'graph'], start: 'road' },
    { label: 'Semáforos', icon: Signal, keys: ['light', 'new_signal'], start: 'light' },
    { label: 'Cidade', icon: Clock3, keys: ['maps', 'weather', 'clock', 'loop'], start: 'clock' }
  ];
  const currentGroup = toolGroups.find(group => group.keys.includes(tool)) || toolGroups[0];
  const roadLabels = useMemo(() => new Map(network.features.map(feature =>
    [String(feature.properties?.id), String(feature.properties?.name || 'Via sem nome')])), [network]);

  return <main className={`city-layout panel-${panelMode}`}>
    <section className="map-frame">
      <CityMap network={network} baseRoads={baseRoads} places={places} snapshot={snapshot} selection={selected}
        selectedRoadId={tool === 'road' ? roadSelection?.id || null : selected?.kind === 'road' ? selected.value.id : null}
        tool={tool} theme={theme} showRoute={showRoute} showPreviousRoute={showPreviousRoute}
        routePulseToken={routePulse ? `${routePulse.vehicleId}-${routePulse.count}` : null}
        followVehicleId={followVehicle && selected?.kind === 'vehicle' ? selected.value.id : null}
        onStopFollow={() => setFollowVehicle(false)} customPoints={tool === 'car' ? points : []}
        previewRoute={tool === 'car' ? previewRoute : tool === 'vehicle' ? vehicleRouteOptions.find(option => option.key === vehiclePreviewChoice)?.route || [] : []}
        onSelect={setSelection}
        graphOverlay={graphOverlay} graphShowVertices={tool === 'graph' && graphShowVertices} graphShowArcs={tool === 'graph' && graphShowArcs}
        graphShowIds={graphShowIds} graphShowWeights={graphShowWeights} graphComponent={graphComponent}
        graphPath={tool === 'graph' ? graphPath : []} graphSelectedId={tool === 'graph' ? graphSelected?.id || null : null}
        accessPoints={accessPoints} onGraphVertex={selectGraphVertex} onAccessClick={addAccessPoint}
        onBuildClick={pickBuildPoint} onSignalClick={pickSignalPoint}
        buildPoints={tool === 'new_signal' ? (signalCandidate ? [signalCandidate.coordinates] : []) : [...(buildOrigin ? [buildOrigin.coordinates] : []), ...buildWaypoints, ...(buildDestination ? [buildDestination.coordinates] : [])]}
        onMapClick={pickMapPoint} onRoadCandidates={setRoadCandidates} onRoadSelect={setRoadSelection} />
      <div className="map-top-left"><div className="map-chip"><span className="chip-dot" /> DADOS OPENSTREETMAP</div>
        <div className="map-caption">{snapshot?.city_name || 'BLUMENAU CENTRAL'} <span>•</span> {snapshot?.city_id ? 'MALHA IMPORTADA' : 'RECORTE REAL DE BLUMENAU'}</div></div>
      <div className="map-top-right"><div className="map-key"><span className="legend car" /> Carro
        <span className="legend red" /> Fechado <span className="legend green" /> Aberto
        <span className="legend yellow" /> Atenção <span className="legend mixed" /> Misto <span className="direction-key">➜</span> Sentido
        <span className="legend slow" /> Lento <span className="legend moderate" /> Moderado <span className="legend free" /> Livre
        <span className="legend blocked-road" /> Via interditada</div></div>
      <div className="map-tip"><strong>{currentTool.label}</strong><span>{currentTool.hint}</span></div>
      <div className="panel-map-controls"><button title={panelMode === 'hidden' ? 'Mostrar painel' : 'Ocultar painel'} onClick={() => setPanelMode(panelMode === 'hidden' ? 'wide' : 'hidden')}>{panelMode === 'hidden' ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}<span>{panelMode === 'hidden' ? 'Mostrar painel' : 'Ocultar painel'}</span></button>
        {panelMode !== 'hidden' && <button title={panelMode === 'compact' ? 'Ampliar painel' : 'Diminuir painel'} onClick={() => setPanelMode(panelMode === 'compact' ? 'wide' : 'compact')}><SlidersHorizontal size={17} /><span>{panelMode === 'compact' ? 'Ampliar' : 'Diminuir'}</span></button>}</div>
      <div className="map-bottom-right">© OpenStreetMap contributors • ODbL</div>
      <div className="tool-tray" aria-label="Ferramentas do mapa">{toolGroups.map(group => <button key={group.label}
        className={currentGroup.label === group.label ? 'active' : ''} title={group.label} onClick={() => chooseTool(group.start)}>
        <group.icon size={18} /><span>{group.label}</span></button>)}</div>
    </section>
    <aside className="panel"><div className="panel-header"><div><div className="eyebrow">FERRAMENTA ATIVA</div><h2>{currentTool.label}</h2></div>
      <span className="panel-header-icon"><currentTool.icon size={19} /></span></div>
      <div className="tool-instruction">{currentTool.hint}</div>
      {currentGroup.keys.length > 1 && <nav className="subtool-nav" aria-label={`Ferramentas de ${currentGroup.label}`}>
        {currentGroup.keys.map(key => { const item = tools.find(candidate => candidate.key === key)!; return <button key={key} className={tool === key ? 'active' : ''} onClick={() => chooseTool(key)}><item.icon size={15} />{item.label}</button>; })}</nav>}
      <div className="panel-scroll">
        {tool === 'select' && <section className="panel-section"><h3>Escolha uma ferramenta</h3>
          <p className="panel-copy">Os botões à esquerda ativam ações diferentes no mapa. A simulação precisa estar iniciada para criar carros ou editar o trânsito.</p>
          <div className="overview-grid"><div><strong>{snapshot?.active || 0}</strong><span>carros ativos</span></div><div><strong>{snapshot?.lights?.length || 0}</strong><span>semáforos</span></div><div><strong>{snapshot?.reroutes || 0}</strong><span>mudanças de rota</span></div></div>
          <button className="primary-button wide" onClick={() => chooseTool('car')}><Plus size={16} /> Criar carro personalizado</button></section>}

        {tool === 'car' && <><section className="panel-section"><div className="section-heading"><span><MapPin size={17} /> Viagem personalizada</span><HelpTip title="Criar viagens">Escolha origem e destino no mapa, compare as três rotas e informe quantos carros seguirão cada uma. Inicie a simulação antes de lançar os grupos.</HelpTip></div>
          <div className="step-list"><button className={pick === 'origin' ? 'current' : ''} onClick={() => setPick('origin')}><b>A</b><span>{origin ? origin.name : 'Definir origem no mapa'}</span></button>
            {waypoints.map((point, index) => <div key={`${point.edge_id}-${index}`} className="waypoint-row"><b>{index + 1}</b><span>{point.name}</span><button onClick={() => setWaypoints(items => items.filter((_, i) => i !== index))}>×</button></div>)}
            <button className={pick === 'waypoint' ? 'current' : ''} onClick={() => setPick('waypoint')}><b>+</b><span>Adicionar ponto de passagem</span></button>
            <button className={pick === 'destination' ? 'current' : ''} onClick={() => setPick('destination')}><b>B</b><span>{destination ? destination.name : 'Definir destino no mapa'}</span></button></div>
          <div className="hint">Cada clique é ajustado à via real mais próxima. Os pontos amarelos são passagens obrigatórias.</div>
          {previewMessage && <div className="inline-warning">{previewMessage}</div>}
          {routeOptions.length > 0 && <div className="route-options"><div className="section-heading"><span><Route size={17} /> Rotas calculadas</span></div>
            {routeOptions.map(option => <div key={option.key} className={`route-option ${routeChoice === option.key ? 'chosen' : ''}`}>
              <button className="route-option-heading" onClick={() => setRouteChoice(option.key)}><strong>{option.label}</strong><span>{duration(option.seconds)} · {number(option.distance_m)} m · {option.segments} trechos</span></button>
              <div className="route-group-controls"><label>Carros <input type="number" min="0" max="100" value={routeGroupCounts[option.key]} onChange={event => setRouteGroupCounts(items => ({ ...items, [option.key]: Math.max(0, Math.min(100, Number(event.target.value) || 0)) }))} /></label>
                <label>Cor <input type="color" value={routeGroupColors[option.key]} onChange={event => setRouteGroupColors(items => ({ ...items, [option.key]: event.target.value }))} /></label></div></div>)}
            <p className="micro-note">Clique numa rota para vê-la no mapa. As alternativas usam o trânsito simulado atual. Todos os grupos partem no mesmo instante; o SUMO pode inseri-los na via em momentos diferentes se não houver espaço.</p></div>}
          {previewRoute.length > 0 && <div className="route-preview"><Route size={16} /> Prévia: {previewRoute.length} trechos · {duration(previewSeconds || 0)}</div>}
          <button className="text-button" onClick={() => { setOrigin(null); setDestination(null); setWaypoints([]); setPick('origin'); }}>Limpar pontos</button></section>
          <section className="panel-section"><div className="section-heading"><span><SlidersHorizontal size={17} /> Personalização</span></div>
            <div className="field"><label>Velocidade desejada: {Math.round(carSpeedFactor * 100)}% do padrão</label><input type="range" min="0.6" max="1.4" step="0.05" value={carSpeedFactor} onChange={event => setCarSpeedFactor(Number(event.target.value))} /></div>
            <div className="field"><label>Estratégia</label><select value={carStrategy} onChange={event => setCarStrategy(event.target.value as 'dynamic' | 'static')}><option value="dynamic">GPS dinâmico</option><option value="static">GPS estático</option></select></div>
            <div className="field"><label>GPS recalcula a cada {carGpsInterval} s</label><input type="range" min="5" max="180" step="5" value={carGpsInterval} onChange={event => setCarGpsInterval(Number(event.target.value))} /></div>
            <div className="field"><label>Trocar rota se economizar ao menos {carGpsBenefit}%</label><input type="range" min="0" max="50" value={carGpsBenefit} onChange={event => setCarGpsBenefit(Number(event.target.value))} /></div>
            <button className="primary-button wide" disabled={!active || busy || !origin || !destination || !routeOptions.length || routeKeys.reduce((sum, key) => sum + routeGroupCounts[key], 0) > 100 || !routeKeys.some(key => routeGroupCounts[key] > 0 && routeOptions.some(option => option.key === key))} onClick={createCustom}><Plus size={16} /> Criar grupos no SUMO</button>
            <p className="micro-note">Máximo de 100 carros por lançamento. O GPS dinâmico pode recalcular depois; escolha GPS estático para preservar a rota definida.</p></section>
          <section className="panel-section"><div className="section-heading"><span><CarFront size={17} /> Geração rápida</span></div>
            <div className="field"><label>Quantidade de viagens aleatórias</label><select value={spawnCount} onChange={event => setSpawnCount(Number(event.target.value))}>{[10, 50, 100, 500].map(count => <option key={count} value={count}>{count} carros</option>)}</select></div>
            <button className="wide" disabled={!active || busy} onClick={() => act('/spawn', { count: spawnCount })}>Gerar viagens</button></section></>}

        {tool === 'vehicle' && <><section className="panel-section"><div className="section-heading"><span><CarFront size={17} /> Veículos ativos</span></div>
          <select value={selected?.kind === 'vehicle' ? selected.value.id : ''} onChange={event => { const car = snapshot?.vehicles.find(item => item.id === event.target.value); if (car) setSelection({ kind: 'vehicle', value: car }); }}>
            <option value="">Selecione um carro</option>{(snapshot?.vehicles || []).map(car => <option key={car.id} value={car.id}>{car.id} · {statusNames[car.state] || car.state}</option>)}</select></section>
          {selected?.kind === 'vehicle' && <><section className="panel-section"><div className="inspector-id"><CarFront size={20} />{selected.value.id}</div>
            <div className={`status-badge ${selected.value.state}`}>{statusNames[selected.value.state] || selected.value.state}</div>
            <div className="data-grid"><div>ORIGEM<strong>{roadLabels.get(selected.value.origin) || selected.value.origin_neighborhood}</strong></div><div>DESTINO<strong>{roadLabels.get(selected.value.destination) || selected.value.destination_neighborhood}</strong></div><div>POSIÇÃO<strong>{selected.value.coordinates[1].toFixed(5)}, {selected.value.coordinates[0].toFixed(5)}</strong></div><div>VELOCIDADE<strong>{number(selected.value.speed * 3.6)} km/h</strong></div><div>DISTÂNCIA RESTANTE<strong>{number(selected.value.remaining_distance_m)} m</strong></div><div>CHEGADA ESTIMADA<strong>{selected.value.eta_city_hour == null ? 'Calculando' : clock(selected.value.eta_city_hour)}</strong></div><div>TEMPO<strong>{duration(selected.value.travel_time)}</strong></div><div>ESPERA<strong>{duration(selected.value.waiting_time)}</strong></div><div>DESVIOS<strong>{selected.value.reroutes}</strong></div><div>ALGORITMO<strong>{selected.value.algorithm}</strong></div></div>
            <div className="vehicle-actions"><button className={followVehicle ? 'active' : ''} onClick={() => setFollowVehicle(!followVehicle)}>{followVehicle ? 'Parar de seguir' : 'Seguir veículo'}</button><button onClick={() => setShowRoute(!showRoute)}>{showRoute ? 'Ocultar rota' : 'Mostrar rota'}</button><button disabled={!selected.value.previous_route.length} className={showPreviousRoute ? 'active' : ''} onClick={() => setShowPreviousRoute(!showPreviousRoute)}>{showPreviousRoute ? 'Ocultar rota anterior' : 'Ver rota anterior'}</button></div>
            <div className="gps-card"><strong><Route size={15} /> GPS integrado</strong><p>{selected.value.gps_status}</p>
              <div>Próxima análise: <b>{duration(Math.max(0, selected.value.gps_next_check - (snapshot?.sim_time || 0)))}</b></div>
              <div>Tempo restante estimado: <b>{selected.value.gps_estimated_remaining == null ? 'Aguardando análise' : duration(selected.value.gps_estimated_remaining)}</b></div>
              <div>Economia alternativa: <b>{duration(selected.value.gps_alternative_saving || 0)}</b></div>
              <div>Previsão atualizada em: <b>{duration(selected.value.forecast_updated_at)}</b></div></div>
            {selected.value.last_route_change && <div className="route-change-card"><strong>Última mudança de rota</strong><span>{duration(selected.value.last_route_change.at_sim_time)} · {selected.value.last_route_change.reason}</span><span>{selected.value.last_route_change.saved_seconds == null ? 'Tempo anterior indisponível' : `${number(selected.value.last_route_change.saved_seconds)} s de diferença estimada`} · {selected.value.last_route_change.distance_delta_m >= 0 ? '+' : ''}{number(selected.value.last_route_change.distance_delta_m)} m</span></div>}
            <div className="micro-note">Chegada prevista pelo simulador, calculada com custos viários observados. A rota anterior aparece em violeta quando ativada.</div>
            <div className="micro-note">A rota destacada no mapa tem {selected.value.route.length} trechos. O custo considera a velocidade observada de todos os carros em cada via.</div></section>
            <section className="panel-section"><div className="section-heading"><span><Route size={17} /> Escolher rota deste carro</span></div>
              <button className="wide" onClick={refreshSelectedRoutes}>Atualizar alternativas pelo trânsito atual</button>
              <div className="route-options">{vehicleRouteOptions.map(option => <div key={option.key} className={`route-option ${vehiclePreviewChoice === option.key ? 'chosen' : ''}`}>
                <button className="route-option-heading" onClick={() => setVehiclePreviewChoice(option.key)}><strong>{option.label}</strong><span>{duration(option.seconds)} · {number(option.distance_m)} m · {option.segments} trechos</span></button>
                <button className="wide" disabled={busy} onClick={() => chooseSelectedRoute(option.key)}>Seguir esta rota</button></div>)}</div>
              {!vehicleRouteOptions.length && <p className="micro-note">Alternativas indisponíveis neste cruzamento ou no trecho atual. Atualize após o carro avançar.</p>}
              <p className="micro-note">Clique no nome para ver a alternativa pontilhada no mapa. Ao escolhê-la, este GPS fica estático; use Ajustar este GPS para reativar os desvios automáticos.</p></section>
            <section className="panel-section"><div className="section-heading"><span><GitBranch size={17} /> Ajustar este GPS</span></div>
              <div className="field"><label>Estratégia</label><select value={carStrategy} onChange={event => setCarStrategy(event.target.value as 'dynamic' | 'static')}><option value="dynamic">Dinâmico</option><option value="static">Estático</option></select></div>
              <div className="field"><label>Recalcular a cada {carGpsInterval} s</label><input type="range" min="5" max="180" step="5" value={carGpsInterval} onChange={event => setCarGpsInterval(Number(event.target.value))} /></div>
              <div className="field"><label>Benefício mínimo: {carGpsBenefit}%</label><input type="range" min="0" max="50" value={carGpsBenefit} onChange={event => setCarGpsBenefit(Number(event.target.value))} /></div>
              <button className="wide" disabled={busy} onClick={setCarGps}>Aplicar ao carro</button></section>
            <section className="panel-section"><div className="section-heading"><span><SlidersHorizontal size={17} /> Aparência e condução</span></div>
              <div className="field"><label>Cor</label><div className="color-row"><input type="color" value={carColor} onChange={event => setCarColor(event.target.value)} /><span>{carColor.toUpperCase()}</span></div></div>
              <div className="field"><label>Velocidade desejada: {Math.round(carSpeedFactor * 100)}%</label><input type="range" min="0.6" max="1.4" step="0.05" value={carSpeedFactor} onChange={event => setCarSpeedFactor(Number(event.target.value))} /></div>
              <button className="wide" disabled={busy} onClick={setCarStyle}>Aplicar ao carro</button></section></>}
        </>}

        {tool === 'road' && <>
          {selected?.kind === 'vehicle' && <section className="panel-section road-watch"><div className="section-heading"><span><CarFront size={17} /> Carro acompanhado</span></div>
            <div className="inspector-id"><CarFront size={20} />{selected.value.id}</div>
            <div className={`status-badge ${selected.value.state}`}>{statusNames[selected.value.state] || selected.value.state}</div>
            <div className="data-grid"><div>DESVIOS<strong>{selected.value.reroutes}</strong></div><div>ROTA ATUAL<strong>{selected.value.route.length} trechos</strong></div><div>CHEGADA ESTIMADA<strong>{selected.value.eta_city_hour == null ? 'Calculando' : clock(selected.value.eta_city_hour)}</strong></div></div>
            {selected.value.last_route_change && <div className="route-change-card"><strong>Última mudança de rota</strong><span>{duration(selected.value.last_route_change.at_sim_time)} · {selected.value.last_route_change.reason}</span></div>}
            <div className="vehicle-actions"><button className={followVehicle ? 'active' : ''} onClick={() => setFollowVehicle(!followVehicle)}>{followVehicle ? 'Parar de seguir' : 'Seguir veículo'}</button><button onClick={() => setShowRoute(!showRoute)}>{showRoute ? 'Ocultar rota' : 'Mostrar rota'}</button><button disabled={!selected.value.previous_route.length} className={showPreviousRoute ? 'active' : ''} onClick={() => setShowPreviousRoute(!showPreviousRoute)}>{showPreviousRoute ? 'Ocultar rota anterior' : 'Ver rota anterior'}</button></div>
            <p className="panel-copy">A rota do carro permanece visível enquanto você interdita trechos. O GPS atualiza a rota quando houver desvio válido.</p></section>}
          <section className="panel-section"><div className="section-heading"><span><TrafficCone size={17} /> Trecho selecionado</span></div>
          {roadSelection ? <><div className="inspector-id"><TrafficCone size={20} />{roadSelection.name || 'Trecho sem nome'}</div>
            {roadCandidates.length > 1 && <div className="field"><label>Trechos neste clique (do mais próximo ao mais distante)</label><select value={roadSelection.id} onChange={event => { const road = roadCandidates.find(item => item.id === event.target.value); if (road) setRoadSelection(road); }}>{roadCandidates.map((road, index) => <option key={road.id} value={road.id}>{index + 1}. {road.name || 'Via sem nome'} · {number(road.length)} m</option>)}</select></div>}
            <div className="data-grid"><div>ID DO TRECHO<strong>{roadSelection.id}</strong></div><div>COMPRIMENTO<strong>{number(roadSelection.length)} m</strong></div><div>FAIXAS<strong>{roadSelection.lanes || 1}</strong></div><div>LIMITE<strong>{number(roadSelection.speed_kmh)} km/h</strong></div><div>VEÍCULOS<strong>{snapshot?.congestion?.find(item => item.id === roadSelection.id)?.count || 0}</strong></div><div>VELOCIDADE MÉDIA<strong>{number((snapshot?.congestion?.find(item => item.id === roadSelection.id)?.speed || 0) * 3.6)} km/h</strong></div><div>ESTADO<strong>{snapshot?.blocked?.includes(roadSelection.id) ? 'Interditada' : snapshot?.partial?.includes(roadSelection.id) ? 'Uma faixa fechada' : snapshot?.reduced?.[roadSelection.id] ? 'Velocidade reduzida' : 'Livre'}</strong></div></div>
            <div className="field"><label>Reduzir velocidade para {roadSpeed} km/h</label><input type="range" min="5" max="60" value={roadSpeed} onChange={event => setRoadSpeed(Number(event.target.value))} /></div>
            <div className="button-grid"><button className="danger-button" disabled={!active || busy} onClick={() => act('/road', { edge_id: roadSelection.id, action: 'close' })}>Interditar trecho</button>{(roadSelection.lanes || 1) > 1 && <button disabled={!active || busy} onClick={() => act('/road', { edge_id: roadSelection.id, action: 'partial' })}>Fechar uma faixa</button>}<button disabled={!active || busy} onClick={() => act('/road', { edge_id: roadSelection.id, action: 'slow', speed_kmh: roadSpeed })}>Reduzir limite</button><button disabled={!active || busy} onClick={() => act('/road', { edge_id: roadSelection.id, action: 'restore' })}>Restaurar trecho</button></div>
            <p className="panel-copy">A rua é desenhada contínua. A interdição afeta somente o trecho selecionado e o sentido correspondente no SUMO.</p>
            <div className="section-heading"><span><SlidersHorizontal size={17} /> Editar rua no cenário</span><HelpTip title="Edição da malha">O nome, o sentido, as faixas e a velocidade são gravados numa cópia do OSM. O SUMO reconstrói a rede e reinicia os carros. Para uma interdição temporária, use os botões acima.</HelpTip></div>
            <p className="panel-copy">A edição física aplica sentido, faixas e limite de velocidade à rua OSM inteira que contém este trecho. Reconstruir reinicia a simulação.</p>
            <div className="field"><label>Nome no cenário (opcional)</label><input value={editName} maxLength={100} placeholder="Ex.: Rua das Flores" onChange={event => setEditName(event.target.value)} /></div>
            <div className="field"><label>Mão da rua</label><select value={editDirection} onChange={event => setEditDirection(event.target.value as typeof editDirection)}><option value="both">Mão dupla</option><option value="selected">Somente no sentido selecionado</option><option value="opposite">Somente no sentido oposto</option></select></div>
            {editDirection !== 'opposite' && <div className="field"><label>Faixas no sentido selecionado</label><select value={editLanesSelected} onChange={event => setEditLanesSelected(Number(event.target.value))}>{[1,2,3,4].map(value => <option key={value} value={value}>{value}</option>)}</select></div>}
            {editDirection !== 'selected' && <div className="field"><label>Faixas no sentido oposto</label><select value={editLanesOpposite} onChange={event => setEditLanesOpposite(Number(event.target.value))}>{[1,2,3,4].map(value => <option key={value} value={value}>{value}</option>)}</select></div>}
            <div className="field"><label>Limite físico: {editSpeed} km/h</label><input type="range" min="5" max="80" step="5" value={editSpeed} onChange={event => setEditSpeed(Number(event.target.value))} /></div>
            <button className="primary-button wide" disabled={building} onClick={() => urbanAction('/urban/road-edit', 'POST', { edge_id: roadSelection.id, name: editName.trim() || null, direction: editDirection, lanes_selected: editLanesSelected, lanes_opposite: editLanesOpposite, speed_kmh: editSpeed })}>{building ? 'Reconstruindo…' : 'Aplicar edição e reiniciar'}</button>
            <p className="micro-note">Nomes atribuídos aqui são hipóteses do cenário local; a fonte OpenStreetMap original não é alterada.</p>
            {urbanNetworks?.scenarios.find(item => item.id === urbanNetworks.active)?.road_edits?.some(item => roadSelection.id.includes(item.way_id)) && <button className="wide" disabled={building} onClick={() => { const item = urbanNetworks.scenarios.find(scenario => scenario.id === urbanNetworks.active)?.road_edits?.find(edit => roadSelection.id.includes(edit.way_id)); if (item) urbanAction(`/urban/road-edit/${item.way_id}`, 'DELETE'); }}>Restaurar configuração OSM</button>}</> : <p className="panel-copy">Clique na rua. A área de seleção é maior que a linha desenhada, e trechos próximos aparecem na lista.</p>}</section></>}

        {tool === 'graph' && <section className="panel-section"><div className="section-heading"><span><GitBranch size={17} /> Grafo de roteamento</span></div>
          <p className="panel-copy">Vértices azuis são trechos dirigíveis do SUMO. Pontos de acesso salvos aparecem em amarelo no grafo e são conectados com pesos proporcionais à posição na via. Arestas violetas representam conexões permitidas.</p>
          <div className="graph-toggles"><label><input type="checkbox" checked={graphShowVertices} onChange={event => setGraphShowVertices(event.target.checked)} /> Vértices</label>
            <label><input type="checkbox" checked={graphShowArcs} onChange={event => setGraphShowArcs(event.target.checked)} /> Arestas</label>
            <label><input type="checkbox" checked={graphShowIds} onChange={event => setGraphShowIds(event.target.checked)} /> IDs</label>
            <label><input type="checkbox" checked={graphShowWeights} onChange={event => setGraphShowWeights(event.target.checked)} /> Pesos</label></div>
          <div className="field"><label>Componente conexa</label><select value={graphComponent ?? ''} onChange={event => setGraphComponent(event.target.value === '' ? null : Number(event.target.value))}>
            <option value="">Todas</option>{Array.from({ length: graphOverlay?.components || 0 }, (_, index) => <option key={index} value={index}>Componente {index + 1}</option>)}</select></div>
          <div className="graph-legend"><span className="legend graph-node" /> Trecho SUMO <span className="legend yellow" /> Acesso salvo <span className="graph-line-key" /> Conexão dirigida</div>
          {graphSelected && <div className="graph-detail"><strong>{graphSelected.id}</strong><span>{graphSelected.neighborhood} · {graphSelected.intersection_type}</span><span>{graphSelected.coordinates[1].toFixed(6)}, {graphSelected.coordinates[0].toFixed(6)}</span><span>Entrada {graphSelected.degree_in} · Saída {graphSelected.degree_out} · Componente {graphSelected.component + 1}</span><span>Conectadas: {[...graphSelected.incoming, ...graphSelected.outgoing].slice(0, 12).join(', ')}</span></div>}
          <div className="graph-path-control"><span>Origem: {graphStart || 'clique num vértice'}</span><span>Destino: {graphEnd || 'clique em outro vértice'}</span><button className="primary-button wide" disabled={!graphStart || !graphEnd} onClick={calculateGraphPath}>Destacar caminho mínimo</button>{graphPath.length > 0 && <span>{graphPath.length} trechos no caminho</span>}</div>
          <p className="micro-note">IDs e pesos aparecem a partir do zoom 17. Em zoom distante, os detalhes são ocultados para preservar a fluidez.</p></section>}

        {tool === 'point' && <section className="panel-section"><div className="section-heading"><span><MapPin size={17} /> Pontos de acesso</span><HelpTip title="Ponto ou cruzamento?">Este ponto vira vértice do grafo para origem ou destino. Ele não abre um cruzamento físico. Use Construir estrada para criar uma ligação trafegável no SUMO.</HelpTip></div>
          <p className="panel-copy">Nomeie e clique sobre uma rua. O ponto entra no grafo como vértice de acesso ponderado pela posição na via e pode servir como origem ou destino. Ele não cria uma interseção física.</p>
          <div className="field"><label>Nome do próximo ponto</label><input value={accessName} onChange={event => setAccessName(event.target.value)} maxLength={100} /></div>
          <div className="access-list">{accessPoints.map(point => <div key={point.id}><strong>{point.name}</strong><small>{roadLabels.get(point.edge_id) || point.edge_id} · {number(point.position)} m</small>
            <div><button onClick={() => { setOrigin({ ...point, name: point.name }); setPick('destination'); setTool('car'); }}>Usar como origem</button><button onClick={() => { setDestination({ ...point, name: point.name }); setPick('origin'); setTool('car'); }}>Destino</button><button onClick={() => removeAccessPoint(point.id)}>Excluir</button></div></div>)}</div></section>}

        {tool === 'new_signal' && <section className="panel-section"><div className="section-heading"><span><Signal size={17} /> Semáforos do cenário</span></div>
          <p className="panel-copy">Clique perto de um cruzamento. A instalação reconstrói a rede SUMO com um controlador semafórico real e reinicia a simulação.</p>
          {signalCandidate && <><div className="graph-detail"><strong>Cruzamento {signalCandidate.id}</strong><span>{number(signalCandidate.distance_m, 1)} m do clique · {signalCandidate.type}</span></div><button className="primary-button wide" disabled={building} onClick={() => urbanAction('/urban/signals', 'POST', { coordinates: signalCandidate.coordinates })}>Instalar e reiniciar</button></>}
          <div className="urban-list">{urbanNetworks?.scenarios.find(item => item.id === urbanNetworks.active)?.signals?.map(item => <div key={item.node_id}><strong>Cruzamento {item.node_id}</strong><button disabled={building} onClick={() => urbanAction(`/urban/signals/${item.node_id}`, 'DELETE')}>Remover</button></div>)}</div>
          <p className="micro-note">Um ponto isolado fora de um cruzamento não pode receber semáforo físico. Construa primeiro a conexão viária se necessário.</p></section>}

        {tool === 'build' && <><section className="panel-section"><div className="section-heading"><span><Route size={17} /> Construir estrada</span><HelpTip title="Mapear uma rua pequena">Ligue duas vias existentes e clique nos pontos de curva para desenhar a rua ausente. O SUMO só permitirá carros após reconstruir e validar a conexão. Não invente nomes como se fossem dados OSM.</HelpTip></div>
          <p className="panel-copy">Marque origem e destino em vias existentes. Entre eles, clique em pontos de curva para traçar uma rua pequena ainda não mapeada. O novo trajeto entra no grafo físico após a reconstrução.</p>
          <div className="button-grid"><button className={buildPick === 'origin' ? 'active' : ''} onClick={() => setBuildPick('origin')}>1. Origem</button><button className={buildPick === 'via' ? 'active' : ''} disabled={!buildOrigin} onClick={() => setBuildPick('via')}>2. Curvas</button><button className={buildPick === 'destination' ? 'active' : ''} disabled={!buildOrigin} onClick={() => setBuildPick('destination')}>3. Destino</button></div>
          <div className="build-points"><div><b>A</b>{buildOrigin?.name || 'Clique no início'}</div><div><b>+</b>{buildWaypoints.length} pontos de curva</div><div><b>B</b>{buildDestination?.name || 'Clique no fim'}</div></div>
          {buildWaypoints.length > 0 && <button className="text-button" onClick={() => setBuildWaypoints(points => points.slice(0, -1))}>Desfazer última curva</button>}
          <button className="text-button" onClick={() => { setBuildOrigin(null); setBuildDestination(null); setBuildWaypoints([]); setBuildPick('origin'); setReplaceRoadId(null); }}>Limpar pontos</button>
          <div className="field"><label>Nome da estrada</label><input value={buildName} onChange={event => setBuildName(event.target.value)} /></div>
          <div className="field"><label>Nome do cenário salvo</label><input value={buildScenarioName} onChange={event => setBuildScenarioName(event.target.value)} /></div>
          <div className="field"><label>Sentido</label><select value={buildDirection} onChange={event => setBuildDirection(event.target.value as typeof buildDirection)}><option value="both">Mão dupla</option><option value="forward">A → B</option><option value="reverse">B → A</option></select></div>
          <div className="field"><label>Velocidade máxima: {buildSpeed} km/h</label><input type="range" min="10" max="80" step="5" value={buildSpeed} onChange={event => setBuildSpeed(Number(event.target.value))} /></div>
          <div className="field"><label>Faixas por sentido</label><select value={buildLanes} onChange={event => setBuildLanes(Number(event.target.value))}>{[1, 2, 3, 4].map(value => <option key={value} value={value}>{value}</option>)}</select></div>
          <div className="field"><label>Capacidade estimada (carros/h)</label><input type="number" min="100" max="8000" value={buildCapacity} onChange={event => setBuildCapacity(Number(event.target.value))} /></div>
          <div className="field"><label>Custo hipotético da obra (R$)</label><input type="number" min="0" value={buildCost} onChange={event => setBuildCost(Number(event.target.value))} /></div>
          {buildOrigin && buildDestination && <div className="route-preview">Comprimento geométrico aproximado: {number([buildOrigin.coordinates, ...buildWaypoints, buildDestination.coordinates].slice(1).reduce((total, point, index) => { const previous = [buildOrigin.coordinates, ...buildWaypoints][index]; return total + Math.hypot((point[0] - previous[0]) * 99_000, (point[1] - previous[1]) * 111_000); }, 0))} m</div>}
          <button className="primary-button wide" disabled={!buildOrigin || !buildDestination || building || !buildName.trim()} onClick={createRoad}>{building ? 'Reconstruindo a rede…' : replaceRoadId ? 'Salvar edição e reiniciar' : 'Construir e reiniciar'}</button>
          <p className="micro-note">O comprimento físico é calculado pela geometria. Capacidade e custo são hipóteses registradas; faixas e limite de velocidade alteram a rede SUMO. A reconstrução reinicia os carros ativos.</p></section>
          <section className="panel-section"><div className="section-heading"><span><MapPin size={17} /> Cenários desta cidade</span></div>
            <div className="urban-list"><div><strong>Rede original da cidade</strong><button disabled={building || !urbanNetworks?.active} onClick={() => urbanAction('/urban/base/activate')}>Ativar</button></div>
              {(urbanNetworks?.scenarios || []).map(scenario => <div key={scenario.id}><strong>{scenario.name}{urbanNetworks?.active === scenario.id ? ' · ativo' : ''}</strong><small>Versão {scenario.network_version} · {scenario.roads.length} ruas novas</small>
                <button disabled={building || urbanNetworks?.active === scenario.id} onClick={() => urbanAction(`/urban/networks/${scenario.id}/activate`)}>Ativar</button></div>)}</div>
            {urbanNetworks?.active && <div className="urban-list">{urbanNetworks.scenarios.find(item => item.id === urbanNetworks.active)?.roads.map(road => <div key={road.id}><strong>{road.name}</strong><small>{number(road.length_m)} m · {road.oneway ? 'mão única' : 'mão dupla'} · {road.speed_kmh} km/h</small><div><button onClick={() => { setBuildOrigin({ coordinates: road.origin_coordinates, edge_id: '', name: 'Início atual', position: 0, distance_m: 0 }); setBuildDestination({ coordinates: road.destination_coordinates, edge_id: '', name: 'Fim atual', position: 0, distance_m: 0 }); setBuildWaypoints(road.via || []); setBuildDirection(road.direction || (road.oneway ? 'forward' : 'both')); setBuildPick('via'); setBuildName(road.name); setBuildSpeed(road.speed_kmh); setBuildLanes(road.lanes); setBuildCapacity(road.capacity_estimate); setBuildCost(road.hypothetical_cost); setReplaceRoadId(road.id); }}>Editar</button><button disabled={building} onClick={() => urbanAction(`/urban/roads/${road.id}`, 'DELETE')}>Remover</button></div></div>)}</div>}</section></>}

        {tool === 'maps' && <><section className="panel-section"><div className="section-heading"><span><MapPin size={17} /> Mapas disponíveis</span></div>
          <p className="panel-copy">Cada mapa tem seus próprios arquivos OSM, grafo e cenários. A cidade original permanece preservada. Ativar outra malha reinicia a simulação em pausa.</p>
          <p className="panel-copy">Esta malha exibe {number(baseRoads.features.length)} vias; {number(baseRoads.features.filter(feature => feature.properties?.name === 'Via sem nome').length)} ainda aparecem sem nome. Ruas ausentes precisam de dados OSM mais recentes ou de desenho manual em <b>Ruas e grafo → Construir estrada</b>.</p>
          <div className="urban-list">{(cityMaps?.cities || []).map(city => <div key={city.id || 'original'}><strong>{city.name}{cityMaps?.active === city.id ? ' · ativo' : ''}</strong>
            <small>{city.region || city.source} · versão {city.network_version}{city.drivable_edges ? ` · ${number(city.drivable_edges)} trechos` : ''}</small>
            <button disabled={mapImporting || cityMaps?.active === city.id} onClick={() => activateMap(city.id)}>Ativar</button></div>)}</div></section>
          <section className="panel-section"><div className="section-heading"><span><Plus size={17} /> Importar OSM XML</span></div>
            <p className="panel-copy">Exporte uma região do OpenStreetMap em formato .osm ou .osm.xml. A conversão para SUMO pode levar alguns minutos. Para uma cidade grande, selecione um recorte.</p>
            <div className="field"><label>Nome da cidade</label><input value={mapName} maxLength={100} onChange={event => setMapName(event.target.value)} placeholder="Ex.: Blumenau inteira" /></div>
            <div className="field"><label>Região ou bairro</label><input value={mapRegion} maxLength={100} onChange={event => setMapRegion(event.target.value)} placeholder="Ex.: Centro" /></div>
            <div className="field"><label>Arquivo OSM XML</label><input type="file" accept=".osm,.xml,.osm.xml,application/xml,text/xml" onChange={event => setMapFile(event.target.files?.[0] || null)} /></div>
            <label className="map-crop-toggle"><input type="checkbox" checked={mapCrop} onChange={event => setMapCrop(event.target.checked)} /> Recortar por coordenadas</label>
            {mapCrop && <div className="map-bounds-grid">{(['west', 'south', 'east', 'north'] as const).map(key => <label key={key}>{({ west: 'Oeste', south: 'Sul', east: 'Leste', north: 'Norte' })[key]}<input type="number" step="0.001" value={mapBounds[key]} onChange={event => setMapBounds(bounds => ({ ...bounds, [key]: Number(event.target.value) }))} /></label>)}</div>}
            <button className="primary-button wide" disabled={mapImporting || !mapName.trim() || !mapFile} onClick={importMap}>{mapImporting ? 'Processando a malha…' : 'Importar e validar no SUMO'}</button>
            <p className="micro-note">Fonte da rede: arquivo OSM fornecido por você. Os cenários sintéticos continuam separados dos dados importados.</p></section></>}

        {tool === 'light' && <section className="panel-section"><div className="section-heading"><span><Signal size={17} /> Semáforos reais do SUMO</span><HelpTip title="Entenda o sinal misto">Misto resume um cruzamento com movimentos de cores diferentes. Selecione uma faixa abaixo ou aproxime o mapa e clique no marcador da via. As fases são programas completos do SUMO; esta tela altera a duração, não abre uma faixa isolada imediatamente.</HelpTip></div>
          {selected?.kind === 'light' ? <><div className="inspector-id"><Signal size={20} />Cruzamento: {[...new Set(selected.value.movements.flatMap(item => [item.incoming_road, item.outgoing_road]).filter(Boolean))].slice(0, 2).join(' / ') || 'sem nome'}</div>
            <p className="signal-id">Controlador SUMO: {selected.value.id}</p>
            <div className={`signal-badge ${selected.value.aspect}`}>{signalNames[selected.value.aspect]}</div>
            <p className="panel-copy">Cada linha abaixo é uma conversão da faixa de entrada para a faixa de saída. A cor ao lado da via indica o estado atual daquele movimento.</p>
            <div className="movement-list">{selected.value.movements.map(movement => <button key={movement.id}
              className={selected.movement_id === movement.id ? 'selected' : ''}
              onClick={() => setSelection({ kind: 'light', value: selected.value, movement_id: movement.id })}>
              <span className={`movement-aspect ${movement.aspect}`} />
              <span><strong>{movement.incoming_road || 'Via sem nome'} → {movement.outgoing_road || 'Via sem nome'}</strong><small>{movement.incoming_lane} → {movement.outgoing_lane}</small></span>
              <b>{signalNames[movement.aspect]}</b></button>)}</div>
            {selected.movement_id && (() => { const movement = selected.value.movements.find(item => item.id === selected.movement_id); return movement ?
              <div className="movement-card"><span>FAIXA SELECIONADA · {signalNames[movement.aspect]}</span><strong>{movement.incoming_road || 'Via sem nome'} → {movement.outgoing_road || 'Via sem nome'}</strong><small>{movement.incoming_lane} → {movement.outgoing_lane}</small></div> : null; })()}
            <div className="signal-counts"><span className="red">● {selected.value.movements.filter(item => item.aspect === 'closed').length} movimentos vermelhos</span><span className="yellow">● {selected.value.movements.filter(item => item.aspect === 'attention').length} amarelos</span><span className="green">● {selected.value.movements.filter(item => item.aspect === 'open').length} verdes</span></div>
            <div className="data-grid"><div>FASE ATUAL<strong>{selected.value.phase + 1}</strong></div><div>PRÓXIMA TROCA<strong>{number(Math.max(0, selected.value.next_switch - (snapshot?.sim_time || 0)))} s</strong></div></div>
            <h3 className="phase-title">Programação das fases <HelpTip title="Quais vias podem passar?">Verde e amarelo são derivados do programa válido do SUMO. Selecione uma faixa acima para ver seu estado em cada fase. Ajustar a duração preserva a sequência de segurança do controlador.</HelpTip></h3>
            <div className="phase-list">{selected.value.phases.map(phase => { const selectedMovement = selected.value.movements.find(item => item.id === selected.movement_id);
              const aspect = selectedMovement ? phase.state[selectedMovement.index] : null;
              const green = selected.value.movements.filter(item => 'gG'.includes(phase.state[item.index] || 'r'));
              return <div key={phase.index} className={`phase-row-detailed ${phase.index === selected.value.phase ? 'current' : ''}`}>
                <div><strong>Fase {phase.index + 1}{phase.index === selected.value.phase ? ' · agora' : ''}</strong><small>{number(phase.duration)} s atuais</small></div>
                {selectedMovement && <span className={`phase-selected ${aspect && 'gG'.includes(aspect) ? 'open' : aspect && 'yY'.includes(aspect) ? 'attention' : 'closed'}`}>Faixa escolhida: {aspect && 'gG'.includes(aspect) ? 'verde' : aspect && 'yY'.includes(aspect) ? 'amarelo' : 'vermelho'}</span>}
                <p>{green.length ? `Passam: ${[...new Set(green.map(item => item.incoming_road || item.incoming_lane))].slice(0, 4).join(', ')}${green.length > 4 ? '…' : ''}` : 'Nenhuma faixa liberada nesta fase.'}</p>
                <button disabled={!active || busy} onClick={() => act('/light', { tls_id: selected.value.id, phase: phase.index, duration: phaseDuration })}>Definir duração: {phaseDuration} s</button>
              </div>; })}</div>
            <div className="field"><label>Nova duração: {phaseDuration} s</label><input type="range" min="3" max="120" value={phaseDuration} onChange={event => setPhaseDuration(Number(event.target.value))} /></div>
            <button className="wide" disabled={!active || busy} onClick={() => act('/light', { tls_id: selected.value.id, restore: true })}>Restaurar programação</button>
            <p className="micro-note">A mudança de duração entra no ciclo do controlador. Ela não força o sinal a mudar de cor no clique.</p></> : <p className="panel-copy">No zoom geral, cada ponto resume o cruzamento. A partir do zoom próximo, os estados aparecem separados nas faixas de entrada.</p>}</section>}

        {tool === 'weather' && <section className="panel-section"><div className="section-heading"><span><CloudSun size={17} /> Condição climática</span></div>
          <div className="weather-options">{[['sun', 'Sol', CloudSun], ['light_rain', 'Chuva fraca', CloudRain], ['heavy_rain', 'Chuva forte', CloudRain]].map(([key, label, Icon]) => <button key={String(key)} className={snapshot?.weather === key ? 'chosen' : ''} disabled={!active || busy} onClick={() => act('/weather', { weather: key })}><Icon size={18} /><span>{String(label)}</span></button>)}</div>
          <div className="data-grid weather-data"><div>FATOR DE VELOCIDADE<strong>{number((snapshot?.weather_modifiers?.speed_factor || 1) * 100)}%</strong></div><div>TEMPO DE SEGURANÇA<strong>{number(snapshot?.weather_modifiers?.tau || 1, 1)} s</strong></div><div>ACELERAÇÃO<strong>{number(snapshot?.weather_modifiers?.accel || 2.6, 1)} m/s²</strong></div><div>FRENAGEM<strong>{number(snapshot?.weather_modifiers?.decel || 4.5, 1)} m/s²</strong></div></div></section>}

        {tool === 'gps' && <section className="panel-section"><div className="section-heading"><span><GitBranch size={17} /> GPS da frota</span></div>
          <p className="panel-copy">Cada carro dinâmico calcula a própria rota no intervalo definido. O custo de cada via usa a velocidade média dos outros carros observada pelo SUMO.</p>
          <div className="field"><label>Recalcular a cada {globalInterval} s</label><input type="range" min="5" max="180" step="5" value={globalInterval} onChange={event => setGlobalInterval(Number(event.target.value))} /></div>
          <div className="field"><label>Economia mínima para trocar: {globalBenefit}%</label><input type="range" min="0" max="50" value={globalBenefit} onChange={event => setGlobalBenefit(Number(event.target.value))} /></div>
          <div className="field"><label>Novos motoristas com GPS dinâmico: {globalDynamic}%</label><input type="range" min="0" max="100" step="10" value={globalDynamic} onChange={event => setGlobalDynamic(Number(event.target.value))} /></div>
          <button className="primary-button wide" disabled={busy} onClick={() => act('/gps', { interval: globalInterval, benefit: globalBenefit / 100, dynamic_percent: globalDynamic / 100 })}>Aplicar à frota</button>
          <p className="panel-copy">A configuração individual de um carro prevalece. Selecione um veículo para ajustá-lo separadamente.</p></section>}

        {tool === 'clock' && <section className="panel-section"><div className="section-heading"><span><Clock3 size={17} /> Relógio da cidade</span></div>
          <div className="loop-clock"><span>HORA SIMULADA</span><strong>{clock(snapshot?.clock_hour ?? chosenHour())}</strong><em>cenário sintético</em></div>
          <p className="panel-copy">Escolha a hora antes de iniciar ou ajuste o relógio durante a execução. O horário previsto dos carros usa este relógio.</p>
          <div className="clock-presets">{[6, 8, 12, 18].map(hour => <button key={hour} onClick={() => { setClockInput(`${String(hour).padStart(2, '0')}:00`); setLoopStart(hour); if (active) act('/clock', { hour }); }}>{clock(hour)}</button>)}</div>
          <div className="field"><label>Horário personalizado</label><input type="time" value={clockInput} onChange={event => setClockInput(event.target.value)} /></div>
          <button className="primary-button wide" onClick={setClock}>Aplicar horário</button>
          <p className="panel-copy">Os perfis de pico do loop são parâmetros sintéticos configuráveis, sem calibração por contagens reais de Blumenau.</p></section>}

        {tool === 'loop' && <section className="panel-section"><div className="section-heading"><span><RotateCcw size={17} /> Demanda diária em loop</span></div>
          <div className="loop-clock"><span>HORA SIMULADA</span><strong>{clock(snapshot?.clock_hour ?? loopStart)}</strong><em>{snapshot?.loop?.peak ? 'HORÁRIO DE PICO' : 'FLUXO NORMAL'}</em></div>
          <p className="panel-copy">O relógio percorre 24 horas e volta ao início. A geração usa segundos simulados; 5× acelera o dia sem alterar o comportamento físico dos carros.</p>
          <div className="field"><label>Começar às {clock(loopStart)}</label><input type="range" min="0" max="23.5" step="0.5" value={loopStart} onChange={event => setLoopStart(Number(event.target.value))} /></div>
          <div className="field"><label>Fluxo normal: {loopBase} carros/min</label><input type="range" min="1" max="30" value={loopBase} onChange={event => setLoopBase(Number(event.target.value))} /></div>
          <div className="field"><label>Pico: {loopPeak}× o fluxo normal</label><input type="range" min="1" max="6" value={loopPeak} onChange={event => setLoopPeak(Number(event.target.value))} /></div>
          <div className="loop-peaks"><span>Manhã <b>07:00–09:00</b></span><span>Tarde <b>17:00–19:00</b></span></div>
          <div className="route-preview"><CarFront size={16} /> Agora: {number(snapshot?.loop?.vehicles_per_minute || 0, 1)} carros/min</div>
          <button className="primary-button wide" disabled={!active || busy} onClick={() => loopAction(!snapshot?.loop?.enabled)}>{snapshot?.loop?.enabled ? 'Pausar geração em loop' : 'Ativar loop diário'}</button>
          {snapshot?.loop?.enabled && <button className="wide secondary-action" disabled={busy} onClick={() => loopAction(true)}>Aplicar novos parâmetros</button>}</section>}
      </div>
    </aside>
    <footer className="sim-bar"><div className="transport"><button className="play-button" disabled={busy || !snapshot?.ready}
      title={running ? 'Pausar' : 'Iniciar'} onClick={() => running ? act('/pause') : active ? act('/resume') : act('/start', { seed, start_hour: chosenHour() }, true)}>
      {running ? <Pause size={19} fill="currentColor" /> : <Play size={19} fill="currentColor" />}</button>
      <button className="transport-button" disabled={busy || !snapshot?.ready} title="Reiniciar" onClick={() => act('/reset', { seed, start_hour: chosenHour() }, true)}><RotateCcw size={19} /></button>
      <button className="transport-button" disabled={!active || busy || running} title="Avançar um segundo" onClick={() => act('/step')}><Plus size={19} /></button></div>
      <div className="bar-divider" /><div className="time-readout"><small>TEMPO SIMULADO</small><strong>{duration(snapshot?.sim_time)}</strong></div>
      <div className="day-readout"><small>HORA DA CIDADE</small><strong>{clock(snapshot?.clock_hour ?? chosenHour())} {snapshot?.loop?.peak && snapshot.loop.enabled ? '· PICO' : ''}</strong></div>
      <div className="bar-divider" /><div className="speed-group"><span>VELOCIDADE</span>{[0.5, 1, 2, 5].map(value => <button key={value} className={(snapshot?.speed || 1) === value ? 'selected' : ''} onClick={() => act('/speed', { speed: value })}>{value}×</button>)}</div>
      <div className="bar-spacer" /><div className="bar-stat"><span className="stat-icon teal"><CarFront size={18} /></span><div><small>VEÍCULOS ATIVOS</small><strong>{number(snapshot?.active)}</strong></div></div>
      <div className="bar-stat"><span className="stat-icon amber"><Zap size={18} /></span><div><small>DESVIOS GPS</small><strong>{number(snapshot?.reroutes)}</strong></div></div></footer>
  </main>;
}
