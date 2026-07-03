# RefCap — Guia de Arquitetura (Overview)

> **Propósito deste documento.** Servir de mapa para navegar o repositório `BUAAPY/RefCap` *antes* do mergulho técnico função a função. Cada afirmação estrutural vem acompanhada do arquivo (e, quando útil, função/linha) que a comprova, para que você possa abrir o código e confirmar por conta própria. Este é o **esqueleto e os sinalizadores** — não a dissecação de cada algoritmo, que fica para etapas posteriores.
>
> Escopo: análise derivada **exclusivamente do código** do repositório. O artigo ainda não foi consultado; onde houver reivindicação de novidade, isso será reconciliado com o paper depois.

---

## 1. A ideia central (em uma frase)

RefCap resolve **Video Corpus Moment Retrieval (VCMR)** — dado um texto de consulta e um *corpus* de vídeos não-recortados, localizar o par `(vídeo, intervalo [início, fim])` que corresponde à consulta — **sem treinar nada no dataset alvo**. A estratégia unificadora é **converter cada vídeo em uma estrutura puramente textual** (legendas densas refinadas + palavras-chave) e reduzir o problema a **recuperação texto-a-texto**, resolvida com modelos pré-treinados de prateleira (BLIP, sentence-transformers, GloVe).

Essa redução é o que torna o zero-shot viável: troca-se o problema difícil (alinhar pixels e texto) pelo problema resolvido (similaridade texto-texto).

---

## 2. Vista de voo: dois estágios acoplados por disco

O sistema tem **dois estágios completamente desacoplados**, cuja única interface é um arquivo em disco (`tree.json`). Isso é arquiteturalmente importante: a indexação (cara, offline) roda uma vez; a recuperação (barata, online) reusa o índice quantas vezes quiser.

```
ESTÁGIO 1 — CONSTRUÇÃO (offline, 1x por corpus)          ESTÁGIO 2 — RECUPERAÇÃO (online, por consulta)
=================================================        ===============================================
 vídeos brutos                                            consulta textual ("a person opens a door")
      │                                                        │
      ▼                                                        ▼
 [1] amostragem 1 fps        (viddataset.py)             carrega índice (capTree.py)
      ▼                                                        │
 [2] captioning por frame    (capgenerator/)                   ▼
      ▼                                                   codifica consulta + calcula similaridade
 [3] features de frame       (sim_utils.py)              (retrievepipe/: sent | key | mix)
      ▼                                                        ▼
 [4] score legenda-frame ITM (sim_utils.py)              top-1000 momentos candidatos
      ▼                                                        ▼
 [5] denoising de legendas   (denoiser/window.py)        NMS temporal (temporal_nms.py)
      ▼                                                        ▼
 [6] segmentação (proposals) (propgenerator/)            métricas Recall/IoU (standalone_eval/eval.py)
      ▼
 [7] montagem da árvore ──────────► tree.json ──────────► (interface entre os estágios)
     (constructpipe/base.py)
```

**Evidência do desacoplamento:** o Estágio 1 termina salvando `tree.json` (`constructpipe/base.py::build_tree_meta`, linha 181); o Estágio 2 começa carregando esse mesmo arquivo (`retrieve.py::start_inference`, linhas 263–269, `CapTree(cfg, tree_meta_path, ...)`). Nenhum objeto em memória é compartilhado entre os dois — só o JSON.

---

## 3. Mapa de diretórios

| Diretório / arquivo | Papel na arquitetura | Importância |
|---|---|---|
| `construct.py` | Ponto de entrada do Estágio 1. Monta e dispara o pipeline de construção. | Crítico |
| `retrieve.py` | Ponto de entrada do Estágio 2. Monta índice + dataset + pipeline e avalia. | Crítico |
| `scripts/construct.sh`, `scripts/retrieve.sh` | Superfície de controle: definem todos os hiperparâmetros e disparam os `.py`. | Crítico |
| `config/` | Definição declarativa de todos os argumentos (`cfg.py`) + parser (fork do HuggingFace). | Crítico |
| `pipeline/` | **Núcleo do método.** Contém os 6 componentes plugáveis (ver §5). | Crítico |
| `dataset/` | Carregadores: `viddataset.py` (frames de vídeo) e `dataset.py` (consultas de teste). | Alto |
| `utils/` | Funções transversais: similaridades (`sim_utils.py`), NMS (`temporal_nms.py`), NLP (`tree_utils.py`), carregamento de modelos (`model_utils.py`), captioning MiniGPT externo. | Alto |
| `standalone_eval/` | Cálculo de métricas VCMR/VR (Recall@K em faixas de IoU). Derivado do protocolo TVR. | Alto (só avaliação) |
| `annos/{charades,activitynet}/vcmr.jsonl` | Duplo papel: **(a)** manifesto de quais vídeos indexar (só o campo `vid_name` na construção) e **(b)** consultas + gabarito para avaliação. **Não** é usado para "aprender". | Contextual |
| `meta/` (gerado) | Caches intermediários reutilizáveis: legendas, features, scores, pesos GloVe. | Gerado |
| `results/` (gerado) | Saídas por experimento: `construct/` (árvores, proposals) e `retrieve/` (métricas, predições). | Gerado |

