# Projeto do `WholePropGenerator`
## Seleção e Ranqueamento de Legendas sem Segmentação — Especificação Completa

---

> **O que é este documento.** A especificação de projeto — **antes do código** — de um novo gerador de propostas para o RefCap que produz **um único segmento por vídeo** (a cena inteira) e **ranqueia as legendas** geradas para ela, em vez de detectar fronteiras.
>
> **Por que ele existe.** Cada vídeo da sua coleção **já é o corte que interessa**. A detecção de fronteiras do `QMPropGenerator` é, no seu caso, trabalho inútil e potencialmente prejudicial (ela pode partir uma cena que você quer inteira). O que você precisa do Passo 3 é apenas a **seleção da legenda** — e é exatamente essa parte que este componente isola e melhora.
>
> **Status.** Nada será codificado sem a sua aprovação. Cada decisão abaixo traz a **justificativa** e, onde existe, a **alternativa rejeitada e o porquê**.
>
> **Base factual.** Todas as afirmações sobre o repositório foram verificadas no código, com arquivo e linha. Sete descobertas novas surgiram desta revisão e estão marcadas com ★ — três delas mudam o desenho.

---

# PARTE 0 — Sumário executivo

**O que será construído:** uma classe `WholePropGenerator`, registrada como `"whole"`, que:
1. emite **um segmento** cobrindo `[0, duration]` por vídeo (sem detecção de fronteiras);
2. **deduplica** as legendas geradas pelo BLIP;
3. calcula **três sinais de ranqueamento independentes** para cada legenda distinta;
4. emite o **ranking completo** (não só o vencedor) no `proposals.json`;
5. preserva as **keywords** de todos os frames (o ramo GloVe da busca).

**O que NÃO será tocado:** nenhum arquivo existente do RefCap terá uma linha modificada. Serão **três adições** (um arquivo novo, uma linha no `__init__.py`, uma string na lista de `choices`).

**O custo:** um forward pass adicional do *text encoder* do BLIP-ITM sobre ≤5 strings curtas por vídeo. Desprezível.

---

# PARTE 1 — Diagnóstico: por que um componente novo

## 1.1 Por que não `prop_max_cnt` (correção de um erro anterior)

Um relatório anterior afirmou que `--prop_max_cnt 1` forçaria o caso-base `boundaries=[0, VID_LEN]`, dando um segmento único **por configuração**. **Isso está errado.**

O motivo está em `QMPropGener.py:95-97`:
```python
if len(boundaries)==0:
    boundaries.append(id)     # ← a 1ª fronteira entra INCONDICIONALMENTE
    continue
if len(boundaries)+1>=self.cfg.prop_max_cnt:   # ← só avaliado a partir da 2ª
    break
```
A primeira fronteira candidata é adicionada **antes** de a checagem de `prop_max_cnt` sequer ser avaliada. Logo `boundaries` nunca fica vazio, e o caso-base da linha 109 é inalcançável na prática.

Simulação fiel do algoritmo com 200 vídeos sintéticos:

| `prop_max_cnt` | 1 segmento | 2 segmentos | 3+ |
|---|---|---|---|
| **1** | 9 | **191** | 0 |
| **2** | 13 | **187** | 0 |
| 5 | 0 | 0 | 200 |

Com `prop_max_cnt=1` você obtém **dois** segmentos em ~95% dos casos. O único caso que colapsa para um é acidente dos dados (a fronteira cair a menos de `min_prop_size` de uma ponta), não garantia de configuração.

**Conclusão:** "um segmento por vídeo" **não é alcançável por configuração**. Exige um componente.

## 1.2 Por que não editar o `QMPropGenerator`

Alterá-lo para "desligar" o agrupamento seria mexer no núcleo, arriscando a seleção e a coleta de keywords, e destruiria a capacidade de comparar as duas abordagens lado a lado. O registry existe precisamente para evitar isso — ver Parte 2.

## 1.3 ★ Por que o critério de seleção atual é inadequado ao seu objetivo

Esta é a descoberta que justifica o componente ir além de "um segmento só".

