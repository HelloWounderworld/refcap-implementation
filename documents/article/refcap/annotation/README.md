# RefCap — Relatório Técnico Consolidado
## Análise Integral do Artigo e do Código + Playbook de Extração de Funcionalidades

---

> **O que é este documento.** A consolidação de toda a análise minuciosa feita sobre o artigo *RefCap* (ICASSP 2025) e sobre o código do repositório `BUAAPY/RefCap`, convertida em um **guia acionável** para extrair as funcionalidades do sistema — busca de momentos em vídeo por prompt textual (VCMR) — e aplicá-las a um acervo de vídeos brutos, sem anotações.
>
> **Como usar.** As Partes I–IV entregam o *entendimento* (viabilidade, novidade, arquitetura, a questão das anotações). A **Parte V é o playbook de extração** (o que mudar, onde, e por quê). A Parte VI isola os riscos que sobrevivem à extração. A Parte VII prepara a fase seguinte — análise fina e testes. O Apêndice é um índice de referência rápida (arquivo → função → linha).
>
> **Escopo e método.** Análise derivada da leitura direta do código (clonado e dissecado) e do texto do artigo, com cada afirmação ancorada em evidência (arquivo/função/linha ou tabela/equação). Postura crítica deliberada: separar novidade real de recombinação, expor pressupostos ocultos, quantificar trade-offs e apontar defeitos.

---

## PARTE I — Síntese executiva e veredito de viabilidade

**Viabilidade: SIM, com escopo preciso.** A funcionalidade que você quer — jogar um prompt ("um ser humano abrindo a porta") e receber uma lista ranqueada de momentos de vídeo — **é exatamente o que o núcleo do RefCap entrega, e ela roda sobre vídeo bruto sem um único rótulo**. Está confirmado no código: nenhum componente do método (captioning, denoising, segmentação, indexação, matching) consome anotação. O diretório `annos/` é **encanamento operacional + avaliação**, não requisito metodológico.

**A ressalva que define o trabalho real.** "Remover o `annos/`" não é apagar a pasta e rodar. O repositório *como escrito* abre o `annos/` nos dois estágios e quebra sem ele. A extração exige **duas cirurgias de dificuldade muito diferente** (Parte V) e o contorno de **um acoplamento não-óbvio** que, se ignorado, faz seu corpus de busca encolher silenciosamente.

**O balanço da extração:**

| Você mantém | Você abre mão |
|---|---|
| Todo o núcleo estado-da-arte: captioning refinado (SWi-Den), geração de eventos (QM-Gen), *Indexing Keyword Sets*, busca multi-granularidade. Roda sobre vídeo bruto, zero rótulos. | A capacidade de **medir** qualidade (Recall/IoU exige gabarito) e de **re-calibrar** hiperparâmetros. Não é limitação do RefCap — é lógica: sem gabarito não há como quantificar acerto. |

**O gargalo real não é a anotação.** É a adequação do VLLM (BLIP/MiniGPT) ao *seu* domínio de vídeo. Se seus vídeos são de um domínio onde esses modelos legendam mal, a premissa "vídeo bruto basta" enfraquece — não por causa do `annos/`, mas por causa do captioning (Parte VI).

---

## PARTE II — O que o artigo propõe: tese e novidade calibrada

### II.1 A tese central (a estrutura argumentativa em três atos)

1. **Diagnóstico.** VCMR sempre foi resolvido por métodos supervisionados ou fracamente-supervisionados, com dois pecados: dependem de anotações trabalhosas e representam o vídeo por *embeddings implícitos* — opacos, sem explicabilidade.
2. **A virada.** VLLMs já descrevem imagens; então **converta o vídeo em texto legível** e reduza VCMR a busca texto-a-texto. A objeção (legendas têm ruído) é o que o paper explora: trabalhos anteriores usavam legendas *indiretamente* (pseudo-rótulos, aumento de features) por medo do ruído; RefCap as usa **diretamente**, com módulos para limpar o ruído antes de indexar.
3. **O payoff.** Obtêm-se **simultaneamente** duas propriedades antes em tensão: **treino/anotação-zero** e **explicabilidade** (a representação do vídeo vira uma frase legível). O nome condensa a aposta: **Ref**Cap = *Refined Captioning* — o gargalo do paradigma é a qualidade da legenda, e refiná-la é o que torna a busca viável.

