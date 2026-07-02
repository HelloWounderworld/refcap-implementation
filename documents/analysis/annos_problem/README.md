# RefCap — Análise Detalhada: Função e Necessidade do Diretório `annos/`

> **Pergunta que este relatório responde.** (1) O que é, de fato, o conteúdo de `annos/`? (2) Quais funcionalidades da arquitetura dependem dele / interagem com ele? (3) Sua existência é uma **condição necessária** para que o *núcleo novo* que o sistema propõe funcione — ou não?
>
> **Método.** Rastreamento exaustivo de todos os pontos do código que abrem/leem `annos/` + inspeção empírica do conteúdo real dos arquivos. Análise baseada só no código (o artigo será cruzado depois).
>
> **Tese central (adiantada).** `annos/` é **operacionalmente load-bearing** para o repositório como distribuído (o código o abre nos dois estágios e quebra sem ele), mas **não é condição necessária para a funcionalidade-núcleo**. Ele fornece três coisas de naturezas distintas — um manifesto de vídeos (substituível), as consultas de avaliação (que em produção vêm do usuário) e o gabarito (usado só para medir, jamais para rodar o método). A distinção entre esses dois sentidos de "necessário" é o eixo de tudo o que segue.

---

## 1. Anatomia do conteúdo de `annos/`

O diretório contém um arquivo por dataset: `annos/charades/vcmr.jsonl` e `annos/activitynet/vcmr.jsonl`. Cada **linha** é uma **consulta** (não um vídeo) no formato JSONL, com exatamente cinco campos.

### 1.1 Esquema, campo a campo

| Campo | Exemplo | O que É (semântica) | Papel funcional |
|---|---|---|---|
| `vid_name` | `"3MSZA"` | Identificador do arquivo de vídeo | **Manifesto** (construção) + chave de gabarito (avaliação) |
| `desc_name` | `"3MSZA#enc#0"` | Identificador da consulta, no formato `{vid_name}#enc#{k}` distinguindo a k-ésima consulta daquele vídeo | Identificador (rastreio) |
| `duration` | `30.96` | Duração do vídeo em segundos | Redundante no código (ver §2.3) |
| `ts` | `[24.3, 30.4]` | **Gabarito**: intervalo `[início, fim]` do momento que responde à consulta | **Ground truth** (só avaliação) |
| `desc` | `"person turn a light on."` | **A consulta textual** em linguagem natural | **Query** (entrada da recuperação) |

### 1.2 Fatos empíricos (medidos sobre os arquivos)

| Métrica | Charades | ActivityNet |
|---|---|---|
| Linhas (consultas) | 3.720 | 17.505 |
| Vídeos únicos | 1.334 | 4.917 |
| Consultas por vídeo (média / máx) | 2,79 / 12 | 3,56 / 25 |
| Vídeos com >1 momento (`ts`) distinto | 57% | 100% |
| Momento / duração do vídeo (mediana) | 0,26 | 0,25 |
| Momentos cobrindo ~o vídeo inteiro (≥98%) | 0% | 4% |
| Duração do momento (mediana) | 7,1 s | 22,9 s |

**Leitura destes números.** Cada vídeo tem **várias consultas**, cada uma apontando (frequentemente) para um **momento diferente** — daí "vid_name" repetir entre linhas. O momento-alvo é tipicamente **~um quarto do vídeo** e quase nunca o vídeo inteiro: isto confirma que a *localização temporal* é um subproblema não-trivial, o que por sua vez confirma que o campo `ts` é um **gabarito de avaliação legítimo** (se os momentos fossem sempre o vídeo todo, medir IoU seria vazio).

### 1.3 As três naturezas dentro de um mesmo arquivo

O ponto conceitual que dissolve qualquer aparente contradição com a alegação "sem anotações": os cinco campos pertencem a **três categorias epistemicamente diferentes**, e é um erro tratá-las como um bloco único chamado "anotação".

- **(N1) Manifesto do corpus** — `vid_name`. Diz *quais vídeos existem*. Informação de catálogo, não de rótulo.
- **(N2) Consulta** — `desc` (e seu id `desc_name`). É a *entrada* que o usuário fornece a qualquer sistema de busca. Não é uma anotação *do vídeo*; é o pedido *sobre* o vídeo.
- **(N3) Gabarito (supervisão)** — `ts`. É o único campo que corresponde ao que a literatura chama de "anotação de momento" no sentido de rótulo supervisionado: a resposta correta.