---

## 4. Pontos de entrada e o fluxo de execução

### Estágio 1 — `construct.py`
O `main()` (linha 27) faz três coisas em sequência que revelam toda a arquitetura de construção:

1. **Carrega os modelos** — `load_pretrained_models(cfg)` (linha 42, definido em `utils/model_utils.py`).
2. **Instancia os componentes plugáveis via fábrica** — linhas 43–47:
   ```python
   caption_generator = get_capgen_class(cfg.caption_generator)(cfg, pretrained_models)
   caption_denoiser  = get_denoiser_class(cfg.caption_denoiser)(cfg, pretrained_models)
   proposal_generator= get_propgen_class(cfg.proposal_generator)(cfg, pretrained_models)
   construct_pipeline= get_constructpipe_class(cfg.construct_pipeline)(cfg, caption_generator, caption_denoiser, proposal_generator, pretrained_models)
   ```
   Isso evidencia que **a construção é composta por três peças intercambiáveis** (gerador de legendas, denoiser, gerador de proposals), orquestradas por um pipeline.
3. **Dispara o pipeline** — `construct_pipeline.construct()` (linha 49).

### Estágio 2 — `retrieve.py`
O `start_inference()` (linha 236) monta a recuperação em quatro objetos (linhas 268–277):
```python
pretrained_models = load_pretrained_models(cfg)
captree           = CapTree(cfg, tree_meta_path, pretrained_models)   # carrega o índice
test_dataset      = DataSet4Test(gt_anno_path, captree_meta=...)       # consultas + gabarito
captree.compute_tree_feature(...)                                      # codifica o índice
infer_pipeline    = get_retrievepipe_class(cfg.retrieve_pipeline)(...) # sent | key | mix
eval_epoch(infer_pipeline, test_dataset, cfg)                          # roda e avalia
```
Isso evidencia que **a recuperação é: um índice (`CapTree`) + um dataset de consultas + uma pipeline de matching intercambiável**, tudo fechado por uma avaliação.

---

## 5. Componentes críticos (o coração da arquitetura)

A tabela abaixo é o mapa rápido; os parágrafos que a seguem explicam *por que* cada peça é estrutural e apontam o código-prova.

| # | Componente | Arquivo / função-chave | O que é (papel) |
|---|---|---|---|
| A | **Orquestrador de construção** | `constructpipe/base.py::construct` (l. 67–90) | A espinha dorsal; encadeia as 7 etapas do Estágio 1. |
| B | **Gerador de legendas** | `capgenerator/BlipCapGener.py`; `capgenerator/base.py` | Transforma frames em texto (entrada de todo o resto). |
| C | **Sinal de qualidade ITM** | `utils/sim_utils.py::get_caption_frame_sims` | O sinal reaproveitado que sustenta denoising e segmentação. |
| D | **Denoiser de legendas** | `denoiser/window.py::denoise_caption` (l. 20–35) | O "refino" (o *Refined* do título). |
| E | **Gerador de proposals** | `propgenerator/QMPropGener.py::generate_proposal` (l. 69) | Segmentação temporal sem treino (fronteiras de eventos). |
| F | **Índice em árvore** | `treebuilder/capTree.py::CapTree` | A estrutura pesquisável do corpus. |
| G | **Pipelines de recuperação** | `retrievepipe/{SentPipe,KeyPipe,MixPipe}.py` | O matching consulta↔índice em tempo de query. |
| H | **Avaliação** | `standalone_eval/eval.py::eval_by_task_type` | Mede desempenho (Recall@K, IoU). |
| I | **Configuração** | `config/cfg.py` | A superfície declarativa de controle. |

### A — Orquestrador de construção · *espinha dorsal*
`constructpipe/base.py::construct()` (linhas 67–90) é o método que define a **ordem canônica e as dependências entre etapas**. Lendo-o de cima a baixo você vê a arquitetura inteira do Estágio 1: gera legendas → computa features → computa scores brutos → **denoise** → **recomputa scores nas legendas denoised** → gera proposals → monta árvore. É o melhor ponto de partida para entender "quem alimenta quem". Note em particular que os scores são computados **duas vezes** (l. 76 e l. 83, ambos via `compute_capframe_scores`): uma antes e uma depois do denoising — evidência de que o denoising altera as legendas e por isso os scores precisam ser refeitos.

