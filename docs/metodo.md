# Método da simulação

## Rede e tráfego

O arquivo OSM foi baixado da API do OpenStreetMap em 11/11/2026. `netconvert` 1.28.0 gerou a rede dirigida com conexões, junções e semáforos inferidos. O roteador lê as conexões de faixas que permitem `passenger`, incluindo a permissão da faixa interna de cada cruzamento. O SUMO calcula aceleração, seguimento, mudança de faixa, semáforos e chegada.

Cada veículo é um agente com par origem/destino, horário, estratégia de GPS, rota, distância, espera e alterações de rota. A geração usa uma semente explícita. O controlador consulta o estado do SUMO a cada segundo simulado. A velocidade 5× executa cinco passos do SUMO por segundo real; nunca multiplica coordenadas ou velocidade física no navegador.

O custo inicial da aresta é `comprimento / velocidade_permitida`. O GPS dinâmico substitui esse custo pelo maior entre o custo livre e `comprimento / velocidade_média_observada` quando há veículos na via. A cada intervalo, Dijkstra busca um caminho desde a aresta atual. O novo caminho só é aplicado se reduzir o custo previsto pelo limiar configurado. Uma interdição força a busca para veículos cuja rota futura usa a via fechada. A chamada `traci.vehicle.setRoute` valida que a nova rota começa na aresta atual.

## Intervenções

Interdição usa `traci.lane.setDisallowed(..., ['passenger'])`. Redução de velocidade usa `traci.edge.setMaxSpeed`. A restauração recupera as permissões originais das faixas. Uma via sem desvio possível permanece um caso de tráfego retido, não recebe teleporte artificial. O modelo foi iniciado com `--time-to-teleport -1` para não apagar congestionamentos por teleporte.

As fases semafóricas mantêm os estados originais de todos os sinais. Só `duration` muda, via `traci.trafficlight.setProgramLogic`; assim, o usuário não define simultaneamente verdes conflitantes. Os parâmetros climáticos são aproximações documentadas no código (`WEATHER`), aplicadas por `setSpeedFactor`, `setAccel`, `setDecel` e `setTau`.

## Métricas

`samples` recebe observações a cada cinco segundos simulados. `trips` recebe uma linha somente após a chegada do veículo. `interventions` registra instante, alvo, parâmetros e quantidade de rotas que incluíam a via no momento da mudança. As médias usam os veículos ativos ou as viagens efetivamente concluídas conforme o indicador. Os tempos de algoritmo usam `perf_counter` no controlador; benchmarks de grafos usam `perf_counter_ns` e, por isso, variam entre máquinas e execuções.

O replay de cenário conserva os pares OD, a ordem/tempo de partida, semente, proporção de GPS, clima, obras e alterações de duração do semáforo. Não conserva um estado intermediário do SUMO; a reexecução começa do segundo zero.

## Complexidades

| Operação | Lista de adjacência | Matriz |
| --- | --- | --- |
| Memória | O(V + E) | O(V²) |
| BFS / DFS | O(V + E) | O(V²) se percorrer linha da matriz |
| Dijkstra, fila simples | O(V² + E) | O(V²) |
| Dijkstra, heap binário | O((V + E) log V) | Não usado |
| Prim, heap | O(E log V) | Não usado |

As medições de 10, 20, 50 e 100 cidades comparam o mesmo grafo e o mesmo par origem/destino nas versões de Dijkstra com heap, fila simples e matriz. Os tempos não são resultados científicos universais; o sistema os mede em execução.

## Fontes técnicas

- [Importação OSM no SUMO](https://sumo.dlr.de/docs/Networks/Import/OpenStreetMap.html)
- [TraCI Python](https://sumo.dlr.de/docs/TraCI/Interfacing_TraCI_from_Python.html)
- [Mudança de rota de veículos](https://sumo.dlr.de/docs/TraCI/Change_Vehicle_State.html)
- [Controle de semáforos](https://sumo.dlr.de/docs/Simulation/Traffic_Lights.html)
- [OpenStreetMap copyright](https://www.openstreetmap.org/copyright)
