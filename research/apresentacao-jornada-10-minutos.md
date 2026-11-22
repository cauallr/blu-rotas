# BLU-ROTAS — apresentação falada para a Jornada Científica

**Tema 2:** Efeito dominó: quando o GPS de todos escolhe o melhor caminho

**Formato:** quatro integrantes, um banner obrigatório, aproximadamente dez minutos.
**Ideia central:** a recomendação muda o trânsito que ela própria tenta prever.

O banner no Canva mantém o modelo visual da instituição. Ensaiem com ele impresso ou projetado; ninguém precisa ler as caixas literalmente.

## 1. Introdução — integrante 1 — 0:00 a 2:00

**Apontar:** título e INTRODUÇÃO, na coluna esquerda.

> Boa noite. Somos Brayan, Cauã, Wisler e Taissa. Apresentamos o BLU-ROTAS, desenvolvido para o tema **“Efeito dominó: quando o GPS de todos escolhe o melhor caminho”**.
>
> Aplicativos de navegação recomendam a cada motorista o trajeto de menor tempo estimado. Porém, a recomendação também desloca veículos e pode alterar o tempo das ruas. Quando muitos recebem a mesma indicação, uma escolha vantajosa para uma pessoa pode não ser vantajosa para o conjunto. Daí surge nossa pergunta de pesquisa: **recomendar a mesma rota a todos pode piorar o trânsito coletivo?**
>
> Nosso **objetivo geral** foi avaliar, por simulação computacional em um recorte do centro de Blumenau, como diferentes formas de distribuir veículos entre a via principal e rotas alternativas afetam o tempo médio de viagem. Também investigamos uma decisão individual: quando o algoritmo prefere um desvio, ele resulta em chegada mais rápida?
>
> A hipótese foi que distribuir **parte** do fluxo poderia reduzir o congestionamento quando a via principal estivesse carregada, enquanto enviar todos ao mesmo desvio poderia criar outro gargalo. Para testar isso, comparamos estratégias em diferentes níveis de demanda, mantendo as demais condições equivalentes. Nosso estudo usa demanda simulada: os números não são medições das ruas de Blumenau.
>
> Agora vamos apresentar os materiais, a coleta dos dados e o papel dos grafos no experimento.

## 2. Material e métodos — integrante 2 — 2:00 a 4:30

**Apontar:** MATERIAL E MÉTODOS e o gráfico ao lado. Percorrer com o dedo a sequência **mapa → grafo → rota → trânsito**.

> O mapa visível no jogo foi construído a partir de dados do OpenStreetMap. Para o algoritmo, ele se torna um **grafo dirigido**: nesta implementação, os 1.389 vértices representam trechos por onde os carros podem dirigir, e 1.708 ligações representam conversões permitidas. A direção importa: uma rota não pode atravessar uma conversão proibida ou seguir uma rua na contramão.
>
> Cada ligação recebe um custo de tempo. Dijkstra busca o caminho de menor custo estimado naquele instante. Para avaliar o que acontece **depois** da escolha, usamos o SUMO 1.28, que simula movimento, semáforos, filas e chegadas. Coletamos seus registros nativos de viagem, com horário de partida, chegada, duração e espera. Os resultados vêm desses registros, não da aparência da animação.
>
> Fizemos comparações em dois corredores, com demanda baixa, média e alta: 30, 90 e 180 veículos programados em quatro minutos. Mantivemos as mesmas origens, destinos, partidas, rede e sementes aleatórias quando mudávamos a estratégia. O estudo principal teve 72 execuções físicas e 7.200 viagens concluídas. No teste que aparece neste gráfico, focamos na Beira-Rio: com 180 carros, enviamos 0%, 25%, 50%, 75% ou 100% ao desvio, repetindo cada condição com três sementes.
>
> Calculamos, para cada condição, a média do tempo entre **partida planejada e chegada**. Incluímos a espera para entrar na rede, que também afeta o motorista. Comparamos as médias entre estratégias e observamos o comportamento da fila. A **Figura 1** apresenta os cinco percentuais testados na Beira-Rio.
>
> Testamos ainda uma decisão individual no cruzamento. Mantivemos todos os carros em estados idênticos até aquele instante e mudamos só a rota de um. Verificamos que ele realmente percorreu o desvio.

## 3. Resultados — integrante 3 — 4:30 a 7:30

**Apontar:** RESULTADOS, depois o ponto mais baixo do gráfico e, por último, o ponto de 100%. Dar uma pausa após cada comparação.