O `QMPropGenerator` escolhe a legenda assim (`QMPropGener.py:130-133`):
```python
scores = capframe_scores[st_idx:ed_idx]
max_idx = torch.argmax(scores).item()
cap = metas['frame_captions'][str(max_idx)]['cap']
```
Ou seja: **argmax de `capframe_scores`**. E `capframe_scores` é, verificado em `sim_utils.py:91`, a **diagonal** da matriz cruzada — `sim(legenda_i, frame_i)`.

**O problema:** a legenda *i* foi **gerada a partir do frame *i***. Logo `sim(cap_i, frame_i)` não é uma medição independente — está contaminada por construção. O que ela mede é *"quão confiante e fluente o BLIP foi ao legendar aquele frame"*, o que correlaciona com **legibilidade e tipicidade do frame**, não com **representatividade da cena**.

E as duas grandezas podem **anticorrelacionar**: um close-up nítido é fácil de legendar com alta confiança *precisamente por ser atípico* — que é o que o torna um péssimo representante da cena.

Demonstração numérica (cena sintética de cozinha, 8s, com dois close-ups atípicos no meio):

| critério | legenda escolhida |
|---|---|
| diagonal (o que o RefCap usa) | *"a close up of a hand holding a knife"* |
| média da linha da matriz cruzada | *"a woman preparing food in a kitchen"* |

**Diagonal responde "o BLIP acertou este frame?"; média da linha responde "este texto descreve a cena?"** São perguntas diferentes, e a segunda é a sua.

---

# PARTE 2 — Encaixe arquitetural

## 2.1 O mecanismo: registry + OCP

O `propgenerator` usa o mesmo padrão *registry* dos outros módulos (`propgenerator/base.py:6-20`): um dicionário `PROPGEN_REGISTRY`, um decorador-fábrica `REGISTER_PROPGEN(names)` e um *getter* `get_propgen_class(name)`.

Isso significa que adicionar uma estratégia nova é **extensão pura** — o Princípio Aberto/Fechado em ação:

| Ação | Arquivo | Tipo |
|---|---|---|
| criar `WholePropGener.py` | `pipeline/propgenerator/` | **adição** |
| registrar o módulo | `pipeline/propgenerator/__init__.py` | **adição de 1 linha** |
| liberar o nome | `config/cfg.py:76` | **1 string na lista** |

**Zero modificações.** O `QMPropGenerator` permanece intacto e utilizável — você troca entre os dois com `proposal_generator=qm` ou `=whole` no `construct.sh`.

## 2.2 A forma do import (decisão consciente)

O `__init__.py` atual usa `from .QMPropGener import *`. Para a linha nova, a recomendação é:

```python
from . import WholePropGener      # e NÃO: from .WholePropGener import *
```

**Justificativa:** o que aquela linha precisa entregar é o **efeito colateral de import** (executar o módulo para o decorador registrar a classe). As duas formas produzem esse efeito idêntico; a forma com `*` adicionalmente despeja todos os nomes do módulo — incluindo os que ele importou (`torch`, `np`, `os`, `spacy`...) — no namespace do pacote. Como o repositório não define `__all__` em lugar nenhum, esse vazamento é total.

É uma divergência deliberada do padrão do repo, e vale um comentário de uma linha explicando. **Não quebra nada** — o registro acontece igual.

## 2.3 ★ A assinatura: um defeito herdado que precisa ser conhecido

`propgenerator/base.py:28` declara:
```python
@abstractmethod
def __call__(self, vid_list, captions, scores): ...        # 3 parâmetros
```
Mas o `QMPropGenerator.__call__` (linha 44) exige **4** (`+ all_frame_features`), e o pipeline passa 4 (`constructpipe/base.py:86`).

**A classe abstrata mente sobre o contrato.** Isso é violação do Princípio de Substituição de Liskov, e o `@abstractmethod` não pega — ele verifica se o método *existe*, nunca se a *assinatura é compatível*.

**Decisão de projeto:** o `WholePropGenerator` seguirá a assinatura **real** (4 parâmetros), não a declarada. Alternativa rejeitada: corrigir a ABC — seria modificar arquivo existente e quebraria o `QMPropGenerator` se alguém dependesse da declaração. Documentamos o defeito e convivemos.