Aqui também mora o uso do `annos/`: `select_videos` (l. 184) lê **apenas** `data['vid_name']` (l. 191) — ou seja, na construção o arquivo de anotação funciona só como **lista de vídeos a processar**, nunca como rótulo.

### B — Gerador de legendas · *transformação de entrada*
Tudo no sistema é derivado das legendas por frame; se elas forem ruins, todo o resto degrada. Há duas implementações sob uma interface comum:
- **BLIP** (`BlipCapGener.py::generate_caption`): legenda cada frame com `blip-image-captioning-large`, usando o prompt `"a photo of"` que depois é removido (l. ~30–38 do arquivo).
- **MiniGPT-4-v2** (`utils/genCaptions_minigpt.py`): script **externo**, rodado fora do pipeline principal; o `base.py::BaseCapGen.generate_caption` (l. ~48) inclusive impõe `assert video_name in self.already_video_names, "You should use external scripts..."`, evidenciando que para MiniGPT as legendas precisam ser geradas antes, à parte.

O prompt do MiniGPT é `'Please describe this image with at most 30 words'` (`genCaptions_minigpt.py`, l. ~197). **Ponto arquitetural chave:** o captioning é **genérico e agnóstico à consulta** — legenda-se o vídeo sem saber o que será perguntado. É isso que permite construir um índice reutilizável para consultas arbitrárias.

### C — Sinal de qualidade ITM · *o backbone reaproveitado*
`utils/sim_utils.py::get_caption_frame_sims` (e os auxiliares `_get_frame_features`, `_get_caption_features`) computa, via BLIP-ITM, a **similaridade entre cada legenda e o seu próprio frame**. Esse número é um *proxy de confiabilidade da legenda* e é **reutilizado em dois lugares críticos**: (1) o denoiser decide o que sobrescrever com base nele (§D) e (2) a variante `it` da segmentação pondera a matriz de similaridade por ele (§E). Por isso este utilitário, embora modesto, é **load-bearing**: é o único ponto onde o sinal visual entra na parte "textual" do método. Também é o ponto de maior acoplamento ao BLIP (acessa `.vision_model`, `.vision_proj`, `.text_proj`).

### D — Denoiser de legendas · *o refino*
`denoiser/window.py::denoise_caption` (l. 20–35) implementa a **propagação temporal de legendas confiáveis**: percorre os frames; se o score ITM ultrapassa `figsim_denoise_thr` marca uma âncora "de alta confiança"; se um frame tem score baixo e está dentro de `denoise_window_width` da última âncora, **copia** a legenda da âncora por cima da legenda ruim (l. 33–34, `copy.deepcopy(...)`). É este componente que materializa o "*Refined* Dense Video Captioning" do título. Há também um `BaseDenoiser` (`denoiser/base.py`) que não faz nada (`return meta`), usado como *baseline* de ablação (`caption_denoiser=base`).

### E — Gerador de proposals · *segmentação temporal*
`propgenerator/QMPropGener.py::generate_proposal` (l. 69) é onde o vídeo é **fatiado em eventos**, sem treino. Duas partes provam sua mecânica:
- **Construção da matriz de similaridade** (`calculate_similarities`, l. 28): três modos — `txt` (só legendas), `it` (legendas × score ITM, o padrão) e `vis` (features visuais).
- **Detecção de fronteiras por novidade** (l. 74–88): monta um *kernel checkerboard* (quadrantes +1/−1, l. 76–83), convolui a matriz e extrai a **diagonal** como score de novidade por frame. É o clássico *kernel de novidade de Foote*; o que é potencialmente próprio do RefCap é aplicá-lo a uma matriz **derivada de legendas e ponderada por ITM**.

Cada segmento resultante recebe **uma legenda representativa** (a do frame de maior score no trecho, l. ~133) e um conjunto de **palavras-chave** (substantivos + verbos de todas as legendas do trecho, via `utils/tree_utils.py::get_nouns_verbs`, l. 135–139).