A alegação "dispensa anotações massivas" refere-se a **N3** (rótulos para *treinar*). Como se verá, N3 nunca é consumido pelo método.

---

## 2. Mapa exaustivo de dependências: quem toca `annos/`, em que modo, lendo o quê

Rastreamento completo (via `grep` sobre `anno_dir`, `anno_file`, `vcmr.jsonl`, `split_json`, `anno_path`, `gt_anno`). Existem **exatamente três** pontos no código que abrem o arquivo, mais os sítios de configuração.

| Ponto de uso | Arquivo · linha | Estágio | Campos lidos | Modo |
|---|---|---|---|---|
| `select_videos` | `constructpipe/base.py:184` (`open` em l. 187, leitura em l. 191) | Construção | **só `vid_name`** | Manifesto (N1) |
| Script MiniGPT | `utils/genCaptions_minigpt.py:203` (leitura em l. 207) | Construção (externa) | **só `vid_name`** | Manifesto (N1) |
| `DataSet4Test` | `dataset/dataset.py` (instanciado em `retrieve.py:270`) | Recuperação | `vid_name`, `desc`, `ts`, `desc_name` | Query (N2) + Gabarito (N3) |
| Declaração de caminho | `config/cfg.py:5-6` (`anno_dir`, `anno_file`) | ambos | — | Configuração |

### 2.1 Na construção: `annos/` é puro manifesto

`select_videos` (`constructpipe/base.py`) lê **um único campo**, `data['vid_name']` (l. 191), e o usa para calcular a **interseção** entre os vídeos anotados e os arquivos presentes em `video_root`. Os campos `ts`, `desc`, `duration` são **ignorados na íntegra**. Portanto, na etapa que constrói o índice — captioning, features, denoising, segmentação, árvore — o arquivo de anotação funciona apenas como uma **lista de nomes de arquivo a processar**. O script do MiniGPT (`genCaptions_minigpt.py`, l. 207) faz exatamente o mesmo.

> **Implicação imediata:** a construção é **agnóstica à consulta e ao gabarito**. Legenda-se cada frame de forma genérica (`"describe this image"`) sem saber o que será perguntado nem onde está a resposta.

### 2.2 Na recuperação: consulta (usada) + gabarito (inerte ao método)

`DataSet4Test` (`dataset/dataset.py`) lê `desc` como **consulta** (l. 51) e `ts`+`vid_name` como **gabarito** (l. 52-54). Mas há uma sutileza decisiva, comprovada no código: **o gabarito `ts` é repassado, nunca calculado**. No `MixPipe.retrieval`, `starts`/`ends` (o `ts`) aparecem em apenas dois lugares:

- l. 61 — desempacotados do batch;
- l. 160 — copiados para a saída como `gt_ts=[starts[i], ends[i]]`.

O *scoring* propriamente dito — `esm_sims` (l. 130) e o `torch.topk` que seleciona os momentos (l. 139) — opera **exclusivamente** sobre similaridades de sentença e de palavra. O `ts` **não entra em nenhum cálculo**; ele só viaja junto da predição para que a avaliação (§2.4) possa compará-lo depois. O mesmo vale para `SentPipe` e `KeyPipe`.

> **Consequência forte:** mesmo em tempo de recuperação, **o método jamais consome a supervisão (N3)**. O gabarito atravessa a pipeline como carga inerte destinada ao avaliador.

### 2.3 Detalhe: `duration` do anno é redundante

`DataSet4Test` nem lê `duration` do anno; as durações usadas no método vêm do **próprio vídeo** (via `ffprobe` em `viddataset.py`) e ficam na `tree.json`. O `duration` do anno existe por convenção do formato, mas é inerte ao código.

### 2.4 Na avaliação: o gabarito é finalmente consumido

`standalone_eval/eval.py::eval_by_task_type` é o **único** lugar que efetivamente usa `ts`. A regra (documentada em l. 85-87): uma predição é positiva sse o `vid_name` bate **e** o IoU temporal entre a predição e o `ts` supera o limiar. Antes disso, `retrieve.py::eval_epoch` (l. 182) aplica NMS. Este bloco é **medição, não método**.

---

## 3. Quais funcionalidades da arquitetura são "cruciais para `annos/`"

