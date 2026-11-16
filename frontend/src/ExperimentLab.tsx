import { useEffect, useState } from 'react';
import { BarChart3, Download, FlaskConical, Play, RotateCcw } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ReplayMap, { type ReplayFrame } from './ReplayMap';
import type { FeatureCollection, Snapshot } from './types';

type Kind = 'gps' | 'signals' | 'saturation' | 'roadworks' | 'new_road' | 'weather' | 'custom';
type Job = { id: string; name: string; kind: Kind; status: { state: string; progress: number; run?: string; error?: string } };
type Summary = { vehicles: number; completed: number; unfinished: number; completion_rate: number; mean_travel_s: number | null;
  median_travel_s: number | null; p95_travel_s: number | null; mean_waiting_s: number | null; mean_distance_m: number | null;
  mean_speed_mps: number | null; reroutes: number; mean_queue: number | null; duration_s: number;
  fictional_road_vehicles?: number; route_distribution?: { route: string[]; vehicles: number }[] };
type Run = { id: string; variant: string; variant_label: string; repetition: number; seed: number; summary: Summary;
  parameters: Record<string, unknown>; network_version: string; demand_hash: string };
type Detail = { config: { id: string; name: string; question: string; hypothesis: string; kind: Kind; seed: number; vehicles: number;
  repetitions: number; code_version: string; source_network_version: string; mode: string; limitations: string[];
  variants: { key: string; label: string; parameters: Record<string, unknown> }[] };
  status: Job['status']; results: { runs: Run[]; aggregates: Record<string, { label: string; mean_travel_s: number | null;
    mean_completion_rate: number | null; mean_waiting_s: number | null; confidence_interval_95: { lower: number; upper: number; n: number } | null }>;
    interpretation: string; limitations: string[] } | null };
type Comparison = { comparison: { metrics: Record<string, { a: number | null; b: number | null; difference: number | null; percent: number | null }>;
  changed_parameters: string[]; paired: boolean; directly_comparable: boolean; interpretation: string;
  road_impacts: { id: string; name: string; queue_a: number; queue_b: number; queue_difference: number; vehicles_a: number; vehicles_b: number }[] } };
const presets: { kind: Kind; label: string; question: string }[] = [
  { kind: 'gps', label: 'A · GPS', question: 'Rotas dinâmicas reduzem o tempo?' },
  { kind: 'signals', label: 'B · Semáforos', question: 'O verde altera as filas?' },
  { kind: 'saturation', label: 'C · Saturação', question: 'Quando o atraso acelera?' },
  { kind: 'roadworks', label: 'D · Obras', question: 'Para onde migra o trânsito?' },
  { kind: 'new_road', label: 'E · Nova estrada', question: 'Uma conexão sempre melhora?' },
  { kind: 'weather', label: 'F · Clima', question: 'Como a chuva afeta o fluxo?' },
  { kind: 'custom', label: 'Personalizado', question: 'Monte suas variantes.' }
];
const number = (value: number | null | undefined, digits = 1) => value == null ? '—' : value.toLocaleString('pt-BR', { maximumFractionDigits: digits });
const duration = (seconds: number) => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
const empty: FeatureCollection = { type: 'FeatureCollection', features: [] };
async function getJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || response.statusText);
  return data as T;
}

