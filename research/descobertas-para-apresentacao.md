# BLU-ROTAS: perguntas menos óbvias e resultados exploratórios

## Pergunta principal

**Qual fração de motoristas deve receber o desvio quando a via principal satura?**
Mandar todos para a rota mais rápida em fluxo livre, dividir igualmente e mandar
todos para a alternativa são apenas três pontos de uma curva. O estudo ampliado
testou 0%, 25%, 50%, 75% e 100% de desvio na Avenida Presidente Castelo Branco.

## Protocolo e verificações

- Rede SUMO 1.28 do recorte central de Blumenau, hash `633d9a0824eb0bb7`.
- Mesmo par origem/destino, 180 veículos em 240 s, sol, passo físico de 0,25 s,
  sem teleporte. Três sementes pareadas: `20261114`, `20261115`, `20261116`.
- As 2.700 viagens solicitadas nas cinco condições foram concluídas. Cada
  condição tem 540 observações de viagem, mas a unidade de repetição da
  comparação é a **execução por semente** (n=3), não cada veículo.
- O analisador confirmou a mesma rede, as mesmas duas rotas, IDs de demanda e
  horários planejados de partida em todas as condições de cada semente. A
  atribuição física foi de 0, 45, 90, 135 e 180 veículos no desvio por execução.
- 0%, 50% e 100% vêm das [execuções originais](estudo-castelo-branco/runs/)
  de 15/11; 25% e 75% são [execuções novas](estudo-proporcoes-castelo/runs/)
  de 17/11. O motor e a malha permaneceram os mesmos; o script ganhou apenas
  as duas políticas de alocação. Esta combinação temporal é uma limitação
  explícita do estudo exploratório.

## Resultados: o desvio tem uma dose útil

Médias das três execuções; tempos em segundos. "Porta a porta" é chegada menos
partida **planejada** e inclui a fila para conseguir entrar na rede. "Na rede"
começa quando o SUMO inseriu o veículo. P95 considera as viagens concluídas.

| Enviados ao desvio | Tempo na rede | Porta a porta | Espera para entrar | P95 na rede |
|---:|---:|---:|---:|---:|
| 0% | 308,82 | 326,90 | 18,20 | 553,20 |
| 25% | 236,18 | 254,24 | 18,18 | 359,25 |
| **50%** | **211,16** | **229,29** | **18,26** | **271,08** |
| 75% | 247,08 | 283,25 | 36,29 | 358,98 |
| 100% | 315,52 | 389,82 | 74,43 | 494,88 |

Neste cenário, 50% foi **o melhor dos cinco percentuais testados**, reduzindo
o tempo porta a porta em **97,60 s (29,9%)** contra 0%. Enviar 100% para o
desvio elevou esse mesmo tempo em **62,92 s (19,2%)** contra 0%. Não se pode
afirmar que 50% é o ótimo exato: percentuais intermediários não foram testados.

Diferenças pareadas de tempo porta a porta, média e intervalo t de 95% sobre
apenas três sementes (descritivos e exploratórios):

| Comparação | Diferença média | Intervalo de 95% |
|---|---:|---:|
| 25% − 0% | −72,66 s | −109,86 a −35,46 s |
| 50% − 0% | −97,60 s | −131,34 a −63,86 s |
| 75% − 0% | −43,65 s | −69,22 a −18,08 s |
| 100% − 0% | +62,92 s | +29,48 a +96,37 s |
| 50% − 25% | −24,94 s | −28,58 a −21,30 s |
| 75% − 50% | +53,95 s | +43,66 a +64,25 s |

O mecanismo sugerido pelos dados é **migração do gargalo**: entre 50% e 75%,
a espera média para entrar quase dobra (18,26 → 36,29 s), mesmo com menos
veículos na via principal. Com 100%, a espera chega a 74,43 s. Isto é uma
interpretação do cenário, não uma medição do trânsito real. O [gráfico
vetorial](estudo-proporcoes-castelo/proporcoes.svg) e os [valores com todas as
métricas e intervalos](estudo-proporcoes-castelo/proporcoes.csv) podem ser usados
na apresentação.

## Duas descobertas adicionais já sustentadas por dados

1. **Uma recomendação que favorece um indivíduo pode prejudicar o conjunto.**
   Na Avenida Brasil com 180 veículos, mandar só o motorista focal para o
   desvio reduziu a viagem dele de 94,92 para 84,58 s. A média coletiva,
   porém, passou de 127,81 para 128,34 s; a diferença média de +0,53 s tem
   intervalo pareado de −0,62 a +1,68 s (três sementes), então não há base
   para afirmar piora coletiva nesse caso isolado. Quando metade foi desviada,
   a média subiu para 140,81 s. Em Castelo Branco, a mesma política de 50%
   reduziu a média para 211,16 s: a direção do efeito depende do corredor.
2. **GPS que muda o plano não significa veículo que mudou de caminho.** No
   estudo da Avenida Brasil, 465 de 900 veículos tiveram ao menos um recálculo
   de rota, somando 934 eventos. Mesmo assim, os seis campos físicos conferidos
   (partida real, chegada, duração, espera, distância e tempo perdido) foram
   iguais aos do GPS estático nos 900 pares. Isso é um resultado sobre o
   comportamento **desta implementação**: a contagem de recálculos não é uma
   medida de benefício real. Ainda é preciso registrar arestas efetivamente
   percorridas e o instante de passagem pela bifurcação para explicar por quê.

## O que o projeto consegue e o que falta

O motor atual já suporta estudos computacionais pareados com rede real OSM,
dinâmica SUMO, intervenções, sementes e arquivos nativos de viagens. Portanto,
há perguntas científicas testáveis **dentro do modelo**. A próxima pergunta
mais forte é: **a melhor porcentagem de desvio muda quando a demanda e a janela
de partidas mudam?** Testar 0% a 100% em passos menores, pelo menos dez
sementes e mais pares origem/destino, mantendo as comparações pareadas.

Para falar de *Blumenau real*, o projeto ainda precisa de contagens observadas
por via e horário, distribuição de origens/destinos, validação dos semáforos e
da capacidade de inserção, além de comparação com tempos observados. Para
avaliar o GPS, precisa registrar percurso físico por aresta, previsão feita
antes da bifurcação, economia prevista e economia efetiva. O resumo acadêmico
deve apresentar as 7.200 viagens anteriores como **observações simuladas em
cenários repetidos**, não como 7.200 motoristas independentes da cidade.

## Reproduzir

Na raiz do projeto, com `SUMO_BINARY` apontando para `sumo.exe`:

```powershell
python scripts/collective_route_study.py --corridor castelo --levels alto `
  --strategies um_quarto tres_quartos --seeds 20261114 20261115 20261116 `
  --output research/estudo-proporcoes-castelo
python scripts/analyze_route_proportions.py
```

Os arquivos `*.tripinfo.xml` de cada execução contêm as medidas nativas SUMO.
O script analítico verifica pareamento e completude antes de gerar CSV e SVG.
Os resultados não demonstram causalidade sobre tráfego observado na cidade.

## Ajustes recomendados no resumo acadêmico entregue

- Substituir "caminhos alternativos, mais eficientes" por "rotas alternativas
  testadas": sem tráfego, a alternativa era mais lenta nos dois corredores.
- Informar que as 7.200 viagens são observações simuladas de cenários repetidos,
  com três sementes por comparação. Evitar tratá-las como amostra de motoristas
  independentes ou como dados coletados nas ruas de Blumenau.
- Trocar "manipulação completa do fluxo de trânsito" por "controle dos cenários
  simulados no recorte central". Antes do envio, substituir o email `xx@xx`.
