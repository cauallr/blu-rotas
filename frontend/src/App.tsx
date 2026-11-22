import { useCallback, useEffect, useState } from 'react';
import { Activity, AlertTriangle, BarChart3, CarFront, CircleHelp, Download, FlaskConical, GitBranch, MapPinned, Maximize2, Minimize2, Moon, PanelLeftClose, PanelLeftOpen, Sun, Zap } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import CityView from './CityView';
import SimulationsPage from './SimulationsPage';
import type { FeatureCollection, RoadNetwork, Snapshot } from './types';

const API = '/api';
const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
async function request<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`${API}${path}`, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data as T;
}
const duration = (seconds = 0) => `${String(Math.floor(seconds / 3600)).padStart(2, '0')}:${String(Math.floor(seconds % 3600 / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
const number = (value = 0, digits = 0) => Number(value).toLocaleString('pt-BR', { maximumFractionDigits: digits });

export default function App() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    try { return localStorage.getItem('blu-rotas-theme') === 'light' ? 'light' : 'dark'; }
    catch { return 'dark'; }
  });
  const [tab, setTab] = useState<'city' | 'simulations' | 'science' | 'lab'>('city');
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [fullscreen, setFullscreen] = useState(Boolean(document.fullscreenElement));
  const [network, setNetwork] = useState<RoadNetwork>(empty);
  const [baseRoads, setBaseRoads] = useState<FeatureCollection>(empty);
  const [places, setPlaces] = useState<FeatureCollection>(empty);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [seed, setSeed] = useState(42);
  const [metrics, setMetrics] = useState<{ samples: Record<string, number>[]; trips: Record<string, string | number>[]; interventions: Record<string, string | number>[] }>({ samples: [], trips: [], interventions: [] });
  const [graph, setGraph] = useState<{ vertices: number; edges: number; density: number; components: number } | null>(null);
  const [graphStart, setGraphStart] = useState('');
  const [graphEnd, setGraphEnd] = useState('');
  const [graphResult, setGraphResult] = useState<{ path: string[]; distance: number } | null>(null);
  const [scenarioName, setScenarioName] = useState('Experimento Blumenau');
  const [scenarios, setScenarios] = useState<{ id: number; name: string; config: Record<string, unknown> }[]>([]);
  const [cities, setCities] = useState<{ id: number; name: string }[]>([]);
  const [cityName, setCityName] = useState('');
  const [benchmarks, setBenchmarks] = useState<Record<string, number>[]>([]);
  useEffect(() => { try { localStorage.setItem('blu-rotas-theme', theme); } catch { /* armazenamento opcional */ } }, [theme]);
  useEffect(() => {
    const update = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', update);
    return () => document.removeEventListener('fullscreenchange', update);
  }, []);
  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch { setNotice('O navegador não permitiu abrir em tela cheia. Use F11 como alternativa.'); }
  };

  useEffect(() => {
    request<RoadNetwork>('/network').then(setNetwork).catch(e => setNotice(e.message));
    request<FeatureCollection>('/roads/base').then(setBaseRoads).catch(e => setNotice(e.message));
    request<FeatureCollection>('/places').then(setPlaces).catch(() => {});
    request<Snapshot>('/status').then(setSnapshot).catch(e => setNotice(e.message));
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout>;
    let closed = false;
    const connect = () => {
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
      socket.onmessage = event => setSnapshot(JSON.parse(event.data));
      socket.onclose = () => { if (!closed) retry = setTimeout(connect, 1500); };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); socket?.close(); };
  }, []);

  const refreshNetwork = useCallback(() => request<RoadNetwork>('/network').then(setNetwork), []);
  const refreshCity = useCallback(async () => {
    const [roads, base, neighborhoods] = await Promise.all([
      request<RoadNetwork>('/network'), request<FeatureCollection>('/roads/base'), request<FeatureCollection>('/places')]);
    setNetwork(roads); setBaseRoads(base); setPlaces(neighborhoods);
  }, []);
  const [chosenSpeed, setChosenSpeed] = useState<number | null>(null);

  const act = useCallback(async (path: string, body?: object, reload = false) => {
    setBusy(true); setNotice('');
    try {
      const result = await request<Snapshot | Record<string, unknown>>(path, body || {});
      if (path === '/speed' && typeof result.speed === 'number') {
        const speed = result.speed;
        setChosenSpeed(speed);
        setSnapshot(current => current ? { ...current, speed } : current);
      }
      if ('connected' in result) setSnapshot(result as Snapshot);
      if (path === '/road' || /^\/vehicles\/[^/]+\/route$/.test(path)) setSnapshot(await request<Snapshot>('/status'));
      if (reload) await refreshNetwork();
      return result;
    } catch (error) {
      setNotice((error as Error).message);
      return null;
    } finally { setBusy(false); }
  }, [refreshNetwork]);

  useEffect(() => {
    if (tab === 'science') {
      const update = () => request<typeof metrics>('/metrics').then(setMetrics).catch(() => {});
      update(); const interval = setInterval(update, 4000); return () => clearInterval(interval);
    }
    if (tab === 'lab') {
      request<typeof graph>('/graph/stats').then(setGraph).catch(() => {});
      request<{ cities: { id: number; name: string }[] }>('/municipalities').then(data => setCities(data.cities)).catch(() => {});
      request<Record<string, number>[]>('/municipalities/benchmarks').then(setBenchmarks).catch(() => {});
    }
  }, [tab, snapshot?.run_id]);

  useEffect(() => { if (tab === 'science') request<typeof scenarios>('/scenarios').then(setScenarios).catch(() => {}); }, [tab, snapshot?.run_id]);
  const cityMutation = async (path: string, method: string, body?: object) => {
    try {
      const response = await fetch(`${API}${path}`, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
      if (!response.ok) throw new Error((await response.json()).detail);
      const data = await request<{ cities: { id: number; name: string }[] }>('/municipalities');
      setCities(data.cities);
      setCityName('');
    } catch (error) { setNotice((error as Error).message); }
  };

  const active = Boolean(snapshot?.connected);
  const running = Boolean(snapshot?.running);
  return <div className={`app-shell${railCollapsed ? ' rail-collapsed' : ''}`} data-theme={theme}>
    <aside className="rail">
      <div className="brand-mark"><MapPinned size={24} strokeWidth={2.2} /></div>
      <div className="rail-divider" />
      <button className={tab === 'city' ? 'rail-button active' : 'rail-button'} title="Cidade" onClick={() => setTab('city')}><MapPinned size={21} /></button>
      <button className={tab === 'simulations' ? 'rail-button active' : 'rail-button'} title="Simulações" onClick={() => setTab('simulations')}><FlaskConical size={21} /></button>
      <button className={tab === 'science' ? 'rail-button active' : 'rail-button'} title="Ciência" onClick={() => setTab('science')}><BarChart3 size={21} /></button>
      <button className={tab === 'lab' ? 'rail-button active' : 'rail-button'} title="Laboratório de grafos" onClick={() => setTab('lab')}><GitBranch size={21} /></button>
      <div className="rail-spacer" /><a className="rail-button" title="Tutorial de situações" href="/tutorial_de_situações.html" target="_blank" rel="noreferrer"><CircleHelp size={20} /></a>
    </aside>
    <div className="app-main">
      <header className="topbar">
        <div className="identity"><button className="header-icon-button" title={railCollapsed ? 'Mostrar barra lateral' : 'Ocultar barra lateral'} onClick={() => setRailCollapsed(value => !value)}>{railCollapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}</button><div><div className="eyebrow">SIMULADOR URBANO • {snapshot?.city_name || 'BLUMENAU CENTRAL'}</div><div className="logo">BLU<span>—</span>ROTAS <small>v2.0</small></div></div></div>
        <nav className="topnav"><button className={tab === 'city' ? 'current' : ''} onClick={() => setTab('city')}>Cidade</button><button className={tab === 'simulations' ? 'current' : ''} onClick={() => setTab('simulations')}>Simulações</button><button className={tab === 'science' ? 'current' : ''} onClick={() => setTab('science')}>Dados</button><button className={tab === 'lab' ? 'current' : ''} onClick={() => setTab('lab')}>Grafos</button></nav>
        <div className="top-actions"><button className="header-icon-button" title={fullscreen ? 'Sair da tela cheia' : 'Tela cheia'} onClick={toggleFullscreen}>{fullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}</button><button className="theme-toggle" title={theme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro'} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}<span>{theme === 'dark' ? 'Claro' : 'Escuro'}</span></button><div className={`engine-badge ${active ? 'online' : ''}`}><span className="pulse-dot" />{active ? running ? 'SUMO EM EXECUÇÃO' : 'SUMO PAUSADO' : snapshot?.ready ? 'SUMO PRONTO' : 'REDE SUMO PENDENTE'}</div></div>
      </header>
      {notice && <div className="notice"><AlertTriangle size={17} />{notice}<button onClick={() => setNotice('')}>×</button></div>}
      {tab === 'city' && <CityView network={network} baseRoads={baseRoads} places={places} snapshot={snapshot} chosenSpeed={chosenSpeed} act={act} busy={busy} seed={seed} theme={theme} setNotice={setNotice} refreshCity={refreshCity} />}
      {tab === 'science' && <main className="content-page"><div className="page-heading"><div><div className="eyebrow">ANÁLISE EXPERIMENTAL</div><h1>Modo Ciência</h1><p>Indicadores derivados das viagens e amostras gravadas pelo SUMO.</p></div><FlaskConical size={42} /></div><div className="metric-cards"><Metric title="Veículos ativos" value={number(snapshot?.active)} icon={<CarFront size={20} />} /><Metric title="Viagens concluídas" value={number(snapshot?.completed)} icon={<Activity size={20} />} /><Metric title="Velocidade média" value={`${number((snapshot?.sample?.mean_speed || 0) * 3.6, 1)} km/h`} icon={<Zap size={20} />} /><Metric title="Tempo médio" value={duration(snapshot?.sample?.mean_travel)} icon={<BarChart3 size={20} />} /><Metric title="Alterações de rota" value={number(snapshot?.reroutes)} icon={<GitBranch size={20} />} /></div><div className="chart-grid"><div className="chart-card"><h3>Veículos ativos</h3><ResponsiveContainer width="100%" height={240}><AreaChart data={metrics.samples}><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#48d9c5" stopOpacity={0.4}/><stop offset="100%" stopColor="#48d9c5" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#29404b" strokeDasharray="3 4" /><XAxis dataKey="sim_time" stroke="#69828d" /><YAxis stroke="#69828d" /><Tooltip /><Area type="monotone" dataKey="active" stroke="#48d9c5" fill="url(#area)" /></AreaChart></ResponsiveContainer></div><div className="chart-card"><h3>Velocidade média (m/s)</h3><ResponsiveContainer width="100%" height={240}><LineChart data={metrics.samples}><CartesianGrid stroke="#29404b" strokeDasharray="3 4" /><XAxis dataKey="sim_time" stroke="#69828d" /><YAxis stroke="#69828d" /><Tooltip /><Line type="monotone" dataKey="mean_speed" stroke="#f7b56d" dot={false} strokeWidth={3} /></LineChart></ResponsiveContainer></div></div><div className="science-bottom"><div className="chart-card"><h3>Experimento reproduzível</h3><p>Salve a configuração atual, a semente e as viagens geradas.</p><div className="inline-form"><input value={scenarioName} onChange={e => setScenarioName(e.target.value)} /><button className="primary-button" onClick={async () => { const result = await act('/scenarios', { name: scenarioName }); if (result) setScenarios(await request('/scenarios')); }}>Salvar cenário</button></div><div className="inline-form"><label>Semente</label><input type="number" value={seed} onChange={e => setSeed(Number(e.target.value))} /></div><div className="saved-scenarios">{scenarios.map(scenario => <div key={scenario.id}><span>{scenario.name} <small>#{scenario.id}</small></span><button onClick={async () => { const result = await act(`/scenarios/${scenario.id}/run`, undefined, true); if (result) { await refreshCity(); setTab('city'); } }}>Executar novamente</button></div>)}</div></div><div className="chart-card"><h3>Exportação</h3><p>{metrics.samples.length} amostras • {metrics.trips.length} viagens • {metrics.interventions.length} intervenções</p><div className="export-buttons">{['samples', 'trips', 'interventions'].map(t => <a key={t} href={`${API}/export/${t}.csv`} download><Download size={16} /> {t}.csv</a>)}</div></div></div></main>}
      {tab === 'simulations' && <SimulationsPage snapshot={snapshot} theme={theme} openCity={() => setTab('city')} openData={() => setTab('science')} />}
      {tab === 'lab' && <main className="content-page"><div className="page-heading"><div><div className="eyebrow">TEORIA DOS GRAFOS</div><h1>Laboratório de Grafos</h1><p>Algoritmos próprios aplicados às conexões dirigidas da rede SUMO.</p></div><GitBranch size={42} /></div><div className="metric-cards"><Metric title="Vértices" value={number(graph?.vertices)} icon={<GitBranch size={20} />} /><Metric title="Arestas" value={number(graph?.edges)} icon={<Activity size={20} />} /><Metric title="Componentes fracos" value={number(graph?.components)} icon={<MapPinned size={20} />} /><Metric title="Densidade" value={number(graph?.density, 5)} icon={<BarChart3 size={20} />} /></div><div className="chart-card lab-card"><h3>Encontrar caminho mínimo</h3><p>Informe IDs das vias da rede SUMO. Dijkstra considera o tempo estimado em cada trecho.</p><div className="inline-form"><input placeholder="Via de origem" value={graphStart} onChange={e => setGraphStart(e.target.value)} /><input placeholder="Via de destino" value={graphEnd} onChange={e => setGraphEnd(e.target.value)} /><button className="primary-button" onClick={async () => { try { setGraphResult(await request('/graph/path', { start: graphStart, end: graphEnd })); } catch (e) { setNotice((e as Error).message); } }}>Calcular rota</button></div>{graphResult && <div className="route-result"><strong>{graphResult.path.length ? `${graphResult.path.length} trechos • custo ${number(graphResult.distance, 1)} s` : 'Sem rota válida'}</strong><p>{graphResult.path.join(' → ')}</p></div>}</div><div className="chart-card lab-card"><h3>Municípios brasileiros • CRUD</h3><p>Grafo acadêmico separado da rede urbana. Cadastre cidades, altere nomes e monte ligações pela API.</p><div className="inline-form"><input placeholder="Nome do município" value={cityName} onChange={e => setCityName(e.target.value)} /><button className="primary-button" onClick={() => cityMutation('/municipalities', 'POST', { name: cityName })}>Adicionar</button></div><div className="saved-scenarios">{cities.map(city => <div key={city.id}><span>{city.name} <small>#{city.id}</small></span><button onClick={() => { const name = prompt('Novo nome do município', city.name); if (name) cityMutation(`/municipalities/${city.id}`, 'PUT', { name }); }}>Renomear</button><button onClick={() => cityMutation(`/municipalities/${city.id}`, 'DELETE')}>Excluir</button></div>)}</div></div><div className="chart-card lab-card"><h3>Experimentos de escala</h3><p>Tempos medidos nesta máquina, em nanossegundos. Grafos gerados com semente fixa.</p><div className="table-wrap"><table><thead><tr><th>Cidades</th><th>Arestas</th><th>Dijkstra heap</th><th>Fila simples</th><th>Matriz</th></tr></thead><tbody>{benchmarks.map(row => <tr key={row.cities}><td>{row.cities}</td><td>{row.edges}</td><td>{number(row.dijkstra_heap_ns)}</td><td>{number(row.dijkstra_simple_ns)}</td><td>{number(row.dijkstra_matrix_ns)}</td></tr>)}</tbody></table></div></div></main>}
    </div>
  </div>;
}

function Metric({ title, value, icon }: { title: string; value: string; icon: React.ReactNode }) { return <div className="metric-card"><div className="metric-icon">{icon}</div><span>{title}</span><strong>{value}</strong></div>; }
