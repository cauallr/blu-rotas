# Texto do banner da Jornada Científica

Modelo visual institucional preservado no [Canva](https://www.canva.com/design/DAHa0piAr28/jO1g7-2oiAIPffMpLHOIzg/edit). Página única, 900 × 1200 mm. Este arquivo registra o texto editado em 22/11/2026 para facilitar revisão sem reconstruir o design.

## Título e autores

BLU-ROTAS — EFEITO DA RECOMENDAÇÃO COLETIVA DE ROTAS

Brayan Duwe, Cauã Leão, Wisler Clervil e Taissa Katrine

## Introdução

Você está atrasado e o GPS sugere um desvio. Se muitos motoristas recebem a mesma sugestão, a rua alternativa continua rápida? Investigamos quando o melhor caminho para uma pessoa deixa de ser a melhor decisão para todos.

## Material e métodos

Usamos a malha OSM do centro de Blumenau como grafo dirigido: 1.389 trechos e 1.708 conversões permitidas. Dijkstra estima a rota mais rápida; o SUMO 1.28 simula filas e semáforos. Mantivemos origem, destino, partidas e semente iguais. Testamos 30, 90 e 180 carros; na Beira-Rio, desviamos 0%, 25%, 50%, 75% ou 100%. São cenários sintéticos.

## Resultados

Beira-Rio (180 carros): tempo médio de 326,90 s sem desvio; 229,29 s com 50% (−29,9%); 389,82 s com 100% (+19,2%). Na Av. Brasil, dividir 50% elevou o tempo de 443,62 para 524,00 s. O efeito depende da rua.

**Gráfico mantido:** Figura 1. Tempo médio por proporção desviada (180 veículos; 3 sementes). Fonte: simulações BLU-ROTAS / SUMO 1.28 (2026).

**Destaques mantidos:** 50% no desvio: −29,9% no tempo médio. 100% no desvio: +19,2% no tempo médio.

## Limitações e próximos testes

Em 3 testes pareados, o grafo preferiu o desvio; em 2, o carro chegou depois. O algoritmo não prevê toda fila futura. São cenários sintéticos com 3 sementes. Para orientar Blumenau, faltam mais repetições e dados reais de fluxo e semáforos.

## Conclusão

Sim, neste modelo: mandar todos ao mesmo desvio pode piorar o tempo coletivo. Na Beira-Rio, distribuir parte ajudou; desviar todos criou outro gargalo. Na Av. Brasil, até dividir metade piorou a média. A melhor rota depende de quantos outros a escolhem: o algoritmo precisa considerar a rede inteira.

## Fontes de conferência

- [Proporções de desvio e intervalos](descobertas-para-apresentacao.md)
- [Teste da decisão no cruzamento](perguntas-gps-e-grafos.md)
- [Estudo por demanda e corredor](relatorio-estudo-rotas.md)
