# Estudo experimental: recomendação coletiva de rotas

Este protocolo usa o **mesmo motor físico `Simulator`/TraCI** do jogo. O script
`scripts/collective_route_study.py` executa processos SUMO independentes, sem
renderização, e salva os dados brutos fora da pasta `data/` do jogo.

## Pergunta e hipótese

Pergunta: sugerir a rota principal a todos, mandar só um motorista para uma
alternativa ou distribuir todos entre caminhos distintos altera os tempos
individuais e coletivos?

Hipótese a testar, sem presumir o resultado: a distribuição pode reduzir o
congestionamento da rota principal em demanda elevada, mas transferir atraso
para vias locais ou para a fila de inserção.

## Desenho pareado

- **Corredor principal:** mesmo par de arestas SUMO, de `1560016695` a
  `93392451#3`, na Avenida Brasil. O caminho principal livre usa apenas essa
  avenida. A alternativa dirigível passa pelas ruas Peru, Uruguai e Chile.
- **Sensibilidade:** `--corridor castelo` testa a Avenida Presidente Castelo
  Branco, de `1151559472#0` a `284625097#1`, em arquivos separados.
- **Demanda:** 30, 90 e 180 veículos distribuídos em 240 s. Todos têm o mesmo
  par origem/destino. Os níveis menores são subconjuntos determinísticos do
  maior. Os horários de partida são idênticos em todas as estratégias da mesma
  semente. As sementes são `20261114`, `20261115` e `20261116`.
- **Estratégias:** todos na principal; só o motorista focal na alternativa;
  todos na alternativa; metade em cada rota; GPS dinâmico com todos inicialmente
  na principal, revisão a cada 15 s e economia mínima prevista de 5%.
- **Motorista focal:** índice 90 da demanda máxima. Ele aparece em todos os
  níveis, na mesma posição temporal aproximada, e usa a alternativa nas
  estratégias “um desvio” e “metade em cada rota”.
- **Controles:** mesma versão da rede, sol, nenhuma obra ou mudança semafórica,
  semente emparelhada, passo físico SUMO de 0,25 s, teletransporte desativado,
  relógio iniciado às 08:00. A observação vai até 1800 s ou termina antes quando
  todos chegam. A amostragem viária ocorre a cada 5 s.

As rotas são calculadas antes da chegada dos carros pelo grafo dirigido do
projeto. Cada viagem recebe uma rota válida por `Simulator.spawn_trip`. A
alternativa é **secundária em tempo livre**, não uma rota previamente declarada
mais eficiente. O teste determina quando ela melhora ou piora o resultado.

## Indicadores e leitura correta

- `travel_s`: duração **após a entrada física** no SUMO; média, mediana, p95 e
  máximo usam apenas viagens concluídas.
- `depart_delay_s`: espera para o SUMO conseguir inserir o carro na via.
- `door_to_door_s`: chegada menos partida planejada; inclui o atraso de entrada
  (diferenças inferiores a 0,25 s podem surgir do arredondamento do passo).
- `time_loss_s`: indicador nativo `timeLoss` do arquivo `tripinfo` do SUMO. Ele
  acumula tempo abaixo da velocidade ideal ao longo da rota percorrida. **Não**
  equivale ao tempo adicional em relação à rota mais curta de outra estratégia.
- `waiting_s`: tempo nativo parado, velocidade até 0,1 m/s.
- `queue_primary` e `queue_alternative`: soma dos veículos parados nas arestas
  exclusivas de cada opção na amostra de 5 s; os trechos compartilhados ficam
  em coluna própria de ocupação. A fila de carros aguardando inserção é medida
  separadamente.
- `roads.csv`: velocidade média observada, fila média e máxima por aresta SUMO.
  O mapa de calor colore a razão entre velocidade observada e limite da via;
  arestas sem veículos permanecem cinzas.
- `reroutes`: alterações do plano de rota do GPS; mudanças físicas exigem
  evidência de arestas percorridas, distância ou ocupação. A contagem sozinha
  não comprova que o motorista efetivamente desviou.

As viagens não concluídas continuam no denominador da taxa de conclusão. Em
comparações com censura, não se deve interpretar a média das concluídas como a
média de toda a demanda. Os intervalos de confiança usam médias de três
repetições e têm caráter exploratório.

## Reproduzir

No PowerShell, a partir da pasta do projeto:

```powershell
$env:SUMO_BINARY = 'C:\caminho\do\sumo.exe'
python scripts\collective_route_study.py
python scripts\render_collective_study.py
python scripts\validate_collective_study.py
```

Com o Python portátil desta instalação, substitua `python` pelo caminho do
executável. As execuções já concluídas com a mesma assinatura são reutilizadas;
apague somente os arquivos da execução que desejar refazer. Para a checagem de
outro corredor:

```powershell
python scripts\collective_route_study.py --corridor castelo --strategies principal todos_desvio dividido
python scripts\render_collective_study.py ..\estudo-castelo-branco
python scripts\validate_collective_study.py ..\estudo-castelo-branco
```

Cada pasta gerada contém `routes.json`, `runs/*.json`, `runs/*.tripinfo.xml`,
`summary.json`, CSV de viagens, comparações pareadas, ocupação e vias, além dos gráficos SVG. O
resumo acadêmico deve usar os valores de `summary.json`/`summary.csv` e informar
a versão da rede e do código nele registradas.

## Limites

A demanda é sintética e concentrada em um único par origem/destino. A via de
entrada pode ser o gargalo dos três caminhos. O recorte central OSM não
representa Blumenau inteira; não há calibração com contagens reais ou dados de
aplicativos comerciais. Os resultados mostram as consequências **deste modelo
e destes corredores**, sem permitir estimar o trânsito real da cidade nem
generalizar para todo motorista.

Referências metodológicas primárias: [saída TripInfo do SUMO](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html),
[valores de veículos no TraCI](https://sumo.dlr.de/docs/TraCI/Vehicle_Value_Retrieval.html),
[valores de vias no TraCI](https://sumo.dlr.de/docs/TraCI/Edge_Value_Retrieval.html).