### II.2 As quatro contribuições — novidade real vs. recombinação

| # | Contribuição declarada | Novidade | Emprestado de | Delta genuíno | Impacto empírico |
|---|---|---|---|---|---|
| C1 | Primeiro VCMR zero-shot / training-free | **Alta (conceitual)** | — | O paradigma + uso *direto* das legendas em nível de corpus | É a tese; sustenta tudo |
| C2 | SWi-Den + QM-Gen | Baixa–Média | Kernel contrastivo do **UBoCo [12]** | SSM *textual* (não visual) + *Quality-Mask* | QM-Gen: moderado; SWi-Den: quase nulo |
| C3 | Indexing Keyword Sets + retrieval multi-granularidade | Média | Fusão híbrida da IR; multi-granularidade já no baseline **JSG [5]** | Agregação `Max_Mean` sobre keyword sets GloVe | Fusão ajuda; `Max_Mean > Max_Max` |
| C4 | Experimentos em 2 datasets | N/A (validação) | — | — | Ver II.3 |

**Leitura crítica da novidade.** A contribuição de nível-paradigma (C1) é o verdadeiro título e é sólida. C2–C3 são **recombinações competentes** de técnicas conhecidas: o kernel de detecção de fronteiras é *explicitamente* do UBoCo (o paper cita); a busca multi-granularidade já era a filosofia do JSG, o próprio baseline. O SWi-Den é, na prática, um filtro causal "segura-último-valor-bom" com gate de qualidade. **Alerta de enquadramento:** chamar SWi-Den *e* QM-Gen de "dois módulos de *denoising*" é impreciso — QM-Gen é um gerador de eventos, não um denoiser.

### II.3 A evidência empírica lida criticamente

- **Assimetria Charades vs ActivityNet (o achado mais informativo).** No Charades, o JSG **vence a maioria das colunas** — a afirmação "comparable ... on Charades" é *generosa frente à própria Tabela I* (leitura precisa: "abaixo, porém na vizinhança"). No ActivityNet, RefCap(M) **domina** (≈2× o JSG em IoU=0.5 R@10: 11.47 vs 5.81). **Implicação:** a vantagem cresce com a duração e a complexidade do acervo.
- **Ablação (Tab. III, só Charades) desmonta a hierarquia retórica.** Texto ≫ visual (+2.95, o maior sinal). SWi-Den isolado: quase nulo (+0.27). QM-Gen isolado: moderado (+1.29) mas **piora a localização fina** (IoU=0.7: 8.55→8.01); só recupera *combinado* com SWi-Den — interação não comentada no paper. Na busca: fusão ajuda (+2.13 sobre sentença), e `Max_Mean > Max_Max` (+1.19).
- **Números absolutos baixos.** O momento certo aparece no top-10 em ~4–11% das consultas nos benchmarks. **Não é crítica ao RefCap** (baselines iguais ou piores; a tarefa é dura), mas define o regime: **protótipo de pesquisa competitivo, não motor de busca de produção**.

### II.4 Pressupostos ocultos e defeitos de enquadramento

1. **"Zero-shot" ≠ "sem componentes aprendidos".** Significa "sem treino *específico da tarefa*"; o motor inteiro são VLLMs pré-treinados.
2. **Ausência de protocolo de hiperparâmetros.** θd=0.4, θb=0.2, α=0.5, W=2s fixados **sem split de validação declarado**. Se escolhidos no teste, há vazamento *indireto* de supervisão pela via da calibração — não quebra "training-free", mas relativiza "annotation-free". **É a única lacuna metodológica séria da alegação central.**
3. **Comparação só contra fracamente-supervisionado** (não contra totalmente-supervisionado nem baselines VLLM modernos).
4. **Ablação só no dataset mais fraco** (Charades); não sabemos se as conclusões transferem para o ActivityNet.
5. **Silêncio sobre custo/latência/escalabilidade** da construção — dado crítico para deployment.

