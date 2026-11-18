# BLU-ROTAS
autores:
cauã lucas leão rodrigues

Simulador local de trânsito e laboratório científico para um recorte **real de Blumenau, SC**. A movimentação, os semáforos e as interações entre veículos são calculados pelo [Eclipse SUMO](https://eclipse.dev/sumo/); o navegador mostra estados recebidos por WebSocket e interpola a apresentação entre passos físicos. O projeto inclui frontend React/MapLibre, API FastAPI, GPS com Dijkstra, editor de rede SUMO, importação OSM e experimentos reproduzíveis.

## Executar no Windows após clonar ou extrair o ZIP

Instale [Python 3.11 ou superior](https://www.python.org/downloads/windows/), [Node.js 20 ou superior](https://nodejs.org/en/download) e o [SUMO para Windows](https://eclipse.dev/sumo/docs/Downloads.html). A versão verificada foi SUMO **1.28.0**. Extraia o ZIP do SUMO em um caminho simples, como `C:\SUMO\sumo-win64-1.28.0`.

No PowerShell, dentro da pasta `blu-rotas`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
$env:SUMO_BINARY = "C:\SUMO\sumo-win64-1.28.0\bin\sumo.exe"
.\iniciar.ps1
```

Abra **http://127.0.0.1:8000**. Clique no botão **Iniciar** na barra inferior. Em **Criar carro**, escolha os pontos no mapa ou use **Gerar viagens**. O backend também serve o frontend compilado, portanto não é necessário manter um segundo servidor Vite. O arquivo `data/blumenau.net.xml` já acompanha o projeto.

Você também pode abrir [iniciar.cmd](iniciar.cmd) com dois cliques depois da instalação. Mantenha o terminal aberto e use o endereço que ele imprimir (normalmente `http://127.0.0.1:8000/`). Se outra aplicação ocupar a porta 8000, o iniciador escolhe uma porta entre 8001 e 8010. Não abra `frontend/dist/index.html` como arquivo local: o mapa precisa da API.

Nesta instalação do Codex, `iniciar.cmd` encontra o Python e o SUMO portáteis da pasta de trabalho. Esses executáveis **não fazem parte do repositório**; colegas que clonarem o projeto devem instalar as dependências acima.

Se usar outra versão ou pasta do SUMO, ajuste `SUMO_BINARY`. Se o executável `sumo.exe` estiver no `PATH`, a variável é opcional. `SUMO_HOME` só é necessário para algumas ferramentas do SUMO; em um caminho com caracteres acentuados, a versão de Windows testada falhou ao validar XML, então prefira instalar o SUMO em um caminho ASCII.

## Recriar a malha

O recorte inicial vai de longitude −49,077 a −49,055 e latitude −26,928 a −26,906. Abrange Centro, Ponta Aguda e trechos próximos. Os arquivos OSM e SUMO já estão incluídos; para atualizar os dados:

```powershell
node scripts\download-osm.mjs
node scripts\prepare-map.mjs
.\scripts\build-network.ps1 -Netconvert "C:\SUMO\sumo-win64-1.28.0\bin\netconvert.exe"
```

A API principal do OSM tem limite de nós por requisição. Um recorte municipal maior deve usar extratos OSM adequados e processamento em blocos. O `netconvert` pode emitir avisos sobre relações de transporte e restrições que atravessam a borda do recorte; a versão fornecida foi construída com sucesso. As arestas usadas pelo roteador são filtradas por permissões de automóvel nas faixas e nas conexões internas.

## Controles

- **Navegação:** o mapa reúne as ferramentas em cinco grupos: Explorar, Carros e GPS, Ruas e grafo, Semáforos e Cidade. Escolha a ação específica nos botões do painel. O botão da barra superior abre tela cheia; a barra esquerda e o painel direito podem ser ocultados, e o painel direito também pode ser estreitado. O mapa se redimensiona automaticamente. Os botões **?** explicam os controles mais complexos.
- **Simulações:** aba dedicada aos estudos A–F, variantes personalizadas, execução rápida ou visual, replay, comparador A/B e exportação. Os cartões iniciais explicam o fluxo. Abra [tutorial_de_situações.html](frontend/public/tutorial_de_situações.html) no navegador ou pelo botão **?** do aplicativo para um roteiro de situações e coleta de dados.
- **Carro personalizado:** em **Criar carro**, clique em **Origem**, **Ponto de passagem** (quantos desejar) e **Destino**, depois no mapa. Os cliques são ajustados à via mais próxima. O GPS mostra até três caminhos dirigíveis distintos: o melhor, um secundário e o mais demorado entre os desvios razoáveis encontrados. Clique em cada opção para vê-la no mapa, defina quantos carros e a cor de cada grupo e lance os grupos no mesmo instante simulado. O SUMO pode inserir veículos em instantes diferentes quando falta espaço na via. Escolha velocidade, GPS estático ou dinâmico, intervalo de atualização e economia mínima para desvio. O GPS dinâmico pode trocar a rota depois da partida; use o estático para manter a opção escolhida.
- **Status do carro:** ao selecionar um veículo, o painel exibe **Em trânsito**, **Preso no trânsito** ou **Parado no semáforo**, além de espera, velocidade, tempo de viagem, rota, próxima análise de GPS, tempo restante e possível economia. Em **Inspecionar carro**, atualize as alternativas para a posição atual, visualize uma e aplique a escolha; ela ficará em GPS estático até nova configuração. A seleção e a rota são limpas quando o carro chega ou a simulação termina. A classificação usa velocidade observada, limite da via e próximo semáforo.
- **GPS:** Dijkstra sobre as conexões dirigidas do SUMO. Cada carro com GPS dinâmico avalia as vias no seu próprio intervalo, usando custos derivados da velocidade observada de **todos os veículos**. O caminho só muda com benefício suficiente ou quando uma via adiante é fechada; a mudança também respeita a faixa de acesso ao próximo cruzamento. O GPS geral define padrões para os carros gerados automaticamente, e o painel do veículo permite ajustes individuais.
- **Ruas e obras:** as vias base do OSM são desenhadas de forma contínua. Ao aproximar, setas sobre as arestas dirigidas do SUMO mostram o sentido permitido para automóveis. Em **Obras e vias**, clique perto da rua para destacar o trecho SUMO exato; quando houver trechos próximos, escolha na lista curta por nome e comprimento. O carro selecionado, sua rota e o acompanhamento da câmera permanecem ativos enquanto você escolhe e interdita uma rua. O painel mostra os desvios e a última troca de rota do carro, com opção para exibir a rota anterior. Uma interdição total pinta todo o trecho em vermelho vivo contínuo, acima da rota do GPS; a faixa fechada parcialmente continua amarela. Interdite, feche uma faixa quando houver duas ou mais, reduza a velocidade ou restaure somente o trecho destacado. A permissão da faixa e o limite de velocidade mudam no TraCI. Quando não há alternativa, o veículo pode ficar retido.
- **Semáforos:** o mesmo grupo permite inspecionar e adicionar controladores. Pontos coloridos resumem o cruzamento; aproxime para ver marcadores separados por faixa. No painel, selecione uma conversão de faixa para ver sua cor atual e a cor em cada fase, além das vias que passam. **Misto** significa movimentos simultâneos com cores diferentes. Ajustar a duração de uma fase mantém os estados e a sequência do controlador; não força imediatamente uma abertura isolada. Restaurar recupera o programa inicial.
- **Movimento dos carros:** o SUMO avança em passos de 0,25 segundo; o navegador interpola cada deslocamento entre posições recebidas, com animação contínua. Isso reduz o atraso normal para aproximadamente um passo de simulação. Em frotas grandes, a frequência efetiva depende da capacidade do computador. As posições vêm das faixas reais do SUMO; a interpolação reta pode cortar discretamente curvas muito fechadas entre dois passos.
- **Loop diário:** em **Loop diário**, escolha a hora de início, carros por minuto no fluxo normal e multiplicador de pico. O relógio simulado percorre 24 horas e repete. A geração cresce das **07:00 às 09:00** e das **17:00 às 19:00**. O painel mostra a taxa atual; a velocidade 1×/2×/5× afeta o tempo de execução da simulação.
- **Cidade:** inicie, pause, avance um segundo, reinicie e ajuste 1×, 2× ou 5×. Gere 10, 50, 100 ou 500 viagens; 500 é uma meta de teste dependente do computador.
- **Mapa e veículos 2.0:** escolha tema claro/escuro (a preferência fica salva no navegador). Há carros vistos de cima no zoom próximo, pontos coloridos e agrupamento no zoom distante, pontes, vias principais e cores de congestionamento. Ao selecionar um carro, destaque rota atual, rota anterior opcional, origem e destino. Quando o GPS muda a rota, a linha ganha brevemente uma cor de atenção e a rota anterior pode ser vista; não há janela de aviso sobre o mapa. **Seguir veículo** mantém a câmera centrada suavemente; arrastar ou dar zoom manualmente desativa o seguimento. O painel exibe posição, velocidade, distância, ETA e horário previsto pelo simulador.
- **Relógio:** comece às 06:00, 08:00, 12:00, 18:00 ou em horário personalizado. Pause, reinicie e acelere o tempo pela barra inferior. A demanda de pico do loop é sintética e configurável.
- **Grafo e pontos:** em **Grafo viário**, aproxime para exibir vértices reais do roteador, IDs, pesos, graus, componentes e caminho mínimo. **Adicionar ponto** cria um acesso sobre a rua, utilizável como origem/destino; ele não cria cruzamento físico.
- **Pontos de acesso e grafo:** pontos salvos sobre a rua aparecem como vértices amarelos reais na lista de adjacência do roteador, ligados à via por pesos proporcionais à posição. Eles podem ser usados como origem ou destino; não criam cruzamentos físicos. Os marcadores temporários de criação de carros desaparecem após o lançamento.
- **Editar via mapeada:** em **Obras e vias**, clique num trecho e ajuste mão única ou dupla, número de faixas por sentido e limite de velocidade. A edição vale para a rua OSM inteira que contém o trecho, é salva em cenário e reconstrói o SUMO; difere de interditar somente o trecho durante uma execução.
- **Ruas sem nome:** a malha base exibe 1.329 vias OSM, das quais 741 chegam como “Via sem nome”. No editor de via, dê um nome para a cópia do cenário; ele passa ao mapa e à rede SUMO reconstruída, sem modificar o OSM original. A auditoria da fonte verificou que as vias OSM ausentes do desenho são caminhos de pedestres, escadas, corredores, ciclovias ou vias propostas. Ruas reais ausentes da fonte exigem importar dados mais recentes ou desenhar uma conexão fictícia validada pelo SUMO.
- **Construir estrada:** marque a origem numa via, até 12 pontos de curva sobre uma rua pequena não mapeada e o destino em outra via. Configure nome, sentido A → B ou B → A, faixas, velocidade, capacidade estimada e custo hipotético. O editor modifica uma cópia do OSM, reconstrói a malha SUMO, verifica a conexão dirigível, salva o cenário e reinicia a simulação em pausa. Cruzamentos com outras vias são criados somente nas extremidades conectadas, não automaticamente em cada cruzamento visual da linha. Cenários podem ser ativados, editados e removidos sem tocar na fonte OSM original.
- **Adicionar semáforo:** clique perto de um cruzamento físico em **Adicionar semáforo**. O sistema insere um controlador na cópia OSM, reconstrói e valida o sinal no SUMO. Um ponto isolado da via não pode receber semáforo antes de uma conexão física.
- **Gerenciar mapas:** importe arquivo OSM XML local, opcionalmente com recorte por coordenadas, para criar uma cidade/área independente. A importação de Blumenau inteira exige fornecer o arquivo OSM e memória/tempo suficientes; o pacote inclui o recorte central original.
- **Laboratório científico:** em **Modo Ciência**, execute A GPS, B semáforos, C saturação, D obras, E estrada nova, F clima ou variantes próprias. Modos rápido e visual usam a mesma física SUMO. Veja resultados por veículo, via e cenário, compare duas execuções, repita com mesma semente/demanda, assista a replay de snapshots reais e exporte CSV, JSON ou PDF. Viagens não concluídas permanecem na contagem. Veja [modelo e metodologia](docs/modelo-2.0.md) para variáveis, métricas e limites.
- **Estudo de rotas coletivas:** o protocolo em [docs/estudo-rotas-coletivas.md](docs/estudo-rotas-coletivas.md) reproduz as comparações “todos na avenida”, “um motorista alternativo”, “todos alternativos”, “metade em cada rota” e “GPS dinâmico” em três níveis de demanda e três sementes, usando o mesmo SUMO. Os scripts geram tabelas CSV, dados brutos e gráficos de tempo, ocupação e calor da rede.
- **Resultados já calculados:** [relatório acadêmico](research/relatorio-estudo-rotas.md), CSVs, gráficos SVG e saídas nativas do SUMO estão em `research/`. Os bancos SQLite locais não são necessários para reproduzir as tabelas publicadas.
- **Clima:** sol, chuva fraca ou intensa aplicam fatores experimentais de velocidade, aceleração, desaceleração e tempo de segurança nos veículos do SUMO.
- **Ciência:** amostras, viagens concluídas, intervenções, gráficos e exportação CSV vêm do SQLite. Um cenário salvo registra semente, pares origem/destino, horário de partida, GPS, clima, obras e fases modificadas; pode ser reexecutado.
- **Laboratório:** lista e matriz de adjacência, BFS, DFS, Dijkstra com fila simples ou heap, Prim, componentes e estatísticas. O módulo separado de municípios tem CRUD por API e experimentos com 10, 20, 50 e 100 cidades.

## Testes

```powershell
$env:SUMO_BINARY = "C:\SUMO\sumo-win64-1.28.0\bin\sumo.exe"
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run build
```

Os 20 testes cobrem grafo, GPS, SUMO, chuva, semáforos, obras, carros personalizados, alternativas, grupos simultâneos, pontos de acesso no grafo, faixas e sentidos reconstruídos, rede fictícia trafegável, importação OSM, demanda determinística, métricas, comparação, exportação e desenho pareado do estudo de rotas. O `pytest.ini` guarda arquivos temporários dentro do projeto, evitando o erro de acesso do Python portátil na pasta temporária do perfil Windows. Testes de carga dependem da máquina.

## Estrutura

```text
backend/       API, controlador TraCI, grafos, municípios e SQLite
frontend/      React, MapLibre, Recharts e CSS
data/          recorte OSM, GeoJSONs e rede SUMO
scripts/       atualização da rede e inicialização
tests/         algoritmos, API e integração SUMO
docs/          método e limites da versão
```

## Escopo e limites desta versão

O pacote contém o recorte central, não todo o município. O gerenciador aceita arquivos OSM para ampliar a região ou importar outras cidades; não faz download automático de uma malha inteira. A atribuição de bairro é aproximada, sem limites administrativos oficiais. Pontos de acesso não dividem fisicamente a rua; uma estrada nova é construída e validada numa rede SUMO separada. Semáforos novos precisam de cruzamentos físicos válidos. Demanda calibrada com contagens reais e garantia de ocorrência do paradoxo de Braess não fazem parte do modelo. Os resultados descrevem **cenários simulados**, não medições do trânsito de Blumenau. O ZIP limpo não inclui bancos SQLite nem experimentos de teste; esses arquivos são gerados ao executar. Veja [limitações e metodologia](docs/modelo-2.0.md).

Dados © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), licença ODbL. SUMO © Eclipse Foundation, licença EPL-2.0 ou GPL-2.0-or-later.