> A **Figura 1** apresenta o tempo médio de viagem conforme o percentual de carros enviados ao desvio da Beira-Rio. Com 180 veículos, a média foi **326,90 segundos** quando todos ficaram na principal. Ao enviar metade para a alternativa, caiu para **229,29 segundos**: **97,60 segundos a menos por viagem**, redução de **29,9%** neste cenário.
>
> Poderíamos parar aqui e recomendar: “mandem todos para o desvio”. Nós testamos isso. Com 100% desviados, a média subiu para **389,82 segundos**: **19,2% pior** do que manter todos na principal. A espera média para conseguir entrar na rede passou de **18,20** para **74,43 segundos**. A fila não desapareceu. O gargalo migrou. Entre os cinco percentuais que testamos, **50% foi o melhor**, mas isso não significa que 50% seja um número mágico para toda rua.
>
> Para conferir, olhamos a Avenida Brasil com a mesma demanda alta. Ali, dividir metade dos carros **piorou** o tempo médio, de **443,62** para **524,00 segundos**. Ou seja: até a regra que ajudou a Beira-Rio falhou em outro corredor. A resposta depende da geometria, da capacidade, dos semáforos e de quantos outros carros escolhem cada rota.
>
> Fizemos também a pergunta que um motorista faria ao volante: **“o GPS sugeriu sair da avenida; vale a pena?”** Em três testes pareados na Beira-Rio, o grafo preferiu o desvio nas três vezes. Na simulação física, desviar economizou **49,5 segundos** uma vez, mas causou atrasos de **21** e **15,75 segundos** nas outras duas. Essa pequena amostra não demonstra que desviar geralmente é ruim. Ela mostra uma falha possível da previsão: a rota mais barata no momento da escolha pode não ser a mais rápida até a chegada.
>
> Então há dois efeitos dominó: muitos carros podem saturar uma alternativa; e o trânsito futuro pode inverter uma recomendação individual. Meu colega fecha explicando o que esses resultados respondem e o que ainda não respondem.

## 4. Conclusão — integrante 4 — 7:30 a 10:00

**Apontar:** CONCLUSÃO, depois LIMITAÇÕES E PRÓXIMOS TESTES. Encerrar olhando para o público, sem ler o banner.

> Retomando o objetivo do trabalho: **a distribuição de rotas altera o tempo médio coletivo?** Sim, nos cenários simulados. Confirmamos também que enviar todos ao mesmo desvio **pode piorar** a média: isso ocorreu na Beira-Rio. A hipótese de que dividir parte do fluxo ajuda foi sustentada nesse corredor, mas **não** na Avenida Brasil, onde dividir pela metade aumentou o tempo médio.
>
> O que aprendemos sobre grafos é que o peso de uma rota não é uma propriedade fixa do mapa. Quando outros motoristas escolhem aquela rota, a fila muda e o peso muda junto. O algoritmo influencia o sistema que ele está tentando otimizar. A pergunta deixa de ser apenas **“qual é o menor caminho para mim?”** e passa a ser **“como a escolha oferecida a muitos carros altera a rede inteira?”**
>
> No teste individual, aplicamos as rotas fisicamente no cruzamento. Não afirmamos que um aplicativo comercial ou o GPS automático do jogo errou. O modelo usa velocidades observadas agora, mas não conhece com precisão as filas e fases semafóricas futuras.
>
> Estes resultados não medem o trânsito real da cidade. Usamos demanda sintética, poucos pares origem e destino e três sementes por condição. Antes de sugerir uma medida à Prefeitura, precisaríamos calibrar o modelo com dados observados. Nosso próximo estudo é testar **quando** um desvio deixa de valer a pena e se o ganho de um motorista atrasa outros.
>
> O BLU-ROTAS nos permite mostrar a decisão no mapa, calcular a rota no grafo e medir sua consequência no simulador. Nossa principal resposta é esta: **a melhor rota de cada um pode deixar de ser a melhor decisão para todos quando todos a escolhem.**

## Ensaio e conferência

- A fala foi dividida para cerca de **2:00 + 2:30 + 3:00 + 2:30**, incluindo pausas para apontar. Ensaiem com cronômetro; reduzam exemplos, não os limites científicos, se passarem de dez minutos.
- **Não digam “50% é ótimo para Blumenau”.** Foi o menor tempo entre cinco percentuais deste cenário sintético na Beira-Rio.
- **Não digam “o GPS automático desviou e errou”.** O experimento individual aplicou uma escolha de rota verificável no cruzamento.
- A Figura 1 mostra duas curvas. Os números citados na fala são da curva **da partida planejada à chegada**, que inclui a espera para entrar; a outra mede apenas o tempo na rede.
- Dados e protocolos: [estudo de proporções](descobertas-para-apresentacao.md), [decisão individual](perguntas-gps-e-grafos.md) e [CSV do gráfico](estudo-proporcoes-castelo/proporcoes.csv).
