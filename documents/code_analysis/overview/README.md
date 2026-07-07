# RefCap — Guia de Arquitetura (Overview) · v2 (Reconciliado com o Paper)

> **Propósito deste documento.** Servir de mapa para navegar o repositório `BUAAPY/RefCap` antes do mergulho técnico função a função. Cada afirmação estrutural vem acompanhada do arquivo (e, quando útil, função/linha) que a comprova.
>
> **Mudança de escopo nesta versão.** A v1 foi escrita **exclusivamente do código**, com a ressalva de que "o artigo será reconciliado depois". Esta v2 faz essa reconciliação: o paper *RefCap* (ICASSP 2025) foi lido em profundidade e cruzado com cada afirmação. Os pontos onde o artigo **confirma**, **corrige** ou **enriquece** a leitura-só-do-código estão marcados com **▸ Reconciliação com o paper**.
>
> **Resultado de alto nível da reconciliação (leia primeiro).** A **arquitetura não mudou** — os fatos estruturais (fluxo, arquivos, acoplamentos, pontos de entrada, papel do `annos/`) foram inferidos corretamente do código e o paper os confirma. O que mudou foi a **interpretação**: o paper recalibra *o que é novidade, o que é emprestado e o que importa empiricamente*. Três correções materiais e três adições, consolidadas na §11.

---

## 1. A ideia central (em uma frase)

RefCap resolve **Video Corpus Moment Retrieval (VCMR)** — dado um texto de consulta e um *corpus* de vídeos não-recortados, localizar o par `(vídeo, intervalo [início, fim])` que corresponde à consulta — **sem treinar nada no dataset alvo**. A estratégia unificadora é **converter cada vídeo em uma estrutura puramente textual** (legendas densas refinadas + palavras-chave) e reduzir o problema a **recuperação texto-a-texto**, resolvida com modelos pré-treinados de prateleira (BLIP, sentence-transformers, GloVe).

Essa redução é o que torna o zero-shot viável: troca-se o problema difícil (alinhar pixels e texto) pelo problema resolvido (similaridade texto-texto).

> **▸ Reconciliação com o paper — CONFIRMA + ENRIQUECE.** O paper valida a formulação ("first zero-shot training-free VCMR system", "two decoupled stages") e adiciona duas dimensões que o código não podia revelar: **(a)** a *explicabilidade* como co-benefício estrutural — a representação do vídeo deixa de ser um embedding implícito opaco e vira legenda legível (contraste explícito com [2, 5]); **(b)** um dado empírico ausente do código: RefCap fica *comparável, na verdade abaixo* do melhor método fracamente-supervisionado (JSG) no **Charades**, mas **≈2× superior** no **ActivityNet** (vídeos longos, queries complexas — Tabelas I–II). A implicação arquitetural: *o método é mais eficaz em corpora longos e semanticamente ricos*.

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

> **▸ Reconciliação com o paper — CONFIRMA.** O desacoplamento é afirmado literalmente: *"two decoupled stages"* e *"The Construction Stage is conducted only once, ensuring the efficiency of the Retrieval Stage"* (Seção II-A). A inferência-só-do-código estava correta.

---

## 3. Mapa de diretórios

| Diretório / arquivo | Papel na arquitetura | Importância |
|---|---|---|
| `construct.py` | Ponto de entrada do Estágio 1. Monta e dispara o pipeline de construção. | Crítico |
| `retrieve.py` | Ponto de entrada do Estágio 2. Monta índice + dataset + pipeline e avalia. | Crítico |
| `scripts/construct.sh`, `scripts/retrieve.sh` | Superfície de controle: definem todos os hiperparâmetros e disparam os `.py`. | Crítico |
| `config/` | Definição declarativa de todos os argumentos (`cfg.py`) + parser (fork do HuggingFace). | Crítico |
| `pipeline/` | **Núcleo do método.** Contém os componentes plugáveis (ver §5). | Crítico |
| `dataset/` | Carregadores: `viddataset.py` (frames de vídeo) e `dataset.py` (consultas de teste). | Alto |
| `utils/` | Funções transversais: similaridades (`sim_utils.py`), NMS (`temporal_nms.py`), NLP (`tree_utils.py`), carregamento de modelos (`model_utils.py`), captioning MiniGPT externo. | Alto |
| `standalone_eval/` | Cálculo de métricas VCMR/VR (Recall@K em faixas de IoU). Derivado do protocolo TVR. | Alto (só avaliação) |
| `annos/{charades,activitynet}/vcmr.jsonl` | Duplo papel: **(a)** manifesto de quais vídeos indexar (só o campo `vid_name` na construção) e **(b)** consultas + gabarito para avaliação. **Não** é usado para "aprender". | Contextual |
| `meta/` (gerado) | Caches intermediários reutilizáveis: legendas, features, scores, pesos GloVe. | Gerado |
| `results/` (gerado) | Saídas por experimento: `construct/` (árvores, proposals) e `retrieve/` (métricas, predições). | Gerado |