### F — Índice em árvore · *a estrutura pesquisável*
`treebuilder/capTree.py::CapTree` transforma os proposals num índice consultável. `build_relations` "achata" todos os proposals do corpus em listas paralelas (`caps`, `keys`) com mapeamentos de volta para os nós (`cap_to_nodeid`, `vidname_to_capids`, …). `compute_tree_feature` então **codifica** tudo: legendas via sentence-transformer (`encode_caps`) e palavras-chave via GloVe (`encode_keys`). **Observação estrutural importante:** apesar do nome "árvore" e do BFS em `build_relations` suportar profundidade arbitrária, a árvore de fato construída em `build_tree_meta` (`constructpipe/base.py`, l. 169–182) tem **só 2 níveis** (vídeo → proposals) — na prática é um índice plano de dois níveis.

### G — Pipelines de recuperação · *o matching em tempo de query*
`retrievepipe/` oferece três estratégias sob a mesma interface (`base.py::BaseRetrievePipe`):
- **`SentPipe`** — só nível-sentença (cosseno consulta↔legendas).
- **`KeyPipe`** — só nível-palavra (GloVe, com agregação "max sobre keys do proposal → média/max sobre keys da consulta").
- **`MixPipe`** (padrão) — **fusão tardia** das duas: `esm_sims = sent·ratio + key·(1−ratio)` (`MixPipe.py`, l. 130 para VCMR e l. 135 para VR). É a peça que combina os dois sinais e a candidata a novidade de recuperação.

Em todas, o resultado final são os `max_vcmr_props` (1000) melhores proposals por consulta (ex.: `MixPipe.py`, l. 138–139, `torch.topk`).

### H — Avaliação · *a régua*
`standalone_eval/eval.py::eval_by_task_type` computa Recall@{1,10,100} em faixas de IoU para VCMR/SVMR/VR. A regra de acerto está documentada no próprio arquivo (l. 85–87): um momento predito é positivo só se **(1)** o `vid_name` bate com o gabarito **e (2)** o IoU temporal supera o limiar. Antes disso, `retrieve.py::eval_epoch` (l. 182) aplica **NMS temporal** (`utils/temporal_nms.py`, limiar 0.5) para remover predições sobrepostas. Este bloco é **só medição** — não faz parte do método de recuperação em si, e é o que você contornaria num modo de produção puro.

### I — Configuração · *a superfície de controle*
`config/cfg.py` define tudo declarativamente em três dataclasses: `BasicArguments` (comum), `BuildArguments` (construção) e `TestArguments` (recuperação). Ler essas três classes é a forma mais rápida de descobrir **todos os botões** do sistema e seus defaults, sem caçar `argparse` espalhado.

---

## 6. Superfície de controle (os botões que importam)

Definidos em `scripts/construct.sh` e `scripts/retrieve.sh`; declarados em `config/cfg.py`.

**Construção (`construct.sh`):**

| Parâmetro | Governa | Componente afetado |
|---|---|---|
| `collection` | Dataset (`charades`/`activitynet`) → qual `annos/*/vcmr.jsonl` ler | manifesto de vídeos |
| `caption_generator` | `blip` ou `minigpt` | §B |
| `caption_denoiser` | `window` (ativa refino) ou `base` (desliga) | §D |
| `figsim_denoise_thr`, `denoise_window_width` | Limiar de confiança e largura da janela de propagação | §D |
| `prop_sim_type` | `it` / `txt` / `vis` — como montar a matriz de similaridade | §E |
| `prop_score_thr`, `prop_kernel_width`, `prop_min_cnt`, `prop_max_cnt` | Seleção de fronteiras (nº de segmentos, separação, corte) | §E |

**Recuperação (`retrieve.sh`):**

| Parâmetro | Governa | Componente afetado |
|---|---|---|
| `construct_name` | Qual índice (`tree.json`) usar | interface entre estágios |
| `retrieve_pipeline` | `sent` / `key` / `mix` | §G |
| `key_policy` | `max_mean` / `max_max` — agregação de keywords | §G (Key/Mix) |
| `retrieve_sent_ratio` | Peso da fusão sentença×palavra (0.5) | §G (Mix) |
| `max_vcmr_props` | Nº de momentos candidatos por consulta (1000) | §G + NMS |

> **Alerta para leitura futura:** esses limiares (0.4, 0.2, 0.5, …) são constantes mágicas. Verificar no artigo se foram fixados a priori ou tunados em dados rotulados — tuning no teste seria uma forma indireta de supervisão, relevante para julgar a alegação "zero-shot".

---

## 7. Artefatos de dados produzidos (onde as coisas caem)

Rastrear o fluxo de arquivos ajuda a entender o que é cache reutilizável versus saída por experimento (ver `config/cfg.py`, l. 8–24, e `constructpipe/base.py::create_dirs`, l. 55).

