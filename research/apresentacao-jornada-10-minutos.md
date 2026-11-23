# BLU-ROTAS — apresentação falada para a Jornada Científica

**Tema 2:** Efeito dominó: quando o GPS de todos escolhe o melhor caminho

**Formato:** quatro integrantes, um banner obrigatório, aproximadamente dez minutos.
**Ideia central:** a recomendação muda o trânsito que ela própria tenta prever.

O banner no Canva mantém o modelo visual da instituição. Ensaiem com ele impresso ou projetado; ninguém precisa ler as caixas literalmente.

## 1. Introdução — integrante 1 — 0:00 a 1:50

**Apontar:** título e INTRODUÇÃO, na coluna esquerda.

> Boa noite. Somos Brayan, Cauã, Wisler e Taissa. Apresentamos o BLU-ROTAS, desenvolvido para o tema **“Efeito dominó: quando o GPS de todos escolhe o melhor caminho”**.
>
> Aplicativos de navegação recomendam a cada motorista o trajeto de menor tempo estimado. Porém, a recomendação também desloca veículos e pode alterar o tempo das ruas. Quando muitos recebem a mesma indicação, uma escolha vantajosa para uma pessoa pode não ser vantajosa para o conjunto. Daí surge nossa pergunta de pesquisa: **recomendar a mesma rota a todos pode piorar o trânsito coletivo?**
>
> Nosso **objetivo geral** foi aplicar algoritmos de navegação e estudar grafos na malha do centro de Blumenau. Com esse modelo, avaliamos por simulação como diferentes distribuições entre a via principal e rotas alternativas afetam o tempo médio coletivo. Também investigamos uma decisão individual: quando o algoritmo prefere um desvio, ele resulta em chegada mais rápida?
>
> A hipótese foi que distribuir **parte** do fluxo poderia reduzir o congestionamento quando a via principal estivesse carregada, enquanto enviar todos ao mesmo desvio poderia criar outro gargalo. Para testar isso, comparamos estratégias em diferentes níveis de demanda, mantendo as demais condições equivalentes. Nosso estudo usa demanda simulada: os números não são medições das ruas de Blumenau.
>
> Agora vamos apresentar os materiais, a coleta dos dados e o papel dos grafos no experimento.

## 2. Material e métodos — integrante 2 — 1:50 a 4:45

**Apontar:** MATERIAL E MÉTODOS. Percorrer com o dedo a sequência **mapa → grafo → rota → trânsito → medida**.

> Fizemos o estudo em cinco etapas. **Primeiro, o mapa.** Importamos um recorte do OpenStreetMap do centro de Blumenau e o transformamos em um **grafo dirigido**. Nele, 1.389 vértices representam trechos dirigíveis e 1.708 ligações representam conversões permitidas. Assim, o algoritmo respeita o sentido das ruas e não atravessa uma conversão proibida.
>
> **Segundo, a rota.** O algoritmo de Dijkstra procura no grafo o caminho de menor tempo estimado. Esse custo considera as velocidades observadas na simulação. O cálculo indica qual trajeto parece melhor **naquele instante**; ele não antecipa perfeitamente as filas que surgirão depois.
>
> **Terceiro, o trânsito.** Atribuímos as rotas aos carros, e o SUMO 1.28 simula o deslocamento físico, semáforos, filas e chegadas. Comparamos dois corredores e três níveis de demanda: 30, 90 e 180 carros programados em quatro minutos. No estudo principal foram 72 execuções e 7.200 viagens concluídas.
>
> **Quarto, a comparação.** Para este gráfico, usamos 180 carros na Beira-Rio e atribuímos 0%, 25%, 50%, 75% ou 100% à alternativa. Mudamos apenas essa proporção: malha, origem, destino e horários de partida permaneceram iguais. Repetimos cada condição com três sementes aleatórias, para comparar cenários equivalentes.
>
> Na prática, geramos a mesma lista de veículos para cada comparação: cada carro tinha origem, destino e instante planejado de partida. A condição experimental determinava quais deles seguiriam a alternativa. Conferimos que todas as viagens solicitadas foram concluídas antes de calcular as médias.
>
> **Quinto, a medida.** Extraímos os registros nativos de cada viagem do SUMO. Calculamos a média entre a **partida planejada e a chegada**, incluindo a espera para entrar na rede. A Figura 1 mostra essa medida e, separadamente, o tempo apenas dentro da rede. Para a pergunta individual, repetimos o estado de todos os carros até uma bifurcação, mudamos apenas a rota de um e verificamos que ele realmente percorreu o desvio.

## 3. Resultados — integrante 3 — 4:45 a 7:45

**Apontar:** RESULTADOS e a Figura 1. Indicar 0%, 50% e 100% no gráfico; depois apontar para LIMITAÇÕES E PRÓXIMOS TESTES ao falar da decisão individual.