> **▸ Reconciliação com o paper — CONFIRMA (com precisão terminológica).** A afirmação "o `annos/` não é usado para aprender" é validada: a alegação central do paper é escopada a **anotações de *treino*** ("without *training* on any annotation"; "despite not requiring *specific* annotations"). O paper *usa* o `annos/` na própria seção experimental — "3720/17505 moment-sentence pairs" — mas para **avaliar** (Recall/IoU), não para treinar. A distinção das três naturezas (manifesto N1 / consulta N2 / gabarito N3) que a análise-só-do-código estabeleceu é exatamente a que o paper pressupõe.

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

> **▸ Reconciliação com o paper — CONFIRMA (mapeia às três peças do pipeline de construção).** Os três componentes intercambiáveis correspondem exatamente aos três módulos do paper: `caption_generator` → o VLLM (BLIP/MiniGPT); `caption_denoiser` → **SWi-Den** (Eq. 2); `proposal_generator` → **QM-Gen** (Eq. 3–4). A fábrica-via-registry é engenharia; a decomposição conceitual é a do paper.

---

## 5. Componentes críticos (o coração da arquitetura)

| # | Componente | Arquivo / função-chave | O que é (papel) | Eq. no paper |
|---|---|---|---|---|
| A | **Orquestrador de construção** | `constructpipe/base.py::construct` (l. 67–90) | A espinha dorsal; encadeia as 7 etapas do Estágio 1. | — |
| B | **Gerador de legendas** | `capgenerator/BlipCapGener.py`; `capgenerator/base.py` | Transforma frames em texto (entrada de todo o resto). | $R_i = VLLM(V_i)$ |
| C | **Sinal de qualidade ITM** | `utils/sim_utils.py::get_caption_frame_sims` | O sinal reaproveitado que sustenta denoising e segmentação. | Eq. 1 |
| D | **Denoiser de legendas (SWi-Den)** | `denoiser/window.py::denoise_caption` (l. 20–35) | O "refino" (o *Refined* do título). | Eq. 2 |
| E | **Gerador de proposals (QM-Gen)** | `propgenerator/QMPropGener.py::generate_proposal` (l. 69) | Segmentação temporal sem treino (fronteiras de eventos). | Eq. 3–5 |
| F | **Índice em árvore** | `treebuilder/capTree.py::CapTree` | A estrutura pesquisável do corpus. | $P_i$ (Sec. II-A) |
| G | **Pipelines de recuperação** | `retrievepipe/{SentPipe,KeyPipe,MixPipe}.py` | O matching consulta↔índice em tempo de query. | Eq. 6–10 |
| H | **Avaliação** | `standalone_eval/eval.py::eval_by_task_type` | Mede desempenho (Recall@K, IoU). | Sec. III |
| I | **Configuração** | `config/cfg.py` | A superfície declarativa de controle. | — |

### A — Orquestrador de construção · *espinha dorsal*
`constructpipe/base.py::construct()` (linhas 67–90) define a **ordem canônica e as dependências entre etapas**: gera legendas → computa features → computa scores brutos → **denoise** → **recomputa scores nas legendas denoised** → gera proposals → monta árvore. Note que os scores são computados **duas vezes** (l. 76 e l. 83): antes e depois do denoising — o denoising altera as legendas, então os scores precisam ser refeitos.

Aqui também mora o uso do `annos/`: `select_videos` (l. 184) lê **apenas** `data['vid_name']` (l. 191) — na construção, o arquivo de anotação funciona só como **lista de vídeos a processar**, nunca como rótulo.

