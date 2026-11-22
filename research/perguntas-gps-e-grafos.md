# BLU-ROTAS — quando confiar no desvio do GPS?

## A pergunta que aproxima o grafo das pessoas

> Chego a uma bifurcação com trânsito à frente. Sigo o desvio oferecido pelo
> GPS ou permaneço na via principal?

O experimento separa **a previsão do algoritmo** da **chegada efetiva do
motorista**. No grafo dirigido do projeto, 1.389 vértices representam trechos
dirigíveis e 1.708 ligações representam conversões permitidas. Dijkstra escolhe
o menor custo, e o custo dinâmico usa a velocidade que os carros apresentam
naquele instante. Depois o SUMO simula aceleração, filas, semáforos, conversões
e os demais veículos. Uma preferência do grafo é uma previsão, não o resultado.

## Experimento novo: decisão durante a viagem

Foram executadas **12 simulações físicas SUMO 1.28**, em seis pares, com 180
carros programados em 240 segundos em cada execução (2.160 viagens concluídas).
Para cada corredor e uma das três sementes `20261114`, `20261115` e `20261116`,
o carro focal e os 179 demais começam na via principal. As duas execuções de
cada par são idênticas até o carro focal entrar numa aresta compartilhada antes
da bifurcação. Numa ele mantém a rota; na outra recebe a alternativa naquele
instante. Os estados de todos os veículos antes da decisão foram comparados
por hash e são iguais em cada par. O script também verificou que o carro
**percorreu fisicamente** arestas exclusivas do caminho escolhido.

Sol, malha original, sem obras, mesmo programa semafórico, passo físico de
0,25 s, sem teleporte. O tempo abaixo é da **decisão até a chegada**, de modo
que espera anterior para entrar na rede é comum aos dois cenários e não mascara
a escolha do motorista.

| Corredor | Semente | Carros parados na principal à frente | Previsão do grafo | Ficar na principal | Tomar o desvio | Efeito do desvio |
|---|---:|---:|---|---:|---:|---:|
| Av. Brasil | 14 | 0 | principal | 84,25 s | 74,50 s | **−9,75 s** |
| Av. Brasil | 15 | 0 | principal | 84,00 s | 74,50 s | **−9,50 s** |
| Av. Brasil | 16 | 0 | principal | 86,25 s | 74,50 s | **−11,75 s** |
| Beira-Rio / Av. Presidente Castelo Branco | 14 | 4 | desvio | 158,00 s | 108,50 s | **−49,50 s** |
| Beira-Rio / Av. Presidente Castelo Branco | 15 | 2 | desvio | 88,00 s | 109,00 s | **+21,00 s** |
| Beira-Rio / Av. Presidente Castelo Branco | 16 | 1 | desvio | 96,00 s | 111,75 s | **+15,75 s** |

Valores negativos significam chegada mais rápida com desvio. A coluna de fila
conta somente as arestas exclusivas da principal no instante da decisão; ela
não representa toda a fila de entrada ou todos os atrasos futuros. Na Av. Brasil,
o desvio foi fisicamente melhor nos três pares, apesar de ser mais longo e de
o custo instantâneo do grafo favorecer a principal nas três ocasiões. O ganho
individual médio foi **10,33 s**; o intervalo pareado t de 95% com apenas três
sementes foi de 7,27 a 13,40 s de ganho, descritivo e exploratório.

Na Beira-Rio, o grafo preferiu a alternativa nas três ocasiões, mas ela ajudou
uma vez e atrasou duas. A diferença média foi de −4,25 s, com intervalo
exploratório muito amplo (−101,82 a +93,32 s). Portanto, **não há evidência
estável de benefício médio para o motorista nesse ponto de decisão** com estas
três sementes. A média isolada esconderia a reversão entre repetições.

Os custos do grafo não preveem explicitamente a fase futura dos semáforos nem
o trânsito que se formará enquanto o veículo ainda se desloca. Esses mecanismos
podem contribuir para as inversões; o experimento ainda não os isolou como
causa. Ele testa uma mudança de rota aplicada na bifurcação. O GPS dinâmico
automático do jogo não foi responsável por estas mudanças. Em um estudo anterior,
465 de 900 carros tiveram mudanças de **plano**, sem diferenças físicas nas
viagens: contar recálculos não demonstra que o motorista desviou.

## Rota secundária: economiza tempo no centro?

