# BLU-ROTAS — respostas rápidas para a banca

Use este cartão depois da apresentação. Responda primeiro em uma frase; detalhe apenas se a banca pedir. Os números abaixo vêm dos [resultados de proporção](descobertas-para-apresentacao.md), do [estudo por corredor](relatorio-estudo-rotas.md) e do [teste da decisão no cruzamento](perguntas-gps-e-grafos.md).

## 1. Qual é a contribuição de grafos e algoritmos no projeto?

**Resposta curta:** o mapa foi modelado como um grafo dirigido, e Dijkstra calcula caminhos de menor tempo estimado; o simulador testa o que acontece quando os carros seguem essas decisões.

**Se pedirem detalhes:** neste recorte há 1.389 vértices que representam trechos dirigíveis e 1.708 ligações que representam conversões permitidas. Sentidos de circulação e conversões proibidas restringem os caminhos. Os custos usam condições observadas na simulação, mas não preveem perfeitamente filas futuras.

## 2. O trabalho prova que o GPS real piora o trânsito de Blumenau?

**Resposta curta:** não. Demonstra, em cenários sintéticos controlados, que uma recomendação coletiva uniforme **pode** piorar o tempo médio.

**Se pedirem detalhes:** faltam contagens reais por via e horário, origens e destinos observados, tempos medidos e validação dos semáforos. O recorte geográfico vem de dados reais de mapa; a demanda do experimento não é uma medição da cidade.

## 3. Por que 50% foi melhor? É o percentual ideal?

**Resposta curta:** na Beira-Rio, 50% foi o melhor **entre cinco percentuais testados**, com 180 carros; não é um valor ideal universal.

**Se pedirem detalhes:** as médias da partida planejada à chegada foram 326,90 s com 0% no desvio, 229,29 s com 50% e 389,82 s com 100%. Enviar todos transferiu o gargalo. Percentuais entre os pontos testados podem produzir outros resultados.

## 4. Qual a evidência de que a regra depende da rua?

**Resposta curta:** dividir o fluxo pela metade ajudou na Beira-Rio, mas piorou o tempo médio na Avenida Brasil.

**Se pedirem detalhes:** na Avenida Brasil, com 180 veículos, a média da partida planejada à chegada passou de 443,62 s para 524,00 s com metade dos carros na alternativa. Assim, não aplicamos a política da Beira-Rio como regra para outra via.

## 5. As 7.200 viagens são 7.200 experimentos independentes?

**Resposta curta:** não. São viagens simuladas em 72 execuções; a unidade de repetição para comparar condições é a execução com uma semente.

**Se pedirem detalhes:** no estudo de proporções da Beira-Rio, cada condição foi repetida com três sementes pareadas. Carros da mesma execução interagem e não podem ser tratados como repetições independentes.

## 6. Qual é a diferença entre a rota calculada e a rota percorrida?

**Resposta curta:** o grafo produz uma previsão; a rota percorrida e o horário de chegada são fatos registrados pelo SUMO dentro da simulação.

**Se pedirem detalhes:** em um teste anterior, houve recálculos do plano de rota sem alteração das viagens físicas. No teste complementar apresentado, aplicamos a escolha no cruzamento e verificamos as arestas efetivamente percorridas. O grafo preferiu desviar em três pares na Beira-Rio; em dois o carro chegou mais tarde.

## 7. Como os dados foram coletados e analisados?

**Resposta curta:** o SUMO registrou cada viagem; calculamos tempo da partida planejada à chegada e comparamos médias entre cenários com as mesmas condições iniciais.

**Se pedirem detalhes:** mantivemos malha, origem, destino, horários de partida e semente quando mudamos a política de desvio. Também examinamos espera para inserção, tempo dentro da rede e percentil 95. A Figura 1 apresenta duas curvas; os números citados na fala são da curva que inclui a espera desde a partida planejada.

## 8. Qual seria o próximo experimento científico?

**Resposta curta:** verificar em que demanda e em que momento o desvio deixa de valer a pena, medindo também quem ganha e quem perde.

**Se pedirem detalhes:** repetir com mais sementes e origens e destinos, registrar a rota física de cada carro, variar a proporção desviada em passos menores e medir filas nas ruas alternativas. Antes de propor intervenções reais, calibrar a simulação com dados observados.

## Cuidados durante a fala

- Digam **“no cenário simulado”** ao apresentar um resultado como 29,9%.
- Digam **“50% foi o melhor entre os percentuais testados”**.
- Digam **“o grafo preferiu o desvio”**, não “o GPS real errou”.
- Não atribuam as 7.200 viagens a motoristas observados em Blumenau.