> **▸ Reconciliação com o paper — CONFIRMA.** A sequência bate com a ordem do paper (SWi-Den → QM-Gen → Keyword Sets, Seção II-B). A recomputação dupla de scores é consequência direta: a *Quality-Mask* do QM-Gen (Eq. 4) usa $Q(\hat R_i)$, os scores das legendas **já denoised** — logo eles precisam ser recalculados após o SWi-Den. A instrumentação da prova de não-necessidade do `annos/` confirmou empiricamente que este é o único ponto de leitura do arquivo na construção.

### B — Gerador de legendas · *transformação de entrada*
Tudo no sistema é derivado das legendas por frame. Duas implementações sob uma interface comum:
- **BLIP** (`BlipCapGener.py::generate_caption`): legenda cada frame com `blip-image-captioning-large`, prompt `"a photo of"` removido depois.
- **MiniGPT-4-v2** (`utils/genCaptions_minigpt.py`): script **externo**; `base.py::BaseCapGen.generate_caption` impõe `assert video_name in self.already_video_names`, evidenciando que as legendas do MiniGPT são geradas antes, à parte. Prompt: `'Please describe this image with at most 30 words'`.

**Ponto arquitetural chave:** o captioning é **genérico e agnóstico à consulta** — legenda-se o vídeo sem saber o que será perguntado. É isso que permite um índice reutilizável.

> **▸ Reconciliação com o paper — CONFIRMA + ENRIQUECE.** Formalizado como $R_i = VLLM(V_i) = \{r_1^i,...,r_{L_i}^i\}$ (Seção II-A), sem dependência da query — exatamente o "agnóstico à consulta" inferido. O paper adiciona uma observação empírica: *o sistema com MiniGPT supera o com BLIP porque as legendas do MiniGPT são mais longas e detalhadas* (Seção III-B). Ou seja, **a qualidade do captioning é o gargalo dominante** — o que valida a ênfase do overview em que "se as legendas forem ruins, todo o resto degrada".

### C — Sinal de qualidade ITM · *o backbone reaproveitado*
`utils/sim_utils.py::get_caption_frame_sims` computa, via BLIP-ITM, a **similaridade entre cada legenda e o seu próprio frame** — um *proxy de confiabilidade* reutilizado em dois lugares: (1) o denoiser decide o que sobrescrever com base nele (§D); (2) a variante `it` da segmentação pondera a matriz por ele (§E). É o **único ponto onde o sinal visual entra na parte "textual" do método**, e o maior acoplamento ao BLIP (acessa `.vision_model`, `.vision_proj`, `.text_proj`).

> **▸ Reconciliação com o paper — CONFIRMA + ADICIONA UMA RESSALVA EMPÍRICA IMPORTANTE.** É a **Eq. 1**: $Q(r_l^i) = \langle E_v(f_l^i), E_t(r_l^i)\rangle$ — literalmente o único lugar onde $E_v$ (encoder visual) aparece. A estrutura estava correta. **Porém**, a ablação (Tabela III) revela uma sutileza que só ela expõe: o QM-Gen com features **textuais** supera o com features **visuais** (Vis 13,74 → Txt 16,69, **+2,95** em IoU=0,5). Isso significa que o caminho *visual → ITM → Quality-Mask* contribui **empiricamente pouco** comparado ao caminho puramente textual. O sinal visual é *estruturalmente* central (o único ponto de entrada visual) mas *empiricamente* secundário — uma dissociação que a leitura-só-do-código não podia antecipar.

### D — Denoiser de legendas (SWi-Den) · *o refino*
`denoiser/window.py::denoise_caption` (l. 20–35) implementa a **propagação temporal de legendas confiáveis**: se o score ITM ultrapassa `figsim_denoise_thr`, o frame vira âncora; se um frame tem score baixo e está dentro de `denoise_window_width` da última âncora, sua legenda é **substituída** por uma cópia da âncora. Materializa o "*Refined*" do título. Há um `BaseDenoiser` (`denoiser/base.py`) que não faz nada (`return meta`), usado como *baseline* de ablação.