**Às vezes, neste modelo.** No teste individual acima, economizou na Av.
Brasil; na Beira-Rio dependeu da semente. Para o grupo, o resultado também
depende do corredor e da proporção enviada ao desvio. Com 180 carros na
Beira-Rio e três sementes, a média porta a porta foi 326,90 s com 0% no
desvio, 229,29 s com 50% e 389,82 s com 100%. O valor de 50% foi o menor
**entre os cinco percentuais testados**, e não um ótimo universal. Na Av.
Brasil, dividir metade dos carros piorou o tempo médio na rede de 127,81 para
140,81 s. Uma rota favorável a um indivíduo pode ser desfavorável ao conjunto.

## Ruas citadas e decisões públicas

A rede fornecida inclui trechos dirigíveis da Rua Itajaí (52 arestas
direcionadas), Rua 7 de Setembro (87), Rua XV de Novembro (37) e Avenida
Presidente Castelo Branco (25). A Prefeitura identifica esta última como
**Beira-Rio**. Os totais de arestas contam segmentos e sentidos, não ruas
físicas distintas. O estudo de distribuição já testa a Beira-Rio e usa a XV
de Novembro como parte da alternativa.

Dentro **deste cenário sintético**, a opção municipal mais defensável para
testar é orientar parte do fluxo antes da bifurcação e monitorar a XV de
Novembro, sem encaminhar todos os veículos ao mesmo desvio. Os dados não
identificam ainda qual alteração de semáforo, faixa ou sentido melhoraria
a Rua Itajaí ou a 7 de Setembro. Ambas estão mapeadas, mas não houve estudo
pareado com demanda calibrada nelas. Um teste responsável compararia a
situação atual com fases semafóricas alternativas válidas, distribuição de
rotas e mudanças de capacidade, sempre medindo também as ruas transversais,
tempo médio, P95 e viagens não concluídas.

**Nada aqui estima o trânsito real no horário de pico de Blumenau.** As viagens
partem de um único par origem/destino por corredor, a demanda é sintética e
há somente três sementes. Para propor uma medida real à Prefeitura, faltam
contagens de veículos por rua e horário, origens e destinos observados,
tempos medidos de viagem e validação dos programas semafóricos.

## Perguntas para escolher a próxima investigação

1. **O GPS ainda deve recomendar o desvio quando a fila já está visível?**
   Variar o instante da decisão e comparar previsão com chegada física.
2. **Uma rota que salva dez segundos para mim tira tempo dos outros?**
   Comparar o carro focal e todos os demais no mesmo par de cenários.
3. **Quando o desvio deixa de funcionar porque todos começam a usá-lo?**
   Refinar a curva de 0% a 100% em passos menores e variar demanda.
4. **O semáforo faz o GPS escolher a rua errada?**
   Registrar a fase observada e futura na bifurcação; testar custos que incluam
   espera semafórica.
5. **Um GPS que reavalia a cada 5 segundos ajuda mais do que um que reavalia
   a cada 30?** Registrar arestas percorridas e decisões antes da bifurcação.
6. **Quem paga pelo desvio: motoristas da avenida ou moradores das ruas
   pequenas?** Medir demora e fila por via, não só a média geral.
7. **Qual cruzamento da Rua 7 de Setembro ou da Itajaí merece prioridade?**
   Localizar conexões do grafo usadas por muitos caminhos e testar intervenções
   semafóricas pareadas com fluxos calibrados.
8. **Uma nova ligação ou faixa pode piorar o trânsito?** Comparar rede base e
   cenário SUMO reconstruído, com a mesma demanda, sem pressupor o resultado.

As perguntas 1 a 3 podem ser ampliadas com o motor atual e demanda sintética.
As perguntas 4 e 5 precisam instrumentar melhor os sinais e a rota física.
As perguntas 6 a 8 exigem ainda mais atenção à demanda e às ruas afetadas.

## Reprodução e dados brutos

Executar na raiz do projeto, com `SUMO_BINARY` apontando para `sumo.exe`:

```powershell
python scripts/study_live_choice.py --levels alto
```

Resultados por par: [paired.csv](estudo-escolha-no-transito/paired.csv).
Resumo: [summary.json](estudo-escolha-no-transito/summary.json).
Cada execução tem `*.json` e a saída nativa `*.tripinfo.xml` no mesmo diretório.
O estudo de proporções está em [descobertas-para-apresentacao.md](descobertas-para-apresentacao.md).

Fonte municipal para o nome Beira-Rio:
https://www.blumenau.sc.gov.br/secao/noticias/62684
