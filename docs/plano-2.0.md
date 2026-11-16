# Plano incremental — BLU-ROTAS 2.0

## Inventário antes das mudanças

- **Interface:** React 19, TypeScript, Vite, MapLibre GL e Recharts. `CityMap.tsx` usa camadas GeoJSON, não um componente por carro.
- **Motor:** FastAPI com WebSocket e SUMO 1.28 via TraCI. Passos físicos de 0,25 segundo; coordenadas, sinais, posições e velocidades vêm do SUMO.
- **Roteamento:** `Graph` próprio, dirigido. Cada vértice atual é uma aresta viária dirigível do SUMO (um trecho), e cada arco representa uma conexão entre trechos. Dijkstra usa custos em segundos.
- **Persistência:** SQLite guarda viagens concluídas, amostras a cada cinco segundos, intervenções e configurações de cenários. O replay existente reexecuta um cenário desde o início; ainda não guarda quadros visuais.
- **Dados:** recorte OSM central de Blumenau, `blumenau.net.xml` e GeoJSONs. A rede original deve continuar disponível.
- **Limite físico:** TraCI altera velocidades e semáforos em tempo real, mas uma nova estrada exige gerar outra rede SUMO e reiniciar a simulação. O editor deve manter alterações fictícias separadas da fonte OSM.

## Etapas

1. **Visual e navegação:** carros por nível de zoom, agrupamento, temas claro/escuro, vias por categoria, pontes, congestionamento, rotas atual/anterior, câmera de seguimento e relógio urbano.
2. **Estado e previsão:** histórico de desvios, distância restante, ETA e erro registrado na chegada. Manter a previsão identificada como estimativa do simulador.
3. **Grafo e pontos de acesso:** explorar vértices do roteador, graus, pesos e componentes. Pontos salvos sobre vias são vértices virtuais ponderados no grafo e podem servir como origem ou destino; a criação de uma junção física exige reconstruir a rede SUMO.
4. **Editor e mapas:** camada fictícia de ruas editáveis, validação de ligação e reconstrução controlada com `netconvert`; importação de OSM por arquivo para cidades/recortes, mantendo Blumenau original.
5. **Laboratório científico:** executor separado do motor visual, cenários pareados com mesma semente/viagens, indicadores, replays derivados de snapshots reais e experimentos A–F.
6. **Rigor e entrega:** métricas de não concluídos, estatísticas por cenário e bairro, manifesto de reprodutibilidade, testes de integração e documentação dos limites.

Cada etapa preserva a versão jogável, adiciona testes para comportamento físico ou persistência e é validada no navegador. A especificação completa, inclusive os itens 20–26, foi recebida. A reprodutibilidade, o comparador A/B e as exportações fazem parte das etapas 5 e 6.

## Estado após a implementação

- **Fase 1:** temas persistentes, mapa e carros adaptativos ao zoom, agrupamento distante, rotas atuais/anteriores, seguimento, relógio e ETA calculado. Validado no navegador e em build TypeScript.
- **Fase 2:** vista do grafo real, componentes, inspeção, caminhos mínimos, pontos de acesso e editor de estradas com rede SUMO reconstruída. Uma estrada de demonstração foi construída pela API; o SUMO gerou dois sentidos trafegáveis e o cenário ficou salvo separadamente.
- **Fase 3:** executor A–F/custom em processo separado, variantes pareadas quando a demanda pode ser mantida, métricas por carro/via/cenário, CSV/JSON/PDF, comparador A/B e replay de snapshots reais. Os ensaios GPS, clima, semáforos, obras, estrada e saturação foram executados com o SUMO; um resultado nulo de mudança é mantido sem ajuste artificial.
- **Fase 4:** importação OSM por arquivo, recorte por caixa, otimização visual por agrupamento e camadas MapLibre, testes e documentação. A importação e a partida do SUMO para uma cidade importada passaram no teste automatizado. O pacote inclui apenas o recorte central; cidade inteira requer arquivo externo.

Os pontos de acesso são projetados em vias e servem de origem/destino; não viram uma nova junção física isolada. Uma estrada nova usa junções realmente inseridas numa cópia do OSM. O modo rápido executa passos físicos completos sem renderizar cada frame. O projeto foi validado com 18 testes e compilação de produção; detalhes metodológicos estão em `modelo-2.0.md`.