---

## PARTE III — A arquitetura do sistema (mapa técnico)

### III.1 Dois estágios desacoplados por disco

A única interface entre os estágios é o arquivo `tree.json`. Isto é o alicerce da viabilidade: a indexação (cara, offline) roda uma vez, sem rótulos; a recuperação (barata, online) reusa o índice para qualquer consulta.

```
CONSTRUÇÃO (offline, 1x)                    RECUPERAÇÃO (online, por consulta)
 vídeos brutos                               consulta textual (prompt do usuário)
   │                                            │
   ▼ [1] frames 1fps  (viddataset.py)           ▼ carrega índice (capTree.py)
   ▼ [2] captioning   (capgenerator/)           ▼ codifica consulta + similaridade
   ▼ [3] features     (sim_utils.py)            ▼ (retrievepipe/: sent|key|mix)
   ▼ [4] score ITM    (sim_utils.py)            ▼ top-1000 momentos
   ▼ [5] denoising    (denoiser/window.py)      ▼ NMS temporal (temporal_nms.py)
   ▼ [6] segmentação  (propgenerator/)          ▼ [avaliação — opcional, exige gabarito]
   ▼ [7] árvore ───► tree.json ────────────────►(interface)
        (constructpipe/base.py:181)
```

### III.2 Componentes críticos (com âncoras de código)

| Componente | Arquivo · função · linha | Papel |
|---|---|---|
| Orquestrador de construção | `constructpipe/base.py::construct` (l. 67–90) | Espinha dorsal; encadeia as 7 etapas |
| Gerador de legendas | `capgenerator/BlipCapGener.py` | Transforma frames em texto (entrada de tudo) |
| Sinal de qualidade ITM | `utils/sim_utils.py::get_caption_frame_sims` (l. 78) | Proxy de confiabilidade; reaproveitado em §5 e §6 |
| Denoiser (SWi-Den) | `denoiser/window.py::denoise_caption` (l. 20–34) | Propaga legendas confiáveis (o "refino") |
| Gerador de eventos (QM-Gen) | `propgenerator/QMPropGener.py::generate_proposal` (l. 69) | Segmentação temporal por novidade |
| Índice em árvore | `treebuilder/capTree.py::CapTree` (l. 14) | Estrutura pesquisável do corpus |
| Pipelines de busca | `retrievepipe/{SentPipe,KeyPipe,MixPipe}.py` | Matching consulta↔índice |
| Avaliação | `standalone_eval/eval.py::eval_by_task_type` (l. 82) | Mede desempenho (Recall/IoU) — só medição |

### III.3 Correspondência artigo ↔ código (as equações confirmadas)

- **Eq. 1 (Quality Score)** = `get_caption_frame_sims` (`sim_utils.py:78`): produto interno legenda-frame do BLIP, seguido de `normalize_min_max` (`sim_utils.py:30`) — *a normalização min-max está no código mas não nas equações*.
- **Eq. 2 (SWi-Den)** = `denoise_caption` (`window.py:20`): `last_high_id` (l. 27), gate `> figsim_denoise_thr` (l. 30), substituição via `deepcopy` dentro da janela `denoise_window_width` (l. 33–34). **Confirmado: propagação apenas causal (para frente), a partir da âncora anterior.**
- **Eq. 3–4 (QM-Gen)** = matriz de similaridade `it` + kernel contrastivo (`QMPropGener.py:74–87`): kernel checkerboard (quadrantes ±1, cruz central 0), `conv2d` + `diagonal`. A *Quality-Mask* é o produto externo dos quality scores (modo `it`).
- **Eq. 5 (Indexing Keyword Set)** = `get_nouns_verbs` sobre as legendas do segmento (`QMPropGener.py:136`).
- **Eq. 6–10 (retrieval)** = `MixPipe.py`: `Max_Mean`, fusão `α·sent + (1−α)·key`.