> Na Figura 1, a linha da partida planejada à chegada inclui a espera para entrar na rede; é ela que usamos nas comparações a seguir. A outra linha mede apenas o tempo após a entrada.
>
> **Primeira pergunta: mandar todos ao mesmo desvio pode piorar o trânsito?** Sim, neste cenário. Na Beira-Rio, com 180 carros, deixar todos na principal produziu média de **326,90 segundos**. Enviar todos à alternativa elevou a média para **389,82 segundos**, ou **19,2% a mais**. A espera média para conseguir entrar na rede também subiu de **18,20** para **74,43 segundos**. O desvio ficou sobrecarregado: o gargalo mudou de lugar.
>
> **Segunda pergunta: distribuir parte dos carros ajuda?** Na mesma Beira-Rio, sim. Com metade no desvio, a média caiu para **229,29 segundos**. São **97,60 segundos a menos por viagem**, ou **29,9%** abaixo de deixar todos na principal. A Figura 1 mostra que 50% foi o menor resultado **entre cinco percentuais testados**. Não sabemos se algum percentual intermediário seria ainda melhor.
>
> Mas **dividir sempre ajuda?** Não. Na Avenida Brasil, também com 180 carros, a divisão pela metade aumentou a média de **443,62** para **524,00 segundos**. A política que melhorou um corredor piorou outro. Isso mostra por que uma regra única, como “desvie metade”, não resolve toda a rede.
>
> **Terceira pergunta: se o algoritmo sugere desviar no meio da viagem, devo seguir?** A resposta variou. Em três pares de testes na Beira-Rio, o grafo preferiu o desvio. O carro que desviou economizou **49,5 segundos** uma vez, mas chegou **21** e **15,75 segundos depois** nas outras duas. Como são apenas três pares, não podemos dizer que desviar costuma ser ruim. Podemos dizer que o melhor custo calculado no cruzamento nem sempre produziu a chegada mais rápida.
>
> Os três resultados respondem ao tema sem um número mágico: a decisão depende de quantos carros vão pela mesma rua, do corredor e do trânsito que surge depois da escolha.

## 4. Conclusão — integrante 4 — 7:45 a 10:00

**Apontar:** CONCLUSÃO, depois LIMITAÇÕES E PRÓXIMOS TESTES. Encerrar olhando para o público, sem ler o banner.

> Retomando nossos **dois objetivos**, aplicamos grafos dirigidos e Dijkstra para calcular caminhos possíveis e seus tempos estimados. Depois, usamos o SUMO para observar as consequências dessas escolhas. Assim, conseguimos estudar os algoritmos de navegação e responder à pergunta sobre o trânsito coletivo dentro do modelo.
>
> **A recomendação igual para todos pode piorar o trânsito?** Sim, nos cenários simulados: na Beira-Rio, todos no desvio ficaram mais lentos que todos na principal. A hipótese de que dividir parte do fluxo ajuda foi sustentada nesse corredor, mas não na Avenida Brasil. Portanto, a distribuição precisa considerar a rede e a demanda; 50% não é um percentual universal.
>
> O estudo de grafos também revelou uma limitação do cálculo: o custo de uma rota pode mudar quando outros motoristas a escolhem. O algoritmo usa condições observadas no presente, mas não prevê perfeitamente todas as filas e fases semafóricas futuras. No teste individual, aplicamos as rotas fisicamente; não atribuímos o resultado ao GPS automático do jogo ou a um aplicativo comercial.
>
> Esses dados ainda não descrevem o trânsito real de Blumenau. A demanda foi sintética e houve apenas três sementes por condição. Antes de sugerir uma intervenção à Prefeitura, precisaríamos calibrar o simulador com fluxos e semáforos observados. O próximo experimento pode investigar quando um desvio deixa de compensar e se o ganho de um motorista prejudica os demais.
>
> O BLU-ROTAS une o conteúdo de grafos da disciplina a uma pergunta que qualquer motorista entende: **a melhor rota de cada um pode deixar de ser a melhor decisão para todos quando todos a escolhem.**

## Ensaio e conferência

- A fala foi dividida para cerca de **1:50 + 2:55 + 3:00 + 2:15**, incluindo pausas para apontar. Ensaiem com cronômetro; reduzam exemplos, não os limites científicos, se passarem de dez minutos.
- **Não digam “50% é ótimo para Blumenau”.** Foi o menor tempo entre cinco percentuais deste cenário sintético na Beira-Rio.
- **Não digam “o GPS automático desviou e errou”.** O experimento individual aplicou uma escolha de rota verificável no cruzamento.
- A Figura 1 mostra duas curvas. Os números citados na fala são da curva **da partida planejada à chegada**, que inclui a espera para entrar; a outra mede apenas o tempo na rede.
- Dados e protocolos: [estudo de proporções](descobertas-para-apresentacao.md), [decisão individual](perguntas-gps-e-grafos.md) e [CSV do gráfico](estudo-proporcoes-castelo/proporcoes.csv).