> **▸ Reconciliação com o paper — CORREÇÃO MATERIAL (recalibração de novidade) + um achado de implementação.** É a **Eq. 2**. A v1 listou o denoiser como "candidato a novidade" (§10). O paper **obriga a rebaixá-lo**: a ablação (Tabela III) mostra que adicionar SWi-Den ao texto rende **+0,27** (16,69 → 16,96 em IoU=0,5) — **impacto empírico quase nulo**. É a novidade nominal de menor retorno do trabalho, e o próprio paper o descreve como "inspirado em técnicas tradicionais de filtragem". *Reclassificação:* de "candidato a novidade" para **"novidade nominal com retorno empírico marginal"**. Além disso, a dissecação com testes revelou um **defeito de implementação não descrito no paper**: `last_high_id` é inicializado como a string `'0'`, que colide com o id do frame 0 — quando a âncora é o frame 0, o denoising é silenciosamente pulado, contrariando a Eq. 2 (que não tem exceção para o frame 0).

### E — Gerador de proposals (QM-Gen) · *segmentação temporal*
`propgenerator/QMPropGener.py::generate_proposal` (l. 69) fatia o vídeo em eventos, sem treino:
- **Matriz de similaridade** (`calculate_similarities`, l. 28): três modos — `txt`, `it` (padrão, legendas × score ITM), `vis`.
- **Detecção de fronteiras por novidade** (l. 74–88): *kernel checkerboard* (quadrantes +1/−1), convolução, diagonal como score de novidade por frame.

Cada segmento recebe uma **legenda representativa** (frame de maior score) e **palavras-chave** (substantivos+verbos de todas as legendas do trecho, `tree_utils.py::get_nouns_verbs`).

> **▸ Reconciliação com o paper — CONFIRMA A SUSPEITA DA FONTE + ELEVA O INSIGHT TEXTUAL AO CENTRO.** A v1 suspeitou: "é o clássico kernel de novidade de Foote; o *potencialmente* próprio é aplicá-lo a uma matriz derivada de legendas". O paper **confirma e nomeia**: o *contrastive kernel* é explicitamente emprestado do **UBoCo [12]** (Kang et al., CVPR 2022). As **duas deltas genuínas** sobre o UBoCo são: **(a)** usar features de *texto* em vez de visuais (Eq. 3, $M_s^i = E_t(\hat R_i)E_t^T(\hat R_i)$) e **(b)** a *Quality-Mask* (Eq. 4, $M_q^i = Q(\hat R_i)Q^T(\hat R_i)$; $\tilde M_s^i = M_s^i \odot M_q^i$). E o mais importante: a escolha textual — que a v1 tratou como "um dos três modos de config" — é na verdade **o insight empírico mais forte do paper** (+2,95 na ablação, o maior delta). *Reclassificação:* a variante `it`/`txt` do QM-Gen sobe de "parâmetro" para **"a substância central do trabalho"**. Ressalva empírica adicional: o QM-Gen isolado *ajuda* em IoU=0,5 (+1,29) mas *piora* em IoU=0,7 (8,55 → 8,01) — só recupera *combinado* com o SWi-Den, uma interação que o paper não comenta.

### F — Índice em árvore · *a estrutura pesquisável*
`treebuilder/capTree.py::CapTree` transforma os proposals num índice consultável. `build_relations` "achata" todos os proposals em listas paralelas (`caps`, `keys`) com mapeamentos de volta aos nós; `compute_tree_feature` codifica legendas (sentence-transformer) e keywords (GloVe). **Observação estrutural:** apesar do nome "árvore" e do BFS suportar profundidade arbitrária, a árvore construída em `build_tree_meta` tem **só 2 níveis** (vídeo → proposals) — na prática, um índice plano.

> **▸ Reconciliação com o paper — CORREÇÃO MATERIAL (a "árvore" é ainda mais oversell do que a v1 admitiu).** A v1 disse "na prática um índice plano de 2 níveis". O paper vai além e **dissolve o conceito de árvore**: a notação formal (Seção II-A) define, por vídeo, um **conjunto plano** $P_i = \{p_1^i, ..., p_{H_i}^i\}$, cada proposal uma tupla $(s_h^i, e_h^i, c_h^i, K_h^i)$. **Não há árvore na formulação matemática** — é uma lista de eventos por vídeo. O nome `CapTree`/`treebuilder` é *vocabulário vestigial sem correspondente conceitual*, não a simplificação de uma hierarquia pretendida. Consequência prática para extração: você pode tratar o índice como uma **tabela plana** `(vídeo, evento) → (legenda, keywords, embeddings)` sem perder nada.