---

## PARTE IV — A questão das anotações (resolvida)

### IV.1 As três naturezas dentro de `annos/vcmr.jsonl`

Cada linha é uma **consulta** com cinco campos. O erro conceitual é tratá-los como um bloco único. São três naturezas epistemicamente distintas:

- **N1 — Manifesto do corpus** (`vid_name`): diz *quais vídeos existem*. Catálogo, não rótulo.
- **N2 — Consulta** (`desc`): a *entrada* do usuário. Não é anotação *do vídeo*; é o pedido *sobre* ele.
- **N3 — Gabarito/supervisão** (`ts`): a resposta correta. Único campo que é "anotação" no sentido de rótulo supervisionado.

### IV.2 O que o código realmente consome (evidência)

| Ponto de uso | Arquivo · linha | Campos lidos | Natureza |
|---|---|---|---|
| `select_videos` | `constructpipe/base.py:184` | **só `vid_name`** | N1 (manifesto) |
| Script MiniGPT | `utils/genCaptions_minigpt.py:203` | **só `vid_name`** | N1 (manifesto) |
| `DataSet4Test` | `dataset/dataset.py` | `desc`, `vid_name`, `ts` | N2 + N3 |
| Avaliação | `standalone_eval/eval.py:154` | `ts` | N3 (só medir) |

**Fato decisivo, confirmado no código:** mesmo na recuperação, o gabarito `ts` é **inerte ao scoring** — em `MixPipe.py` ele só é desempacotado (l. 61) e copiado para a saída como `gt_ts` (l. 160), enquanto o `topk` (l. 139) decide os momentos apenas por similaridade texto-a-texto. **O método jamais consome a supervisão.**

### IV.3 O que o artigo afirma (escopo preciso)

O artigo **não** afirma isenção total de anotações. Afirma, cuidadosamente escopado, isenção de anotações **de treino**. As frases-chave: "first zero-shot **training-free** VCMR system"; "Without **training on** any annotation"; "despite not requiring **specific** annotations". A palavra "**specific**" (específicas = da tarefa) é o reconhecimento tácito de que *outras* anotações estão presentes — e estão: o próprio paper usa "3720/17505 moment-sentence pairs" para **avaliar**. A alegação técnica (não treina em rótulos) é verdadeira; a *impressão* de "dispensa anotações" é falsa. **Não confunda a manchete com a alegação.**

### IV.4 Necessidade — dois sentidos

- **Necessidade operacional** (o código roda sem `annos/`?): **Não** — quebra em `open(anno_path)` na construção e em `DataSet4Test` na recuperação. É encanamento.
- **Necessidade metodológica** (o núcleo precisa da *informação* dele?): **Não** — N1 é substituível por listagem de diretório; N2 vem do usuário em produção; N3 nunca é usada pelo método. A única "necessidade" que sobra é a trivial de *qualquer* motor de busca: um corpus a indexar e uma consulta a atender.

**Conclusão:** `annos/` **não é condição necessária** para a funcionalidade-núcleo. É necessário apenas para (i) o repositório rodar sem edição e (ii) a avaliação em benchmark ser computável.

---

## PARTE V — PLAYBOOK DE EXTRAÇÃO (o núcleo acionável)

### V.1 O que você recebe (confirme que casa com seu objetivo)

A saída da recuperação (`vcmr_res_dict`, construída em `MixPipe.py:145–162`) é, **por consulta**, uma lista ranqueada:

```
predictions = [ [vid_id, início, fim, score, nome_do_vídeo, legenda_do_evento], ... ]
               (top-1000 antes do NMS; top-100 depois)
```

É precisamente um resultado de busca de vídeo — e ainda inclui a **legenda que explica** por que o trecho foi retornado (a explicabilidade do paper). Confirma: a funcionalidade-alvo está no núcleo e não precisa de rótulo.

### V.2 Mapa de severação: os três pontos que tocam `annos/`

