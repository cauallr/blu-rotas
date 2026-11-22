# Texto do banner da Jornada Científica

Modelo visual institucional preservado no [Canva](https://www.canva.com/design/DAHa0piAr28/jO1g7-2oiAIPffMpLHOIzg/edit). Página única, 900 × 1200 mm. Este arquivo registra o texto editado em 22/11/2026 para facilitar revisão sem reconstruir o design.

## Título e autores

BLU-ROTAS — EFEITO DA RECOMENDAÇÃO COLETIVA DE ROTAS

Brayan Duwe, Cauã Leão, Wisler Clervil e Taissa Katrine

## Introdução

Aplicativos de navegação sugerem rotas de menor tempo. Se muitos seguem a mesma indicação, o trânsito pode mudar. Objetivo: aplicar algoritmos de navegação e estudar grafos para avaliar, em simulação do centro de Blumenau, o efeito da distribuição de rotas no tempo médio coletivo.

## Material e métodos

Estudo experimental com recorte OSM do centro de Blumenau convertido em grafo dirigido (1.389 trechos; 1.708 conversões). Dijkstra calcula rotas; SUMO 1.28 registra cada viagem. Mantivemos origem, destino e partidas iguais. Na Beira-Rio, simulamos 180 carros em 240 s, com 0%, 25%, 50%, 75% ou 100% no desvio e três sementes pareadas. Analisamos o tempo médio da partida planejada à chegada.

## Resultados

Beira-Rio (180 carros): média de 326,90 s com 0% no desvio; 229,29 s com 50% (−29,9%); 389,82 s com 100% (+19,2%). O excesso criou outro gargalo. Na Av. Brasil, dividir 50% elevou a média de 443,62 para 524,00 s.

**Gráfico mantido:** Figura 1 – Tempo médio por percentual de desvio na Beira-Rio (180 carros). Fonte: simulações BLU-ROTAS / SUMO 1.28 (2026).

**Destaques mantidos:** 50% no desvio: −29,9% no tempo médio. 100% no desvio: +19,2% no tempo médio.

## Limitações e próximos testes

Limitações: demanda sintética, três sementes e ausência de calibração com fluxos observados. Em teste complementar, o grafo preferiu o desvio nas três decisões, mas o carro chegou depois em duas. Próximo passo: repetir os cenários e validar fluxo e semáforos com dados reais.

## Conclusão

Os resultados confirmam que recomendar o mesmo desvio a todos pode piorar o tempo médio coletivo. A hipótese de que distribuir parte ajuda foi confirmada na Beira-Rio, mas refutada na Av. Brasil. Portanto, a estratégia depende da via e da demanda; não há percentual universal.

## Fontes de conferência

- [Proporções de desvio e intervalos](descobertas-para-apresentacao.md)
- [Teste da decisão no cruzamento](perguntas-gps-e-grafos.md)
- [Estudo por demanda e corredor](relatorio-estudo-rotas.md)