### G — Pipelines de recuperação · *o matching em tempo de query*
Três estratégias sob a mesma interface (`base.py::BaseRetrievePipe`):
- **`SentPipe`** — só nível-sentença (cosseno consulta↔legendas).
- **`KeyPipe`** — só nível-palavra (GloVe, agregação "max sobre keys do proposal → média/max sobre keys da consulta").
- **`MixPipe`** (padrão) — **fusão tardia**: `esm_sims = sent·ratio + key·(1−ratio)` (`MixPipe.py`, l. 130/135). A candidata a novidade de recuperação.

Resultado: os `max_vcmr_props` (1000) melhores proposals por consulta (`torch.topk`).

> **▸ Reconciliação com o paper — CONFIRMA + SITUA NA LINHAGEM.** Mapeamento direto: `SentPipe` → Eq. 6; `KeyPipe` → Eq. 7–8 (o `Max_Mean` é enquadrado como *Multiple Instance Learning* [16]); `MixPipe` → Eq. 9 ($S = \alpha S_s + (1-\alpha)S_w$, VCMR) e Eq. 10 (VR). A ablação confirma: a fusão ajuda (**+2,13** sobre sentença-só) e **`Max_Mean > Max_Max`** (+1,19). *Ponto de linhagem que a v1 não tinha:* o principal baseline, **JSG [5], já é "multi-granularity"** ("Joint searching and grounding: **Multi-granularity** video content retrieval") — logo a "busca multi-granularidade" de RefCap **transpõe** para o regime training-free uma filosofia já presente no SOTA fraco-supervisionado; a novidade é a transposição, não o conceito. Escolha datada confirmada: **GloVe** (não-contextual) é um teto de desempenho.

### H — Avaliação · *a régua*
`standalone_eval/eval.py::eval_by_task_type` computa Recall@{1,10,100} em faixas de IoU. Um momento é positivo só se **(1)** o `vid_name` bate com o gabarito **e (2)** o IoU supera o limiar (l. 85–87). Antes, `retrieve.py::eval_epoch` aplica **NMS temporal**. Este bloco é **só medição** — não é o método, e é o que você contorna num modo de produção.

> **▸ Reconciliação com o paper — CONFIRMA.** As métricas (Recall@K, IoU=m para event-level; Recall@K para video-level) e a regra de acerto batem com a Seção III-A. O bloco de avaliação consome o gabarito `ts` — que a prova instrumentada mostrou ser **inerte ao scoring** (é apenas ecoado na saída como `gt_ts`), reforçando que é medição, não método.

### I — Configuração · *a superfície de controle*
`config/cfg.py` define tudo em três dataclasses: `BasicArguments`, `BuildArguments`, `TestArguments`. Ler as três é a forma mais rápida de descobrir todos os botões e seus defaults.

---

## 6. Superfície de controle (os botões que importam)

**Construção (`construct.sh`):** `collection`, `caption_generator` (§B), `caption_denoiser` (§D), `figsim_denoise_thr`/`denoise_window_width` (§D), `prop_sim_type` (§E), `prop_score_thr`/`prop_kernel_width`/`prop_min_cnt`/`prop_max_cnt` (§E).

**Recuperação (`retrieve.sh`):** `construct_name`, `retrieve_pipeline` (§G), `key_policy` (§G), `retrieve_sent_ratio` (§G), `max_vcmr_props`.

> **▸ Reconciliação com o paper — O ALERTA DA v1 VIROU DEFEITO CONFIRMADO.** A v1 marcou: "verificar no artigo se os limiares (0,4/0,2/0,5) foram tunados em dados rotulados — tuning no teste seria supervisão indireta". **Veredito após ler o paper:** ele fixa $\theta_d{=}0{,}4$, $\theta_b{=}0{,}2$, $\alpha{=}0{,}5$, $W{=}2s$ (Seção III-A) **sem declarar qualquer conjunto de validação**. O alerta deixa de ser hipótese e vira a **única fissura metodológica séria** da alegação "zero-shot/annotation-free": se esses valores foram escolhidos no teste rotulado, há vazamento *indireto* de supervisão via calibração. Não quebra "training-free" (não há treino por gradiente), mas relativiza "annotation-free". *Implicação para extração:* você herda esses defaults sem garantia de que transferem para o seu domínio, e sem rótulos seus não há como re-tunar.