```
meta/                                    (cache — computado 1x por collection+caption_generator)
├── captions/{collection}_{gen}.jsonl    legendas por frame            (§B)
├── framefeatures/{collection}.pt        features visuais BLIP         (§C)
├── scores/{collection}_{gen}.pt         scores legenda-frame brutos   (§C)
└── glove.6B/glove.6B.300d.txt           pesos GloVe (pré-requisito externo)

results/construct/{collection}/{construct_name}/   (por construção)
├── settings.json                        config congelada do experimento
├── denoised_captions.jsonl              legendas após refino          (§D)
├── denoised_capframe_scores.pt          scores recomputados           (§C/§D)
├── prop_sims.pt                         matrizes de similaridade      (§E)
├── proposals.json                       segmentos + legenda + keys    (§E)
└── tree.json                            ◄── O ÍNDICE (interface p/ §2)

results/retrieve/{collection}/{retrieve_name}/     (por recuperação)
├── build_settings.json / eval_settings.json
├── metrics.json                         Recall@K, IoU                 (§H)
└── vcmr_preds.json                      momentos recuperados
```

O cache em `meta/` é a razão de a construção poder ser reexecutada barato: legendas, features e scores brutos só são computados na primeira vez (guardas `if os.path.exists(...)` em `compute_frame_features` l. 122 e `compute_capframe_scores` l. 96).

---

## 8. O padrão de extensibilidade (como o código foi feito para crescer)

Todos os componentes de `pipeline/` usam o **padrão de registro (registry)**: um decorador `@REGISTER_*` popula um dicionário global, e uma fábrica `get_*_class(name)` resolve o nome (vindo da config) para a classe. Exemplos: `capgenerator/base.py::REGISTER_CAPGEN` + `get_capgen_class`; idem para `DENOISER`, `PROPGEN`, `CONSTRUCTPIPE`, `RETRIEVEPIPE`.

**Implicação prática:** trocar um componente (ex.: escrever um novo denoiser) é registrar uma classe nova e mudar um parâmetro no `.sh` — sem tocar no orquestrador. **Porém**, todos compartilham o mesmo objeto `cfg` e o mesmo dicionário `models`, então extrair uma peça para fora do repositório significa carregar essas convenções junto. Peça mais portável isoladamente: a segmentação de Foote (§E), que só precisa de uma matriz de similaridade.

---

## 9. Roteiro de leitura sugerido (do overview à profundidade)

Ordem recomendada para sair deste mapa e entrar no detalhe técnico sem se perder:

1. **Config primeiro** — `config/cfg.py`. Conheça os botões e os nomes antes de ver o comportamento.
2. **Os dois `.sh`** — `scripts/construct.sh` e `retrieve.sh`. Veja quais botões o experimento default liga.
3. **Os dois `main`** — `construct.py` e `retrieve.py::start_inference`. Fixe o esqueleto de montagem.
4. **O orquestrador** — `constructpipe/base.py::construct`. Entenda a ordem e as dependências das etapas.
5. **Os componentes de construção, na ordem do pipeline** — `capgenerator/` → `sim_utils.py` → `denoiser/window.py` → `propgenerator/QMPropGener.py`. Aqui mora a maior parte da "novidade".
6. **O índice** — `treebuilder/capTree.py`. Como o texto vira algo pesquisável.
7. **A recuperação** — `retrievepipe/SentPipe.py` (mais simples) → `KeyPipe.py` → `MixPipe.py` (a fusão).
8. **A avaliação** — `standalone_eval/eval.py` e `utils/temporal_nms.py`. Só quando quiser entender como os números são produzidos.

---

## 10. Mapa de importância (o que é estrutural vs auxiliar)

- **Load-bearing (o método não existe sem):** orquestrador (§A), gerador de legendas (§B), sinal ITM (§C), segmentação (§E), índice (§F), fusão de recuperação (§G-Mix).
- **Diferencial/refino (candidatas a novidade, a confirmar no paper):** denoiser (§D), a ponderação `it` da segmentação (§E), a fusão dupla granularidade (§G).
- **Auxiliar (necessário para rodar/medir, mas não é o "método"):** avaliação (§H), NMS, `annos/` como manifesto e gabarito, caches em `meta/`.
- **Andaime de engenharia:** o padrão de registro (§8) e a config (§I) — importam para *estender*, não para *entender* o algoritmo.

---

### Próximo passo natural
Com este mapa fixado, o mergulho técnico pode atacar um componente por vez — a sugestão é começar pelos itens de "diferencial/refino" (§D e §E), que concentram o que o artigo provavelmente reivindica como contribuição. Quando o PDF chegar, cada afirmação de novidade aqui será cruzada com o texto e com as ablações.