---

# PARTE 3 — Contratos de dados (o que entra e o que sai)

## 3.1 O que o componente recebe

```python
def __call__(self, vid_list, captions, scores, all_frame_features):
```

| Argumento | Tipo | Conteúdo |
|---|---|---|
| `vid_list` | `list[str]` | nomes de arquivo com extensão (`"clipA.mp4"`) |
| `captions` | `list[dict]` | um dict por vídeo: `{'vid_name', 'duration', 'frame_captions'}` |
| `scores` | `dict[str, Tensor]` | `capframe_scores` por vídeo — **a diagonal** `[N]` |
| `all_frame_features` | `dict[str, Tensor]` | features visuais BLIP-ITM `[N, D]`, L2-normalizadas |

E, do `__init__` (espelhando o `QMPropGenerator`): `cfg`, `txt_sim_model` (sentence-transformer), `it_sim_model` + `it_sim_processor` (BLIP-ITM), `nlp` (spaCy).

## 3.2 ★ Como obter a matriz cruzada completa sem modificar nada

Este é o achado central do desenho.

`utils/sim_utils.py:90-92`:
```python
ALL_SIMS = cap_features @ frame_features.t()     # matriz COMPLETA [N,N]: legenda i × frame j
sims = ALL_SIMS.diag()                            # só a DIAGONAL
return sims, ALL_SIMS
```

E `constructpipe/base.py:110`:
```python
sims, _ = sim_utils.get_caption_frame_sims(...)   # ← a matriz completa é DESCARTADA
```

**O RefCap calcula exatamente a matriz que precisamos e a joga fora num underscore.**

Ambos os lados são L2-normalizados no espaço compartilhado do BLIP-ITM (`sim_utils.py:52` e `:74`, via `vision_proj`/`text_proj`), então o produto interno **é** cosseno legítimo.

**A solução que preserva o OCP:** o `WholePropGenerator` **recalcula** `ALL_SIMS` internamente, chamando a mesma função utilitária. Ele já recebe `all_frame_features` e já tem `it_sim_model`/`it_sim_processor` — tem tudo o que precisa.

```python
_, all_sims = sim_utils.get_caption_frame_sims(
    self.it_sim_model, self.it_sim_processor, frame_features, sentences, self.cfg)
```

**Alternativa rejeitada:** modificar `compute_capframe_scores` para persistir `ALL_SIMS`. Rejeitada porque (a) modificaria arquivo existente, quebrando o OCP; (b) invalidaria os caches `.pt` já gerados; (c) o custo evitado é irrisório.

**O custo real da recomputação:** um forward do *text encoder* sobre ≤5 strings curtas por vídeo. As features **visuais** (a parte cara) já vêm prontas. Desprezível.

## 3.3 O que o componente devolve

O contrato exigido pelo consumidor (`constructpipe/base.py:174-181`):
```python
proposals[video_name] = {
    'proposals': [ {'st': float, 'ed': float, 'cap': str, 'keys': list[str]}, ... ],
    'duration': float
}
```

★ **Verificado:** o `build_tree_meta` lê apenas `st`, `ed`, `cap` e `keys`. **Chaves extras no dicionário de proposta são simplesmente ignoradas.**

**Isso é uma oportunidade:** podemos anexar todo o ranking e os diagnósticos ao objeto de proposta. Eles sobrevivem no `proposals.json` (salvo pelo próprio componente) para você inspecionar, e **não poluem** o `tree.json`.

## 3.4 ★ Múltiplas legendas por segmento são suportadas — e é ganho grátis

Duas verificações no lado da recuperação:

**`capTree.py:72`** — `self.cap_to_nodeid += [node['node_id']]*len(node['caps'])`. Várias legendas de um nó mapeiam todas para **o mesmo nó**, ou seja, para o mesmo intervalo `[st, ed]`.

**`MixPipe.py:73`** — `sims = torch.max(rel_sims, dim=1)[0]`. O score de um vídeo é o **MÁXIMO** sobre as suas legendas.