Reformulando sua pergunta ("quais funcionalidades cumprem papel crucial *para* annos"): trata-se de identificar **quais partes do sistema estão acopladas ao `annos/`** — e, por contraste, quais não estão. O mapa é nítido e assimétrico.

**Dependem de `annos/` (acopladas a ele):**
- `select_videos` (`constructpipe/base.py`) — precisa dele como manifesto (N1) para saber o que indexar.
- `DataSet4Test` (`dataset/dataset.py`) — precisa dele para obter consultas (N2) e gabarito (N3).
- `eval_epoch` + `standalone_eval/eval.py` — precisam do gabarito (N3) para produzir métricas.

**NÃO dependem de `annos/` (o núcleo do método):**
- Gerador de legendas (`capgenerator/`) — opera sobre frames de vídeo.
- Sinal ITM (`utils/sim_utils.py`) — opera sobre legendas e frames.
- Denoiser (`denoiser/window.py`) — opera sobre legendas e scores ITM.
- Segmentação (`propgenerator/QMPropGener.py`) — opera sobre a matriz de similaridade.
- Índice (`treebuilder/capTree.py`) — opera sobre proposals.
- A matemática de matching (`retrievepipe/`) — opera sobre embeddings da consulta e do índice (o `ts` é inerte, §2.2).

Ou seja: **todo o pipeline que constitui a contribuição do trabalho é indiferente ao conteúdo de `annos/`.** As três funcionalidades acopladas a `annos/` são, todas, de *infraestrutura experimental* (catalogar, alimentar consultas, medir) — não de *método*.

---

## 4. Análise de necessidade — dois sentidos de "necessário"

A pergunta "annos é condição necessária?" só tem resposta precisa se separarmos dois sentidos que a linguagem natural funde.

### 4.1 Necessidade operacional (o código, como escrito, roda sem `annos/`?)

**Não — o código quebra.** Contrafactual, apagando `annos/`:
- **Construção:** `select_videos` executa `open(anno_path)` (`base.py:187`) → `FileNotFoundError`.
- **Recuperação:** `retrieve.py:262` monta `gt_anno_path` e `DataSet4Test` tenta lê-lo; além disso l. 54 faria `KeyError` sem `ts`.

Logo, no sentido de *plumbing*, `annos/` é necessário ao repositório tal como distribuído. **Mas isto diz respeito ao encanamento do experimento, não ao método.**

### 4.2 Necessidade metodológica (o núcleo novo precisa da *informação* de `annos/`?)

Aqui decompomos o que `annos/` **fornece** versus o que o núcleo **consome**, por categoria:

| Informação | Consumida por | Necessária p/ o código rodar? | Necessária p/ o **núcleo** funcionar? | Necessária só p/ **avaliar**? | Substituível por quê |
|---|---|:---:|:---:|:---:|---|
| **N1 — manifesto** (`vid_name`) | `select_videos` | Sim | **Não** | — | `os.listdir(video_root)` ou manifesto próprio só com `vid_name` |
| **N2 — consulta** (`desc`) | `DataSet4Test` → matching | Sim | **Não*** | — | Prompt do usuário em tempo de query |
| **N3 — gabarito** (`ts`) | só `standalone_eval` | Sim (`DataSet4Test` exige o campo) | **Não** | **Sim** | Nada — só existe para medir |

\* **Nota sobre N2.** É preciso ser exato: qualquer sistema de busca precisa de *uma* consulta para funcionar — sem termo de busca não há recuperação. Esse é um requisito trivial de *qualquer* motor de busca, não uma dependência de anotação. O que o núcleo do RefCap **não** precisa é que a consulta venha pré-existente do `annos/`, nem que ela seja um rótulo do vídeo. Em produção, `desc` = o prompt digitado pelo usuário. Portanto N2 não é uma "anotação"; é a entrada do sistema.

**Síntese:** nenhuma das três informações de `annos/` é condição necessária para o **núcleo** funcionar. N1 é substituível por uma listagem de diretório; N2 é fornecida pelo usuário; N3 nunca é usada pelo método (só pelo avaliador). A única "necessidade" real e não-trivial que sobra é a de *qualquer* motor de busca: existir um corpus a indexar e uma consulta a atender.

---

## 5. O núcleo novo do sistema e sua relação formal com `annos/`

O que o trabalho propõe como contribuição (a confirmar no paper, mas evidente no código) é: **transformar vídeos brutos em uma estrutura textual pesquisável — sem supervisão específica da tarefa — e recuperar momentos por similaridade texto-a-texto.**

