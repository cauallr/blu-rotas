import { ArrowRight, CircleHelp, Download, FlaskConical, MapPinned, Route } from 'lucide-react';
import ExperimentLab from './ExperimentLab';
import HelpTip from './HelpTip';
import type { Snapshot } from './types';

export default function SimulationsPage({ snapshot, theme, openCity, openData }: {
  snapshot: Snapshot | null; theme: 'dark' | 'light'; openCity: () => void; openData: () => void;
}) {
  return <main className="content-page simulations-page">
    <div className="page-heading"><div><div className="eyebrow">LABORATÓRIO DE TRÂNSITO</div><h1>Simulações</h1>
      <p>Crie situações, execute o mesmo trânsito sob regras diferentes e compare os resultados calculados pelo SUMO.</p></div><FlaskConical size={42} /></div>
    <div className="simulation-intro">
      <div><span className="step-number">01</span><h3>Monte o cenário</h3><p>Na Cidade, escolha ruas, semáforos, clima, carros e GPS. Salve a rede modificada antes de testar uma estrada nova.</p><button onClick={openCity}><MapPinned size={15} /> Abrir cidade <ArrowRight size={14} /></button></div>
      <div><span className="step-number">02</span><h3>Escolha uma pergunta</h3><p>Use os estudos prontos A–F ou variantes próprias. Fixe a semente, a demanda e a janela de partida para comparar estratégias.</p><HelpTip title="O que é um experimento pareado?">Use os mesmos veículos, partidas, destinos e semente em A e B. Assim, a diferença principal é a regra alterada. Faça mais de uma repetição para medir a variabilidade.</HelpTip></div>
      <div><span className="step-number">03</span><h3>Observe e exporte</h3><p>Veja viagens concluídas e não concluídas, tempo médio, P95, espera, filas e replay. Exporte CSV, JSON ou PDF para a apresentação.</p><button onClick={openData}><Download size={15} /> Ver dados da cidade <ArrowRight size={14} /></button></div>
    </div>
    <div className="simulation-guide"><Route size={20} /><div><strong>Primeira experiência sugerida</strong><p>Teste GPS estático contra dinâmico com 25 carros, 3 repetições e semente 42. Depois aumente a demanda sem mudar os outros parâmetros. Os resultados podem favorecer qualquer estratégia.</p></div>
      <a href="/tutorial_de_situações.html" target="_blank" rel="noreferrer"><CircleHelp size={16} /> Tutorial completo</a></div>
    <ExperimentLab snapshot={snapshot} theme={theme} />
  </main>;
}