1. **Construção** — `select_videos` (`constructpipe/base.py:46,184`): usa `annos/` como manifesto (N1).
2. **Recuperação — consultas** — `DataSet4Test` (`dataset/dataset.py`): lê `desc` (N2) e exige `vid_name`+`ts` (N3).
3. **Recuperação — avaliação** — `eval_epoch` (`retrieve.py:182`) → `eval_retrieval`: consome `ts` (N3) para métricas.

### V.3 Cirurgia 1 — Construção (TRIVIAL)

`select_videos` lê **só** `data['vid_name']` para filtrar a interseção pasta∩anotação. Substitua por uma listagem direta, preservando a conversão mkv→mp4 que já existe na função:

```python
# constructpipe/base.py, em __init__ (linha ~46), trocar:
#   new_vid_list = self.select_videos(vid_list, anno_path)
# por uma versão que lista todos os vídeos da pasta (sem ler annos),
# mantendo o tratamento de .mkv presente em select_videos (l. 193–199).
```

Resultado: `tree.json` construída sobre os **seus** vídeos, zero rótulos. Nenhum outro ponto da construção toca `annos/`. **Indolor.**

### V.4 Cirurgia 2 — Recuperação (MODERADA; contém a armadilha)

`DataSet4Test` exige por linha `desc`, `vid_name`, `ts` (a linha `self.time_stamps.append(item["ts"])` quebra sem `ts`). Três sub-problemas:

**(a) Alimentar suas consultas — o paradoxo do `vid_name`.** Numa busca real você **não sabe** em qual vídeo está a resposta, mas o formato exige `vid_name`/`ts` (que são gabarito). *Confirmado em `MixPipe.py:66–73`:* o scoring roda a consulta contra **todos** os proposals do corpus e **nunca usa o `vid_name` da consulta** para pontuar — ele só é ecoado como `gt_vid_name`/`gt_ts`. Logo: preencha `vid_name`/`ts` com *dummies* e ignore esses campos no resultado. (Melhor prática: tornar `ts` opcional com default `[0.0, 0.0]` e adaptar o filtro de `vid_name`.)

**(b) A ARMADILHA DE ACOPLAMENTO (o ponto que ninguém vê).** Em `retrieve.py:271`:
```python
captree.compute_tree_feature(resume_video_names=test_dataset.vid_name_to_id.keys())
```
**O corpus pesquisável é atualmente *definido* pelos vídeos que aparecem no arquivo de consultas.** Se você quer buscar sobre *todos* os seus vídeos, `vid_name_to_id` precisa conter **todos** eles — senão a árvore é podada só para os referenciados, e o loop `vid_id = test_dataset.vid_name_to_id[vid_name]` (`MixPipe.py:70`) dá `KeyError` para qualquer vídeo da árvore ausente do dataset. **Correção:** popular `vid_name_to_id` a partir do conjunto de vídeos da *árvore* (não das consultas), ou desacoplar esse filtro. Sem isso, seu corpus encolhe silenciosamente.

**(c) Contornar a avaliação.** `eval_epoch` calcula métricas contra `ts` (lixo com dummies). Mas — crucial — as **predições** (`vcmr_res_dict`) são produzidas por `pipeline.retrieval()` **antes e independentemente** de qualquer métrica. Escreva um laço de inferência enxuto que: chama `pipeline.retrieval(test_dataset)`, aplica `post_processing_vcmr_nms` (o NMS), e salva só `vcmr_res_dict['VCMR']` — **pulando** `eval_retrieval` e as métricas de VR. Você obtém os resultados de busca sem gabarito.

### V.5 Contrafactual — o que quebra se você só apagar `annos/`

- **Construção:** `FileNotFoundError` em `open(anno_path)` (`base.py:187`).
- **Recuperação:** `DataSet4Test` falha ao abrir o arquivo; e `self.time_stamps.append(item["ts"])` daria `KeyError` sem `ts`.

Ou seja: apagar não basta. As cirurgias V.3–V.4 são o caminho correto.

### V.6 Arquitetura-alvo mínima para o seu deployment