---

## 7. Artefatos de dados produzidos (onde as coisas caem)

```
meta/                                    (cache — computado 1x por collection+caption_generator)
├── captions/{collection}_{gen}.jsonl    legendas por frame            (§B)
├── framefeatures/{collection}.pt        features visuais BLIP         (§C)
├── scores/{collection}_{gen}.pt         scores legenda-frame brutos   (§C)
└── glove.6B/glove.6B.300d.txt           pesos GloVe (pré-requisito externo)

results/construct/{collection}/{construct_name}/   (por construção)
├── settings.json · denoised_captions.jsonl (§D) · denoised_capframe_scores.pt (§C/§D)
├── prop_sims.pt (§E) · proposals.json (§E)
└── tree.json                            ◄── O ÍNDICE (interface p/ §2)

results/retrieve/{collection}/{retrieve_name}/     (por recuperação)
├── build_settings.json / eval_settings.json · metrics.json (§H) · vcmr_preds.json
```

O cache em `meta/` permite reexecução barata: legendas, features e scores brutos só são computados na primeira vez (guardas `if os.path.exists(...)`).

> **▸ Reconciliação com o paper — SEM MUDANÇA.** Estrutural; o paper não contradiz nem detalha o layout de disco. O `denoised_captions.jsonl` é o artefato onde a Fig. 2 do paper (visualização das legendas densas) se materializa — útil para o diagnóstico qualitativo de domínio.

---

## 8. O padrão de extensibilidade (como o código foi feito para crescer)

Todos os componentes de `pipeline/` usam o **padrão de registro (registry)**: `@REGISTER_*` popula um dicionário global, `get_*_class(name)` resolve o nome (da config) para a classe. Trocar um componente é registrar uma classe nova e mudar um parâmetro no `.sh` — sem tocar no orquestrador. **Porém**, todos compartilham o mesmo `cfg` e o mesmo dicionário `models`, então extrair uma peça para fora significa carregar essas convenções junto. Peça mais portável isoladamente: a segmentação de Foote (§E).

> **▸ Reconciliação com o paper — REFORÇA A PORTABILIDADE.** Agora que o paper confirma que o kernel de fronteiras é o do UBoCo [12] (técnica conhecida e autônoma), a §E é *ainda mais claramente* a peça mais reutilizável: é um algoritmo de detecção de novidade sobre uma SSM qualquer, com genealogia pública, não uma invenção acoplada ao RefCap.

---

## 9. Roteiro de leitura sugerido (do overview à profundidade)

1. **Config** — `config/cfg.py`. Os botões e nomes.
2. **Os dois `.sh`** — quais botões o experimento default liga.
3. **Os dois `main`** — `construct.py` e `retrieve.py::start_inference`. O esqueleto de montagem.
4. **O orquestrador** — `constructpipe/base.py::construct`. A ordem e as dependências.
5. **Os componentes de construção, na ordem do pipeline** — `capgenerator/` → `sim_utils.py` → `denoiser/window.py` → `propgenerator/QMPropGener.py`. Aqui mora a substância.
6. **O índice** — `treebuilder/capTree.py`.
7. **A recuperação** — `SentPipe.py` → `KeyPipe.py` → `MixPipe.py`.
8. **A avaliação** — `standalone_eval/eval.py` e `utils/temporal_nms.py`.

> **▸ Reconciliação com o paper — ADICIONA O MAPA EQUAÇÃO↔CÓDIGO.** Com o paper em mãos, o mergulho técnico ganha um cruzamento direto: Eq. 1 ↔ `sim_utils.py::get_caption_frame_sims`; Eq. 2 ↔ `denoiser/window.py::denoise_caption`; Eq. 3–4 ↔ `QMPropGener.py::generate_proposal` (matriz + Quality-Mask); Eq. 5 ↔ `get_nouns_verbs`; Eq. 6–10 ↔ `retrievepipe/`. **Ponto de atenção para a fase técnica:** a implementação *detalha o que o paper abstrai* — ex., a normalização min-max dos quality scores (em `sim_utils.py`) não aparece nas equações; e o bug de colisão de sentinela do §D não está no paper. Cruzar equação↔código é onde esses gaps aparecem.

---

## 10. Mapa de importância (o que é estrutural vs auxiliar) · **revisado pela ablação**