**Consequência:** indexar N legendas em vez de 1 **só pode aumentar o score de recuperação, nunca diminuir**. Uma consulta que case com qualquer uma das legendas recupera a cena. Não há risco de resultado duplicado, porque o `max` colapsa tudo num score por vídeo.

**Isso muda o papel do ranking.** Ele deixa de ser "escolher uma e descartar o resto" e passa a ser:
- **ordem de prioridade** para inspeção e diagnóstico;
- **controle opcional de poda**, se você quiser um índice enxuto.

A arquitetura não te obriga a jogar legenda fora. O ranking te dá a escolha.

---

# PARTE 4 — Os critérios de ranqueamento

## 4.1 O problema epistemológico e a sua solução

O impasse que você levantou: *"para dizer qual legenda é a melhor, eu não precisaria de uma legenda de referência?"*

**A premissa está errada de um jeito produtivo.** Você não precisa de uma legenda-referência porque tem uma **referência melhor: o próprio vídeo**. O problema é *cross-modal*, não texto-contra-texto. E existe um segundo sinal que dispensa até o vídeo: as N legendas são amostras independentes do mesmo conteúdo, então **a multidão é sua própria referência**.

Isso dá três sinais reference-free.

## 4.2 Sinal A — `self_score` (a diagonal, o critério atual)

**Definição:** `all_sims[i][i]` — similaridade da legenda *i* com o **seu próprio** frame.

**O que mede:** confiança/fluência do BLIP naquele frame.

**Por que incluir:** é o critério do `QMPropGenerator`. Mantê-lo como coluna permite **comparar** as abordagens nos seus dados reais, em vez de assumir que a nova é melhor.

**Limite:** enviesado por construção (Parte 1.3). Não deve ser o critério padrão.

## 4.3 Sinal B — `scene_score` (média da linha) ← o critério recomendado

**Definição:** `all_sims[i].mean()` — similaridade média da legenda *i* com **todos** os frames da cena.

**A formalização:** você quer o representante da cena. Se a cena é o conjunto de frames e "representar bem" significa alta similaridade com um frame qualquer dela, o objetivo é

```
argmax_i  E_j [ sim(legenda_i, frame_j) ]
```

que é exatamente a média da linha. É o **medoide cross-modal** — não é heurística arbitrária, é o objetivo natural de "elemento mais central de um conjunto".

**Por que é melhor que a diagonal:** não sofre o viés de construção. A legenda *i* nunca viu os frames *j≠i*, então `sim(cap_i, frame_j)` é uma medição **independente**. A média sobre todos os *j* mede representatividade genuína.

**★ Limite honesto — e é sério:** a média **premia legenda genérica**. *"a woman in a kitchen"* casa moderadamente com tudo; *"a woman chopping onions"* casa muito com dois frames e pouco com três. A média favorece a sem graça.

E isso importa para o seu objetivo final, que é **busca por texto**: legenda genérica é quase inútil para recuperação — não discrimina entre cenas. Há uma **tensão real entre representatividade e especificidade**, e não é óbvio que a representatividade deva vencer.

É precisamente por causa dessa tensão que o desenho **não elege um critério** — ver 4.6.

## 4.4 Sinal C — `consensus` (centralidade textual)

**Definição:** média da linha da matriz de similaridade **texto-texto** entre as legendas (SBERT), excluindo a diagonal.

**O que mede:** o quanto a legenda *i* concorda com as outras. O que é idiossincrático de um frame não se repete; o que é essencial à cena aparece em várias legendas.

**Por que incluir:** é o único sinal que dispensa completamente o vídeo — útil como verificação cruzada. E é *consensus reranking*, ideia estabelecida na literatura de captioning.

**★ Limite honesto — e com N≤5 ele é grave:** consenso é estatística de multidão, e uma multidão de 2–5 elementos não é multidão. Além disso, **frequência ≠ qualidade**: se 3 dos 5 segundos são estáticos, o BLIP gera 3 legendas quase iguais e o consenso é dominado por repetição, não por mérito.

**Decisão:** incluir como coluna diagnóstica, **não** como critério padrão.

## 4.5 Sinal D — `n_words` (proxy de especificidade)

**Definição:** contagem de palavras da legenda.

