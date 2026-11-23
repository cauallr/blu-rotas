# Texto do banner da Jornada Científica

Modelo visual institucional preservado no [Canva](https://www.canva.com/design/DAHa0piAr28/jO1g7-2oiAIPffMpLHOIzg/edit). Página única, 900 × 1200 mm. Este arquivo registra o texto editado em 22/11/2026 para facilitar revisão sem reconstruir o design.

## Título e autores

BLU-ROTAS — EFEITO DA RECOMENDAÇÃO COLETIVA DE ROTAS

Brayan Duwe, Cauã Leão, Wisler Clervil e Taissa Katrine

## Introdução

Aplicativos de navegação sugerem rotas de menor tempo. Se muitos seguem a mesma indicação, o trânsito pode mudar. Objetivo: aplicar algoritmos de navegação e estudar grafos para avaliar, em simulação do centro de Blumenau, o efeito da distribuição de rotas no tempo médio coletivo.

## Material e métodos

Mapa: recorte OSM do centro convertido em grafo dirigido (1.389 trechos; 1.708 conversões). Rota: Dijkstra estima o menor tempo. Trânsito: SUMO 1.28 simula carros, filas e semáforos e registra cada viagem. Teste: 180 carros em 240 s na Beira-Rio, com 0%, 25%, 50%, 75% ou 100% no desvio; três sementes, mesma origem, destino e partidas. Análise: tempo médio da partida planejada à chegada.

## Resultados

Todos no desvio? Beira-Rio: 326,90 s (0%) → 389,82 s (100%): piorou. Dividir ajuda? Com 50%, caiu a 229,29 s (−29,9%). Sempre? Não: na Av. Brasil, 50% elevou a média de 443,62 a 524,00 s.

**Gráfico mantido:** Figura 1 – Tempo médio por percentual de desvio na Beira-Rio (180 carros). Fonte: simulações BLU-ROTAS / SUMO 1.28 (2026).

**Destaques mantidos:** 50% no desvio: −29,9% no tempo médio. 100% no desvio: +19,2% no tempo médio.

## Limitações e próximos testes

Limitações: demanda sintética, três sementes e ausência de calibração com fluxos observados. Em teste complementar, o grafo preferiu o desvio nas três decisões, mas o carro chegou depois em duas. Próximo passo: repetir os cenários e validar fluxo e semáforos com dados reais.

## Conclusão

Os objetivos foram atendidos no modelo: grafos dirigidos e Dijkstra calcularam rotas; o SUMO mediu as viagens. Enviar todos ao mesmo desvio piorou a média; distribuir parte ajudou na Beira-Rio, mas não na Av. Brasil. A estratégia depende da rede e da demanda.

## Fontes de conferência

- [Proporções de desvio e intervalos](descobertas-para-apresentacao.md)
- [Teste da decisão no cruzamento](perguntas-gps-e-grafos.md)
- [Estudo por demanda e corredor](relatorio-estudo-rotas.md)