export default function ExperimentLab({ snapshot, theme }: { snapshot: Snapshot | null; theme: 'dark' | 'light' }) {
  const [kind, setKind] = useState<Kind>('gps');
  const [name, setName] = useState('');
  const [question, setQuestion] = useState('');
  const [hypothesis, setHypothesis] = useState('');
  const [independent, setIndependent] = useState('');
  const [vehicles, setVehicles] = useState(25);
  const [repetitions, setRepetitions] = useState(1);
  const [seed, setSeed] = useState(42);
  const [maxTime, setMaxTime] = useState(180);
  const [windowSeconds, setWindowSeconds] = useState(45);
  const [mode, setMode] = useState<'fast' | 'visual'>('fast');
  const [roadId, setRoadId] = useState('');
  const [tlsId, setTlsId] = useState('');
  const [customVariants, setCustomVariants] = useState('[{"key":"a","label":"GPS estático","parameters":{"gps_strategy":"static"}},{"key":"b","label":"GPS dinâmico","parameters":{"gps_strategy":"dynamic"}}]');
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<Detail | null>(null);
  const [details, setDetails] = useState<Record<string, Detail>>({});
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [compareA, setCompareA] = useState('');
  const [compareB, setCompareB] = useState('');
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [replayRun, setReplayRun] = useState('');
  const [replayFrames, setReplayFrames] = useState<ReplayFrame[]>([]);
  const [replayRoads, setReplayRoads] = useState<FeatureCollection>(empty);
  const [replayIndex, setReplayIndex] = useState(0);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(5);
  const [liveRun, setLiveRun] = useState('');
  const [liveFrame, setLiveFrame] = useState<ReplayFrame | null>(null);
  const [liveRoads, setLiveRoads] = useState<FeatureCollection>(empty);

  useEffect(() => {
    const update = () => getJSON<{ experiments: Job[] }>('/experiments').then(data => setJobs(data.experiments)).catch(() => {});
    update(); const timer = setInterval(update, 4000); return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!selectedId) return;
    const update = () => getJSON<Detail>(`/experiments/${selectedId}`).then(data => {
      setDetail(data); if (data.results) setDetails(items => ({ ...items, [selectedId]: data }));
    }).catch(err => setError(err.message));
    update(); const timer = setInterval(update, 2500); return () => clearInterval(timer);
  }, [selectedId]);
  useEffect(() => {
    const missing = jobs.filter(job => job.status.state === 'complete' && !details[job.id]);
    if (!missing.length) return;
    Promise.all(missing.map(job => getJSON<Detail>(`/experiments/${job.id}`).then(data => [job.id, data] as const)))
      .then(entries => setDetails(items => ({ ...items, ...Object.fromEntries(entries) }))).catch(() => {});
  }, [jobs, details]);
  useEffect(() => {
    if (!selectedId || detail?.status.state !== 'running' || detail.config.mode !== 'visual') return;
    let cancelled = false;
    const update = () => getJSON<{ run: string | null; frames: ReplayFrame[] }>(`/experiments/${selectedId}/live`).then(async data => {
      if (cancelled || !data.run) return;
      if (data.run !== liveRun) {
        const roads = await getJSON<FeatureCollection>(`/experiments/${selectedId}/live-network?run_id=${encodeURIComponent(data.run)}`);
        if (!cancelled) { setLiveRoads(roads); setLiveRun(data.run); }
      }
      if (!cancelled && data.frames.length) setLiveFrame(data.frames[data.frames.length - 1]);
    }).catch(() => {});
    update(); const timer = setInterval(update, 1500); return () => { cancelled = true; clearInterval(timer); };
  }, [selectedId, detail?.status.state, detail?.config.mode, liveRun]);
  useEffect(() => {
    if (!replayPlaying || !replayFrames.length) return;
    const interval = Math.max(100, ((replayFrames[1]?.time ?? 5) - replayFrames[0].time) * 1000 / replaySpeed);
    const timer = setInterval(() => setReplayIndex(index => {
      if (index + 1 >= replayFrames.length) { setReplayPlaying(false); return index; }
      return index + 1;
    }), interval);
    return () => clearInterval(timer);
  }, [replayPlaying, replayFrames, replaySpeed]);

  const submit = async () => {
    setError(''); setSubmitting(true);
    try {
      const body: Record<string, unknown> = { kind, name, question, hypothesis, independent_variable: independent,
        vehicles, repetitions, seed, duration_s: maxTime, departure_window_s: windowSeconds, mode,
        snapshot_interval_s: mode === 'visual' ? 1 : 5, road_id: roadId || null, tls_id: tlsId || null,
        modified_scenario_id: snapshot?.network_scenario_id || null };
      if (kind === 'custom') body.variants = JSON.parse(customVariants);
      const result = await getJSON<{ id: string }>('/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      setSelectedId(result.id);
      setJobs((await getJSON<{ experiments: Job[] }>('/experiments')).experiments);
    } catch (err) { setError((err as Error).message); }
    finally { setSubmitting(false); }
  };
  const repeat = async () => {
    if (!selectedId) return;
    try {
      const result = await getJSON<{ id: string }>(`/experiments/${selectedId}/repeat`, { method: 'POST' });
      setSelectedId(result.id); setError('');
    } catch (err) { setError((err as Error).message); }
  };
  const watch = async (runId: string) => {
    if (!selectedId) return;
    try {
      const [frames, roads] = await Promise.all([
        getJSON<{ frames: ReplayFrame[] }>(`/experiments/${selectedId}/frames?run_id=${encodeURIComponent(runId)}`),
        getJSON<FeatureCollection>(`/experiments/${selectedId}/network?run_id=${encodeURIComponent(runId)}`)]);
      setReplayFrames(frames.frames); setReplayRoads(roads); setReplayRun(runId); setReplayIndex(0); setReplayPlaying(true);
    } catch (err) { setError((err as Error).message); }
  };
  const doCompare = async () => {
    if (!compareA || !compareB) return;
    const [experimentA, runA] = compareA.split('|'); const [experimentB, runB] = compareB.split('|');
    try {
      setComparison(await getJSON<Comparison>(`/experiments/compare?experiment_a=${experimentA}&run_a=${runA}&experiment_b=${experimentB}&run_b=${runB}`));
    } catch (err) { setError((err as Error).message); }
  };
  const allRuns = Object.entries(details).flatMap(([jobId, data]) => (data.results?.runs || []).map(run => ({ jobId, run })));
  const chartData = detail?.results ? Object.entries(detail.results.aggregates).map(([key, item]) => ({ key,
    name: item.label, vehicles: Number(detail.config.variants.find(variant => variant.key === key)?.parameters.vehicle_limit || detail.config.vehicles),
    tempo: item.mean_travel_s, espera: item.mean_waiting_s, conclusao: (item.mean_completion_rate || 0) * 100 })) : [];
  const metricNames: Record<string, string> = { completion_rate: 'Taxa de conclusão', mean_travel_s: 'Tempo médio (s)',
    median_travel_s: 'Mediana (s)', p95_travel_s: 'P95 (s)', mean_waiting_s: 'Espera média (s)',
    mean_distance_m: 'Distância média (m)', mean_speed_mps: 'Velocidade média (m/s)', reroutes: 'Desvios GPS', mean_queue: 'Fila média' };

  return <section className="experiment-lab"><div className="experiment-heading"><div><div className="eyebrow">LABORATÓRIO CIENTÍFICO</div><h2>Experimentos reproduzíveis</h2><p>O SUMO avança em passos físicos de 0,25 s. O modo rápido só dispensa a renderização; demanda e regras do motor permanecem iguais.</p></div><FlaskConical size={35} /></div>
    <div className="preset-grid">{presets.map(item => <button key={item.kind} className={kind === item.kind ? 'active' : ''} onClick={() => { setKind(item.kind); setName(''); setQuestion(''); setHypothesis(''); }}><strong>{item.label}</strong><span>{item.question}</span></button>)}</div>
    <div className="experiment-form"><div className="field"><label>Nome do experimento</label><input placeholder={presets.find(item => item.kind === kind)?.label} value={name} onChange={event => setName(event.target.value)} /></div>
      <div className="field"><label>Pergunta científica</label><input placeholder="Use a pergunta do modelo ou escreva a sua" value={question} onChange={event => setQuestion(event.target.value)} /></div>
      <div className="field"><label>Hipótese</label><input placeholder="Use a hipótese do modelo ou escreva a sua" value={hypothesis} onChange={event => setHypothesis(event.target.value)} /></div>
      {kind === 'custom' && <div className="field"><label>Variável independente</label><input value={independent} onChange={event => setIndependent(event.target.value)} /></div>}
      <div className="field"><label>Veículos</label><select value={vehicles} onChange={event => setVehicles(Number(event.target.value))}>{[5, 10, 25, 50, 100, 250, 500].map(value => <option key={value} value={value}>{value}</option>)}</select></div>
      <div className="field"><label>Repetições</label><input type="number" min="1" max="20" value={repetitions} onChange={event => setRepetitions(Number(event.target.value))} /></div>
      <div className="field"><label>Semente</label><input type="number" value={seed} onChange={event => setSeed(Number(event.target.value))} /></div>
      <div className="field"><label>Duração máxima (s)</label><input type="number" min="30" max="3600" value={maxTime} onChange={event => setMaxTime(Number(event.target.value))} /></div>
      <div className="field"><label>Janela de partidas (s)</label><input type="number" min="1" max="600" value={windowSeconds} onChange={event => setWindowSeconds(Number(event.target.value))} /></div>
      <div className="field"><label>Modo</label><select value={mode} onChange={event => setMode(event.target.value as 'fast' | 'visual')}><option value="fast">Científico rápido</option><option value="visual">Visual em tempo real</option></select></div>
      {(kind === 'roadworks' || kind === 'custom') && <div className="field"><label>ID da via {kind === 'roadworks' ? '(vazio = primeira via com 2 faixas)' : '(para variante de obra)'}</label><input value={roadId} onChange={event => setRoadId(event.target.value)} /></div>}
      {(kind === 'signals' || kind === 'custom') && <div className="field"><label>ID do semáforo {kind === 'signals' ? '(vazio = primeiro)' : '(para variante de fase)'}</label><input value={tlsId} onChange={event => setTlsId(event.target.value)} /></div>}
      {kind === 'new_road' && <p className="experiment-note">Cenário de rua nova: {snapshot?.network_scenario_id || 'construa uma via em Modo Cidade antes de executar E'}.</p>}
      {kind === 'custom' && <div className="field custom-variants"><label>Variantes JSON (2 a 8)</label><textarea value={customVariants} onChange={event => setCustomVariants(event.target.value)} /></div>}
      <button className="primary-button run-experiment" disabled={submitting || (kind === 'new_road' && !snapshot?.network_scenario_id)} onClick={submit}><Play size={16} /> {submitting ? 'Preparando demanda…' : 'Executar experimento'}</button></div>
    {error && <div className="inline-warning">{error}</div>}
    <div className="experiment-results"><div className="experiment-list"><h3>Execuções salvas</h3>{jobs.map(job => <button key={job.id} className={selectedId === job.id ? 'active' : ''} onClick={() => setSelectedId(job.id)}><strong>{job.name}</strong><small>{job.id} · {job.status.state === 'complete' ? 'concluído' : job.status.state === 'error' ? 'erro' : `${number(job.status.progress * 100)}%`}</small></button>)}</div>
      <div className="experiment-detail">{detail ? <><div className="experiment-detail-header"><div><h3>{detail.config.name}</h3><p>{detail.config.question}</p></div><span>{detail.status.state === 'complete' ? 'CONCLUÍDO' : detail.status.state === 'error' ? 'ERRO' : 'EM EXECUÇÃO'}</span></div>
        {detail.status.state === 'running' && <div className="experiment-progress"><div style={{ width: `${Math.min(100, detail.status.progress * 100)}%` }} /><span>{number(detail.status.progress * 100)}% · {detail.status.run || 'Preparando'}</span></div>}
        {detail.status.error && <div className="inline-warning">{detail.status.error}</div>}
        {detail.status.state === 'running' && detail.config.mode === 'visual' && liveFrame && <div className="replay-card"><h4>Observação ao vivo · {liveRun}</h4><ReplayMap roads={liveRoads} frame={liveFrame} theme={theme} /><div className="replay-stats">{duration(liveFrame.time)} · {liveFrame.active} ativos · {liveFrame.completed} concluídos</div></div>}
        {detail.results && <><div className="experiment-meta"><span>Hipótese: {detail.config.hypothesis}</span><span>Semente {detail.config.seed} · {detail.config.vehicles} veículos · {detail.config.repetitions} repetição(ões)</span><span>Código {detail.config.code_version} · rede {detail.config.source_network_version}</span></div>
          <div className="experiment-chart"><ResponsiveContainer width="100%" height={250}>{detail.config.kind === 'saturation'
            ? <LineChart data={chartData}><CartesianGrid stroke="#49606b" strokeDasharray="3 4" /><XAxis dataKey="vehicles" type="number" domain={['dataMin', 'dataMax']} stroke="#81999e" label={{ value: 'Veículos', position: 'insideBottom', offset: -4 }} /><YAxis stroke="#81999e" /><Tooltip /><Line type="monotone" dataKey="tempo" name="Tempo médio (s)" stroke="#52ddc7" strokeWidth={3} connectNulls={false} /><Line type="monotone" dataKey="espera" name="Espera média (s)" stroke="#f5b96f" strokeWidth={2} /></LineChart>
            : <BarChart data={chartData}><CartesianGrid stroke="#49606b" strokeDasharray="3 4" /><XAxis dataKey="name" stroke="#81999e" tick={{ fontSize: 10 }} /><YAxis stroke="#81999e" /><Tooltip /><Bar dataKey="tempo" name="Tempo médio (s)" fill="#52ddc7" /><Bar dataKey="espera" name="Espera média (s)" fill="#f5b96f" /></BarChart>}</ResponsiveContainer></div>
          <div className="table-wrap"><table><thead><tr><th>Variante</th><th>Tempo médio</th><th>Conclusão</th><th>IC 95%</th></tr></thead><tbody>{chartData.map(item => { const aggregate = detail.results!.aggregates[item.key]; return <tr key={item.key}><td>{item.name}</td><td>{number(item.tempo)} s</td><td>{number(item.conclusao)}%</td><td>{aggregate.confidence_interval_95 ? `${number(aggregate.confidence_interval_95.lower)}–${number(aggregate.confidence_interval_95.upper)} s` : 'requer ≥2 repetições'}</td></tr>; })}</tbody></table></div>
          <div className="experiment-runs">{detail.results.runs.map(run => <div key={run.id}><strong>{run.variant_label} · repetição {run.repetition}</strong><span>{run.summary.completed}/{run.summary.vehicles} concluídas · média {number(run.summary.mean_travel_s)} s · espera {number(run.summary.mean_waiting_s)} s</span>
            {detail.config.kind === 'new_road' && <span>Carros com rota pela nova via: {run.summary.fictional_road_vehicles || 0}</span>}
            <details><summary>Distribuição de rotas</summary>{(run.summary.route_distribution || []).map((item, index) => <small key={index}>{item.vehicles} veículo(s) · {item.route.length} trechos · {item.route[0]} → {item.route[item.route.length - 1]}</small>)}</details>
            <button onClick={() => watch(run.id)}>Ver replay real</button></div>)}</div>
          <div className="export-buttons"><a href={`/api/experiments/${selectedId}/export/csv?dataset=summary`} download><Download size={15} /> CSV resumo</a><a href={`/api/experiments/${selectedId}/export/csv?dataset=vehicles`} download>CSV veículos</a><a href={`/api/experiments/${selectedId}/export/csv?dataset=roads`} download>CSV vias</a><a href={`/api/experiments/${selectedId}/export/json`} download>JSON</a><a href={`/api/experiments/${selectedId}/export/pdf`} download>PDF</a><button onClick={repeat}><RotateCcw size={15} /> Repetir idêntico</button></div>
          <p className="experiment-limits">{detail.results.interpretation} Limites: {detail.config.limitations.join('; ')}.</p></>}
      </> : <p>Selecione ou execute um experimento para ver resultados derivados do SUMO.</p>}</div></div>
    {replayRun && <div className="replay-card"><div className="experiment-detail-header"><h3>Replay · {replayRun}</h3><button onClick={() => { setReplayRun(''); setReplayPlaying(false); }}>Fechar</button></div><ReplayMap roads={replayRoads} frame={replayFrames[replayIndex] || null} theme={theme} /><div className="replay-controls"><button onClick={() => setReplayPlaying(!replayPlaying)}>{replayPlaying ? 'Pausar' : 'Reproduzir'}</button><input type="range" min="0" max={Math.max(0, replayFrames.length - 1)} value={replayIndex} onChange={event => { setReplayIndex(Number(event.target.value)); setReplayPlaying(false); }} /><select value={replaySpeed} onChange={event => setReplaySpeed(Number(event.target.value))}>{[1, 5, 20].map(value => <option key={value} value={value}>{value}×</option>)}</select></div><div className="replay-stats">Tempo {duration(replayFrames[replayIndex]?.time || 0)} · {replayFrames[replayIndex]?.active || 0} ativos · {replayFrames[replayIndex]?.completed || 0} concluídos · velocidade média {number((replayFrames[replayIndex]?.mean_speed || 0) * 3.6)} km/h</div><small>Quadros e posições gravados da execução física, sem reconstrução artificial.</small></div>}
    <div className="compare-panel"><div className="experiment-heading"><div><div className="eyebrow">COMPARADOR A/B</div><h2>Compare duas execuções</h2></div><BarChart3 size={28} /></div><div className="compare-choices"><select value={compareA} onChange={event => setCompareA(event.target.value)}><option value="">Cenário A</option>{allRuns.map(item => <option key={`${item.jobId}|${item.run.id}`} value={`${item.jobId}|${item.run.id}`}>{item.jobId} · {item.run.variant_label} · r{item.run.repetition}</option>)}</select><select value={compareB} onChange={event => setCompareB(event.target.value)}><option value="">Cenário B</option>{allRuns.map(item => <option key={`${item.jobId}|${item.run.id}`} value={`${item.jobId}|${item.run.id}`}>{item.jobId} · {item.run.variant_label} · r{item.run.repetition}</option>)}</select><button className="primary-button" disabled={!compareA || !compareB} onClick={doCompare}>Comparar</button></div>
      {comparison && <><p className="experiment-note">{comparison.comparison.directly_comparable ? 'Mesma demanda e semente; uma variável alterada.' : 'Condições não diretamente comparáveis; confira as diferenças.'} Variáveis alteradas: {comparison.comparison.changed_parameters.join(', ') || 'nenhuma'}.</p><div className="table-wrap"><table><thead><tr><th>Indicador</th><th>A</th><th>B</th><th>Diferença</th><th>%</th></tr></thead><tbody>{Object.entries(comparison.comparison.metrics).map(([key, value]) => <tr key={key}><td>{metricNames[key] || key}</td><td>{number(value.a)}</td><td>{number(value.b)}</td><td>{number(value.difference)}</td><td>{number(value.percent)}%</td></tr>)}</tbody></table></div>
        {comparison.comparison.road_impacts?.length > 0 && <><h3>Vias afetadas, inclusive transversais</h3><div className="table-wrap"><table><thead><tr><th>Via</th><th>Fila A</th><th>Fila B</th><th>Δ fila</th><th>Carros A/B</th></tr></thead><tbody>{comparison.comparison.road_impacts.map(item => <tr key={item.id}><td title={item.id}>{item.name}</td><td>{number(item.queue_a)}</td><td>{number(item.queue_b)}</td><td>{number(item.queue_difference)}</td><td>{number(item.vehicles_a)}/{number(item.vehicles_b)}</td></tr>)}</tbody></table></div></>}
        <p className="experiment-limits">{comparison.comparison.interpretation}</p></>}</div>
  </section>;
}