**Por quê:** é o contrapeso grosseiro ao viés genérico do Sinal B. Não é um critério de qualidade — é um **desempatador** e um sinalizador. Se o topo do ranking por `scene_score` for sistematicamente a legenda mais curta, isso é evidência visível do problema de 4.3.

## 4.6 ★ A decisão central: colunas, não veredito

**O componente não elegerá um critério vencedor.** Ele emitirá o ranking com **todas as colunas lado a lado**, ordenado por um critério configurável (padrão: `scene_score`).

**A justificativa é epistemológica, e é o ponto mais importante deste relatório.** Escolher um critério *a priori* exigiria saber qual acerta mais — o que exigiria referências, que você não tem. Sem referências e com N≤5, **olhar algumas dezenas de casos com as colunas lado a lado é literalmente o método mais rigoroso disponível**, e é barato.

Fixar um critério agora seria fingir um conhecimento que não temos. Isso é o oposto do que o resto desta análise vem fazendo.

---

# PARTE 5 — O algoritmo, passo a passo

Para cada vídeo em `vid_list`:

**Passo 1 — Extrair as legendas.**
Ler `cap['frame_captions']` preservando a **ordem temporal** dos índices. ★ Ver a armadilha das chaves em 6.3.

**Passo 2 — Deduplicar.**
Normalizar (minúsculas, espaços colapsados, pontuação final removida) e agrupar idênticas. Guardar, para cada legenda distinta: o texto, os índices de frame onde ocorreu, e a contagem.
**Justificativa:** com cenas de 1–5s, frames consecutivos são quase idênticos e o BLIP muito provavelmente gera legendas repetidas. Ranquear duplicatas é ruído. E a contagem (`n_occurrences`) é ela mesma um sinal informativo.

**Passo 3 — Calcular a matriz cruzada.**
Chamar `get_caption_frame_sims` com as legendas **distintas** e as features de frame, capturando o **segundo** valor de retorno (`ALL_SIMS`), de shape `[n_distinct, N_frames]`.

**Passo 4 — Calcular os quatro sinais** para cada legenda distinta (4.2–4.5).

**Passo 5 — Ordenar** pelo critério configurado (padrão `scene_score`), decrescente.

**Passo 6 — Coletar as keywords.**
Substantivos e verbos de **todas** as legendas de **todos** os frames, via `tree_utils.get_nouns_verbs` com o spaCy — exatamente como o `QMPropGenerator` faz (linha 135-139).
**Justificativa:** as keywords alimentam o ramo GloVe da busca. Coletá-las de todos os frames (e não só da vencedora) preserva a riqueza que essa via precisa. Esse era o argumento central a favor da Alternativa 1 no nosso alinhamento, e ele continua valendo.

**Passo 7 — Montar a proposta única.**
```
st = 0.0
ed = duration
cap = ranking[0].texto                    ← a legenda do topo
caps = [c.texto for c in ranking[:K]]     ← as K primeiras (K configurável)
keys = keywords deduplicadas
ranking = [ {texto, self_score, scene_score, consensus, n_words, n_occurrences, frames}, ... ]
```

O campo `cap` cumpre o contrato do `build_tree_meta`. O campo `ranking` é diagnóstico, sobrevive no `proposals.json` e é ignorado pelo `tree_meta`.

---

# PARTE 6 — Casos de borda (verificados)

## 6.1 ★ N = 0 — cenas com menos de 1 segundo QUEBRAM o pipeline

`viddataset.py:47` faz `for i in range(int(duration))`. Verificado:

| duração | frames | legendas |
|---|---|---|
| 0.7s, 0.9s | **0** | **0** |
| 1.0 – 1.9s | 1 | 1 |
| 2.0 – 2.9s | 2 | 2 |
| 5.0s | 5 | 5 |

Com zero frames, `np.stack([], axis=0)` (linha 60) levanta `ValueError: need at least one array to stack` — e essa linha está **fora do try/except**, que só protege o `ffprobe`. **A construção inteira cai.**

**Isso está diretamente na sua faixa de durações (1–5s).** Qualquer clipe de 0,x segundos derruba o processo.