> **▸ Esta seção foi materialmente recalibrada pela Tabela III do paper.** A v1 classificava por *estrutura*; a v2 classifica por *estrutura + impacto empírico*.

- **Load-bearing (o método não existe sem):** orquestrador (§A), gerador de legendas (§B), sinal ITM (§C), segmentação (§E), índice (§F), fusão de recuperação (§G-Mix). *(Inalterado — confirmado.)*
- **Onde mora a substância empírica (recalibrado):** **a escolha de features textuais no QM-Gen (§E)** — o maior delta da ablação (+2,95, "texto > visual"); e a **fusão dupla-granularidade (§G)** (+2,13, com `Max_Mean > Max_Max`). *Estes são o valor real.*
- **Novidade nominal de retorno marginal (rebaixado da v1):** **o denoiser SWi-Den (§D)** — +0,27 na ablação. *Era "candidato a novidade"; agora é o primeiro candidato a **descarte** se você precisar simplificar o sistema.*
- **Emprestado, não novo (confirmado pelo paper):** o **kernel de fronteiras (§E)** — do UBoCo [12]; a **filosofia multi-granularidade (§G)** — já no baseline JSG [5].
- **Auxiliar (necessário para rodar/medir, não é o "método"):** avaliação (§H), NMS, `annos/` como manifesto e gabarito, caches em `meta/`.
- **Andaime de engenharia:** o registry (§8) e a config (§I).

---

## 11. Reconciliação código↔paper — o balanço consolidado

O que a leitura do paper mudou (e não mudou) em relação à v1, em uma tabela.

| Item | Status | O que muda | Referência no paper |
|---|---|---|---|
| Dois estágios desacoplados por disco | ✅ Confirmado | nada | Sec. II-A |
| Captioning agnóstico à consulta | ✅ Confirmado | nada | $R_i = VLLM(V_i)$ |
| Sinal ITM é o único ponto visual | ✅ Confirmado | nada | Eq. 1 |
| `annos/` = manifesto + gabarito, não treino | ✅ Confirmado | precisão: "sem anotação" = de *treino* | Sec. III-A |
| **Denoiser (SWi-Den) é candidato a novidade** | ⚠️ **Corrigido** | rebaixado a **retorno empírico marginal** (+0,27); 1º candidato a descarte | Tab. III |
| **Kernel de fronteiras é "potencialmente próprio"** | ⚠️ **Corrigido** | confirmado **emprestado do UBoCo [12]** | Sec. II-B-2, [12] |
| **Hiperparâmetros: possível tuning no teste?** | ⚠️ **Corrigido** | **gap confirmado** — sem protocolo de validação declarado | Sec. III-A |
| A "árvore" é um índice plano | ⚠️ **Reforçado** | não há árvore na formulação; é um **conjunto plano** $P_i$ | Sec. II-A |
| Insight "texto > visual" na segmentação | ➕ **Adicionado** | é o **maior delta empírico** (+2,95), não "um parâmetro" | Fig. 1b, Tab. III |
| Assimetria Charades vs ActivityNet | ➕ **Adicionado** | ≈2× superior no ActivityNet; *onde o método brilha* | Tab. I–II |
| Linhagem (UBoCo, JSG, Cap4Video) | ➕ **Adicionado** | situa os componentes numa genealogia | [5, 8, 9, 12] |

**Conclusão de uma linha:** *a arquitetura descrita na v1 estava correta; o paper recalibrou o que vale.* As três correções convergem para a mesma tese prática: **a novidade transferível está no paradigma (VCMR sem-rótulo via texto) e em um insight (texto > visual para fronteiras) — não nos módulos individuais**, que são recombinações competentes de peças conhecidas, com um deles (o denoiser) rendendo quase nada.

---

### Próximo passo natural
Com o Overview reconciliado, o mergulho técnico ganha foco cirúrgico: comece por **§E (QM-Gen)**, onde mora a substância (a escolha textual + a Quality-Mask), usando o mapa equação↔código da §9 para cruzar Eq. 3–4 com `generate_proposal` linha a linha — e atento aos gaps onde a implementação detalha o que o paper abstrai (a normalização min-max) ou diverge dele (o bug de colisão de sentinela do §D). O §D (SWi-Den), por render pouco empiricamente, pode ser lido por completude, não como prioridade.