```
[Sua pasta de vídeos brutos]
        │
        ▼  Construção (Cirurgia 1): select_videos → os.listdir
   tree.json (índice do SEU corpus, zero rótulos)
        │
        ▼  Recuperação (Cirurgia 2):
   [Prompt do usuário] → DataSet4Inference (ts opcional, vid_name desacoplado)
        │                → compute_tree_feature(resume_video_names = TODOS os vídeos da árvore)
        │                → pipeline.retrieval() → NMS → predições
        ▼
   [Lista ranqueada de (vídeo, [início,fim], score, legenda)]
```

---

## PARTE VI — Riscos que sobrevivem à extração (o que decide se vale a pena)

Remover o `annos/` resolve o bloqueio operacional, **não** os riscos de fundo. Estes governam a decisão:

1. **Transferência dos hiperparâmetros (risco alto).** θd, θb, α, W foram fixados em Charades/ActivityNet, sem protocolo declarado. No seu domínio podem ser subótimos — e, **sem rótulos seus, você não tem como re-tunar**. Fica preso aos defaults a menos que rotule uma fatia de validação. É o custo escondido mais concreto de "não ter anotação".
2. **A premissa VLLM é o requisito real (risco crítico, dependente de domínio).** Todo o pipeline repousa sobre BLIP/MiniGPT legendarem *bem os seus frames*. Domínios fora de "atividades internas"/"YouTube" (footage técnico, baixa luz, nichos) podem degradar tudo — não por causa do `annos/`, mas do captioning. **O gargalo do seu sistema é a adequação do VLLM ao seu domínio.**
3. **Teto de desempenho absoluto (risco alto para produto).** ~4–11% de acerto no top-10 nos benchmarks. No seu domínio, espere taxa de nível-pesquisa. Para uso por usuário final, terá de elevar o teto (VLLM moderno > BLIP; embeddings contextuais > GloVe; amostragem > 1fps).
4. **Granularidade temporal (risco médio).** 1fps + segmento mínimo ~3s; momentos curtos sofrem no IoU por construção.
5. **Escalabilidade da busca (risco médio, dependente de escala).** O `KeyPipe`/`MixPipe` monta matrizes densas `[Nq·max_QN, Np·max_PN]` que podem estourar memória em corpora grandes (dezenas de milhares de vídeos). Vigie se o acervo for grande.

---

## PARTE VII — O que falta para excelência + preparação da próxima fase

### VII.1 Informações necessárias para orientar com precisão

- **O domínio dos seus vídeos** (fator nº 1): decide se a premissa VLLM se sustenta.
- **Se você precisa *medir* qualidade:** se sim, terá de rotular uma fatia — e aí o `annos/` volta, no papel de avaliação, para o *seu* conjunto.
- **O tamanho do corpus:** decide se o risco de memória do `KeyPipe` (VI.5) é real.

### VII.2 Plano para a fase seguinte (análise fina + testes)

A próxima fase — que você indicou querer conduzir no chat — deve seguir esta ordem, com boas práticas de teste a cada passo:

1. **Reproduzir o pipeline como está**, num micro-corpus (5–10 vídeos seus) *com* um `annos/` mínimo dummy, para validar o ambiente antes de qualquer modificação. *Teste:* a `tree.json` é gerada? As predições saem?
2. **Cirurgia 1 (construção)** isolada. *Teste:* comparar a `tree.json` gerada com listagem de diretório vs. com o manifesto — devem ser idênticas para o mesmo conjunto de vídeos (teste de equivalência).
3. **Dissecar os módulos-núcleo** cruzando equação↔código, com testes unitários: SWi-Den (Eq. 2 — verificar a propagação causal e o gate), QM-Gen (Eq. 3–4 — verificar o kernel e a Quality-Mask), Keyword Sets (Eq. 5), fusão (Eq. 6–10). *Teste:* casos sintéticos com entrada conhecida e saída esperada.
4. **Cirurgia 2 (recuperação + desacoplamento)** com o laço de inferência puro. *Teste crítico:* verificar que o corpus pesquisável = todos os vídeos da árvore (a armadilha V.4b), com um teste que injeta um vídeo não-referenciado e confirma que ele é buscável.
5. **Teste de ponta a ponta:** prompt conhecido → o momento esperado aparece no top-K? (validação qualitativa, já que sem gabarito não há métrica).