As **condições necessárias** para esse núcleo funcionar, lidas do código, são:
1. Os **vídeos brutos** (entrada de `viddataset.py`).
2. Uma **enumeração do corpus** (quais vídeos indexar) — hoje suprida por N1, trivialmente substituível.
3. Os **modelos pré-treinados** (`model_utils.py`: BLIP, sentence-transformer, GloVe).
4. Em tempo de query, **uma consulta** (N2 em produção = prompt do usuário).

**Anotações supervisionadas (N3) não aparecem nesta lista.** Portanto, formalmente: `annos/` **não é condição necessária** para a funcionalidade-núcleo e nova do sistema. É condição necessária apenas para (i) o repositório rodar sem edição e (ii) a avaliação em benchmark ser computável.

Isto é **consistente** com a alegação "dispensa anotações massivas": o índice — a parte cara — é construído com **zero rótulos e zero conhecimento das consultas**.

---

## 6. O caveat honesto: o único canal pelo qual `annos/` *poderia* tocar o núcleo

Rigor exige apontar a fresta. Mesmo que o método não consuma rótulos em tempo de execução, ele **poderia** ter sido *calibrado* usando-os. As constantes mágicas — `figsim_denoise_thr=0.4`, `prop_score_thr=0.2`, `denoise_window_width`, `retrieve_sent_ratio=0.5`, etc. (todas em `scripts/*.sh`) — são hiperparâmetros. Se foram escolhidos maximizando Recall **no conjunto rotulado de teste**, então informação derivada de `annos/` (N3) vazou **indiretamente**, via configuração, para o método.

Isso **não** contradiz "training-free" (não há treino por gradiente), mas relativiza "annotation-free". É um canal de *design experimental*, não uma dependência de código. **A verificar no artigo:** existe um protocolo de validação (limiares fixados a priori, ou tunados em um split de validação separado, ou — o problema — no teste)? Esta é a única pergunta que, respondida, fecha em definitivo a questão da necessidade de anotações.

---

## 7. Implicação prática para o seu sistema (busca por prompt em vídeos brutos)

Traduzindo a análise em ação, por estágio:

**Construção (indexar seus vídeos):**
- Substituir a leitura de `annos/` em `select_videos` (`constructpipe/base.py`) por `os.listdir(video_root)` — ou por um manifesto próprio contendo **apenas** `vid_name` dos seus vídeos. É a alteração mínima; nenhum outro componente da construção precisa mudar.
- Resultado: uma `tree.json` construída sobre o **seu** corpus, sem nenhum rótulo.

**Recuperação (servir consultas do usuário):**
- Você precisa **fornecer suas consultas** e **contornar a avaliação**. `DataSet4Test` hoje exige `ts` (l. 54) e `eval_epoch` calcula métricas contra ele — ambos pressupõem benchmark, não produção.
- Cirurgia leve: um caminho de inferência que aceite `desc` (o prompt) sem `ts`, chame `infer_pipeline.retrieval(...)` e devolva os `predictions` (vídeo + intervalo) **sem** passar por `eval_epoch`.

**Gabarito:** você **não guarda** N3, a menos que queira medir acurácia num conjunto rotulado — aí, e só aí, precisará de `ts`.

---

## 8. Veredito

`annos/` é **operacionalmente necessário** ao repositório como distribuído (o código o abre nos dois estágios e falha sem ele), porém **não é condição necessária para a funcionalidade-núcleo e nova** que o sistema propõe. Ele empacota três informações de naturezas distintas: um **manifesto de vídeos** (N1, substituível por uma listagem de diretório), as **consultas de avaliação** (N2, que em produção são o prompt do usuário e não são anotações do vídeo) e o **gabarito de momentos** (N3, consumido *exclusivamente* pelo avaliador e comprovadamente inerte ao *scoring* do método). O núcleo — captioning agnóstico à consulta, denoising, segmentação por novidade, indexação e matching texto-a-texto — funciona a partir de vídeos brutos + enumeração do corpus + modelos pré-treinados + a consulta, sem jamais tocar em rótulos. A alegação de "dispensar anotações massivas" é, portanto, coerente com a presença de `annos/` — restando um único ponto a confirmar no artigo: o protocolo de ajuste dos hiperparâmetros, o único canal pelo qual anotações poderiam ter influenciado o método de forma indireta.