**Decisão:** filtrar cenas com `duration < 1.0` **na fronteira** (no `make_annos.py`), não dentro do componente. Justificativa: quando o `WholePropGenerator` executa, o dano já ocorreu três etapas antes. É o mesmo princípio *fail-fast* que já discutimos — validar o barato antes de investir no caro.

O componente ainda assim tratará `n_distinct == 0` defensivamente, emitindo uma proposta vazia com aviso, em vez de estourar.

## 6.2 N = 1 — o caso mais comum

Se as durações estiverem espalhadas em 1–5s, cerca de **25% das cenas terão exatamente uma legenda**, e todas as de 1,0–1,9s terão. Não há ranking a fazer: a única legenda vence.

**Decisão:** caminho curto explícito — todos os sinais recebem valor neutro, `ranking` tem um elemento. Sem cálculo de matriz.

## 6.3 ★ As chaves de `frame_captions` mudam de tipo entre execuções

Descoberta verificada, e é um **bug latente do repositório** que afeta o `QMPropGenerator`:

- **1ª execução (sem cache):** `BlipCapGener.py:34` faz `res['frame_captions'][id] = ...` com `id` **inteiro** vindo do `enumerate`.
- **2ª execução (com cache):** `BaseCapGen.__init__` carrega do `.jsonl`, e JSON converte chaves em **strings**.

E `QMPropGener.py:133` faz `metas['frame_captions'][str(max_idx)]` — sempre com `str()`.

Prova:
```
1a execucao (chaves int): KeyError '1'   <-- QUEBRA
2a execucao (chaves str): OK
```

**Ou seja: o `QMPropGenerator` falha na primeira execução e funciona na segunda.** Provavelmente nunca foi notado porque os autores rodavam a legendagem separadamente antes.

**Decisão de projeto:** o `WholePropGenerator` será **agnóstico ao tipo da chave** — normalizará os índices antes de usar. É defesa barata contra um defeito real que você certamente encontraria.

## 6.4 Legendas todas idênticas

Cenário provável em cena estática de 2–3s. Após a dedup, `n_distinct == 1` → cai no caso 6.2. O campo `n_occurrences` registra que houve consenso total — informação útil na inspeção.

---

# PARTE 7 — Integração: os arquivos exatos

## 7.1 Adição 1 — `pipeline/propgenerator/WholePropGener.py` (novo)

```python
@REGISTER_PROPGEN(["whole"])
class WholePropGenerator(BasePropGen):
    def __init__(self, cfg, models) -> None: ...
    def __call__(self, vid_list, captions, scores, all_frame_features): ...
```
Espelha o `__init__` do `QMPropGenerator` (mesmos modelos) e salva no mesmo lugar (`cfg.exp_dir` + `cfg.proposals_file`).

## 7.2 Adição 2 — `pipeline/propgenerator/__init__.py` (1 linha)

```python
from .base import *
from .QMPropGener import *
from . import WholePropGener      # registra sem poluir o namespace (ver 2.2)
```

## 7.3 Adição 3 — `config/cfg.py:76` (1 string)

```python
proposal_generator: str = field(
    default="qm",
    metadata={"choices": ["qm", "whole"]}      # ← "whole" adicionado
)
```
**Necessário:** o `HfArgumentParser` **impõe** os `choices` (verificado em `hf_argparser.py:150`, que copia o metadata para o argparse). Sem essa adição, `--proposal_generator whole` é rejeitado.

## 7.4 Adições de configuração (opcionais, com defaults seguros)

| Campo | Default | Papel |
|---|---|---|
| `whole_rank_by` | `"scene_score"` | qual sinal ordena o ranking |
| `whole_max_caps` | `1` | quantas legendas vão para `caps` (o índice de busca) |
| `whole_dedup` | `True` | deduplicar antes de ranquear |

**Nota sobre `whole_max_caps`:** o default `1` preserva o comportamento clássico (uma legenda por cena). Dado o achado 3.4 (agregação por `max`, ganho grátis), **aumentá-lo é seguro** — mas é decisão sua, e vale tomá-la *depois* de olhar o ranking.

## 7.5 Uso

```bash
proposal_generator=whole    # no construct.sh
```

---