### VII.3 Direções de melhoria (headroom do método)

A arquitetura é **agnóstica aos componentes**, então o teto é limitado principalmente pela idade das peças — boa notícia para quem estende: trocar BLIP por VLLM moderno (Qwen-VL, InternVL, LLaVA-OneVision); GloVe por embeddings contextuais (o `Max_Mean` sobrevive); amostragem >1fps; e segmentação que preserve a magnitude absoluta de novidade (o código a descarta via min-max, causando sobre-segmentação de vídeos uniformes).

---

## APÊNDICE — Índice de referência rápida (para navegar na fase 2)

| Arquivo | Função / âncora | Linha | Papel |
|---|---|---|---|
| `construct.py` | `main` (instancia componentes) | 27, 42–49 | Ponto de entrada da construção |
| `constructpipe/base.py` | `construct` | 67–90 | Orquestrador (7 etapas) |
| `constructpipe/base.py` | `select_videos` | 184 | **Alvo Cirurgia 1** (lê só `vid_name`) |
| `constructpipe/base.py` | `build_tree_meta` | 169–182 | Monta `tree.json` (2 níveis) |
| `viddataset.py` | `VideoDatasetPerSec` | — | Amostragem 1fps (ffmpeg) |
| `capgenerator/BlipCapGener.py` | `generate_caption` | — | Captioning BLIP |
| `utils/genCaptions_minigpt.py` | script externo | 203 | Captioning MiniGPT (lê só `vid_name`) |
| `utils/sim_utils.py` | `get_caption_frame_sims` | 78 | Quality Score (Eq. 1) |
| `utils/sim_utils.py` | `normalize_min_max` | 30 | Normalização (não está nas eqs.) |
| `denoiser/window.py` | `denoise_caption` | 20–34 | SWi-Den (Eq. 2) |
| `propgenerator/QMPropGener.py` | `calculate_similarities` | 28 | Matriz `vis`/`txt`/`it` |
| `propgenerator/QMPropGener.py` | `generate_proposal` | 69–105 | QM-Gen: kernel (74–87), fronteiras (98–105) |
| `propgenerator/QMPropGener.py` | keys via `get_nouns_verbs` | 136 | Indexing Keyword Set (Eq. 5) |
| `treebuilder/capTree.py` | `CapTree`, `build_relations` | 14, 47 | Índice pesquisável |
| `treebuilder/capTree.py` | `compute_tree_feature` | 105 | **Armadilha de acoplamento** (V.4b) |
| `retrievepipe/MixPipe.py` | scoring | 66–73 | Consulta vs corpus; `vid_name_to_id` |
| `retrievepipe/MixPipe.py` | construção da saída | 145–162 | **Formato do resultado** (V.1) |
| `retrieve.py` | `start_inference` | 236–283 | Ponto de entrada da recuperação |
| `retrieve.py` | `eval_epoch` | 182–231 | **Alvo Cirurgia 2c** (avaliação a contornar) |
| `dataset/dataset.py` | `DataSet4Test` | — | **Alvo Cirurgia 2a** (exige `ts`) |
| `standalone_eval/eval.py` | `eval_by_task_type` | 82–164 | Regra de acerto (vid_name + IoU) |
| `utils/temporal_nms.py` | NMS | — | Deduplicação de momentos |

**Hiperparâmetros (defaults, em `scripts/*.sh` e `config/cfg.py`):** θd=0.4 (`figsim_denoise_thr`), W=2 (`denoise_window_width`), θb=0.2 (`prop_score_thr`), `prop_kernel_width`=5, `prop_min/max_cnt`=2/5, α=0.5 (`retrieve_sent_ratio`), `key_policy`=max_mean, amostragem 1fps.

---

*Fim do relatório. A fase seguinte — análise fina módulo a módulo com testes — pode começar pelo item VII.2, na ordem proposta.*