# PARTE 8 — O que deliberadamente NÃO faremos

Anti-over-engineering explícito. Cada item foi considerado e recusado:

| Não faremos | Por quê |
|---|---|
| Detecção de fronteiras (kernel de Foote) | Suas cenas já são o corte. Seria trabalho inútil e arriscado. |
| Modificar `compute_capframe_scores` | Quebraria OCP e invalidaria caches. Recomputar custa nada (3.2). |
| Corrigir a assinatura da ABC | Modificaria arquivo existente e quebraria o `QMPropGenerator` (2.3). |
| Introduzir um modelo novo (CLIP, BLIP-2) | Toda a maquinaria necessária já está carregada. |
| Fundir legendas (gerar uma legenda "resumo") | Exigiria um LLM e sairia do escopo. Talvez depois, com dados na mão. |
| Eleger um critério vencedor | Sem referências, seria fingir conhecimento (4.6). |
| Aprender pesos para combinar os sinais | Exigiria supervisão. E com N≤5 e ~25% de cenas com N=1, não há sinal suficiente. |
| Deduplicação semântica (por embedding) | Dedup exata basta como primeiro passo. Semântica adiciona um limiar arbitrário. |

---

# PARTE 9 — Plano de validação (sem referências)

**Passo 0 — Antes de tudo, medir a distribuição.** Um script de ~10 linhas sobre o `meta/captions/{collection}_blip.jsonl` responde:
- Quantas cenas têm N=1? (nenhuma decisão a tomar)
- Qual a mediana de legendas **distintas** por cena?

★ **Se a maioria tiver 1–2 legendas distintas, o problema é quase inexistente** e a resposta correta é "pegue qualquer uma". Este passo pode tornar boa parte deste projeto desnecessária — e descobrir isso **antes** de codificar é exatamente o objetivo de fazer o relatório primeiro.

**Passo 1 — Concordância entre critérios.** Em quantas cenas `argmax(self_score) == argmax(scene_score)`? Se for ~90%, os critérios convergem e a escolha é irrelevante. Se divergirem muito, vale olhar *quais* casos.

**Passo 2 — Inspeção manual de ~30 cenas.** Com as colunas lado a lado. É aqui que você decide o critério — e é o método mais rigoroso disponível sem referências.

**Passo 3 — Diagnóstico do viés genérico.** Se o topo por `scene_score` for sistematicamente a legenda mais curta (coluna `n_words`), o problema de 4.3 está presente e vale considerar um desempate por especificidade.

---

# PARTE 10 — Decisões que dependem da sua aprovação

1. **Ordenação padrão** — proponho `scene_score` (justificado em 4.3), com a ressalva honesta do viés genérico. Aceita?
2. **`whole_max_caps` default** — proponho `1` (conservador), sabendo que aumentar é ganho grátis (3.4). Prefere já indexar todas as distintas?
3. **Onde vive o ranking** — proponho `proposals.json` (via chaves extras ignoradas pelo `build_tree_meta`). Prefere um arquivo separado?
4. **Filtro de cenas < 1s** — proponho no `make_annos.py` (fail-fast), não no componente. Concorda?
5. **A ordem de execução** — proponho rodar o **Passo 0 da Parte 9 primeiro**, com as legendas que você já tiver, antes de escrever o componente. Se a maioria das cenas tiver 1–2 legendas distintas, o escopo encolhe muito.

---

*Esta especificação projeta um componente que isola exatamente o que o seu caso precisa do Passo 3 do RefCap — a seleção de legenda — descartando a detecção de fronteiras, que é inútil para vídeos que já são o corte desejado. O desenho respeita a arquitetura existente (três adições, zero modificações, via o registry que o repositório já provê), corrige o critério de seleção enviesado (usando a matriz cruzada que o próprio RefCap computa e descarta), e recusa deliberadamente eleger um critério vencedor enquanto não houver evidência dos seus dados. Sete descobertas desta revisão estão marcadas com ★, das quais três mudaram o desenho: a matriz cruzada descartada, a agregação por máximo que torna múltiplas legendas ganho grátis, e a inconsistência de tipo das chaves que quebra o `QMPropGenerator` na primeira execução.*
