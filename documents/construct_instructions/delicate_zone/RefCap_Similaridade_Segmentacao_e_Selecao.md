# RefCap — Similaridade, Segmentação e Seleção
## A Análise do Código, a Estrutura de Dependência, e os Defeitos Verificados

---

> **O que é este documento.** A análise do mecanismo que vai da matriz de similaridade até a escolha da legenda no RefCap: o que `calculate_similarities` computa, como `capframe_scores` é calculado, quem depende de quem, e quais defeitos essa cadeia contém.
>
> **A pergunta que o originou.** *"O processo de escolha das legendas depende fortemente da segmentação, ou a relação está invertida? Qual o papel da matriz de similaridade nisso?"*
>
> **Base matemática.** Os conceitos (embeddings, matriz de Gram, argmax, normalização L2) estão no documento companheiro `Fundamentos_Embeddings_Gram_e_Argmax.md`. Aqui eles são **aplicados**, não redefinidos.
>
> **Companheiro executável.** `LAB9_refcap_similaridade_verificacoes.py` — verificações R1–R5. Para a matemática pura, `LAB8`.

---

## Protocolo de verificação

| Marca | Significa |
|---|---|
| **[L]** | **Lido no código** — arquivo e linha citados; confira abrindo o arquivo |
| **[V]** | **Verificado numericamente** — rode o `LAB9` (ou `LAB8` onde indicado) |
| **[D]** | **Demonstrado** — prova no texto |
| **[C]** | **Citado da literatura** — fonte nomeada |
| **[J]** | **Julgamento meu** — opinião de engenharia, não fato |

**Escopo desta análise.** Repositório `BUAAPY/RefCap`, versão obtida por `git clone` do branch padrão. Todos os números de linha referem-se a essa versão. Exemplos numéricos são **sintéticos** e estão rotulados — nenhum dado real do RefCap foi executado nesta análise.

---

# PARTE I — O QUE O CÓDIGO COMPUTA

## 1. `calculate_similarities` — os três modos

**[L]** `pipeline/propgenerator/QMPropGener.py:28–42`

```python
28:  def calculate_similarities(self, sentences, capframe_scores, frame_features):
29:      if self.cfg.prop_sim_type == "vis":
31:          sims = sim_util.cos_sim(frame_features, frame_features)
32:      else:
33:          with torch.no_grad():
34:              embeddings = self.txt_sim_model.encode(sentences)
35:              txt_sims = sim_util.cos_sim(embeddings, embeddings).to(self.cfg.device)
36:              if self.cfg.prop_sim_type == 'txt':
37:                  sims = txt_sims
38:              elif self.cfg.prop_sim_type == 'it':
39:                  sims = txt_sims * capframe_scores[None, :] * capframe_scores[:, None]
42:      return sims
```

**O objeto produzido:** uma matriz `[N × N]` de **auto-similaridade**, onde N é o número de legendas (= número de frames = duração inteira em segundos).

| modo | compara | usa legendas? | usa frames? |
|---|---|---|---|
| `vis` **[L:29,31]** | frame × frame | **não** | sim |
| `txt` **[L:36,37]** | legenda × legenda | sim | não |
| `it` (default) **[L:38,39]** | legenda × legenda, ponderado | sim | sim (como peso) |

**[L]** O default é `it` — `config/cfg.py:86–92`, `prop_sim_type: str = field(default="it", ...)`.

**O que `cos_sim` faz. [L]** `utils/sim_utils.py:8`, com o retorno em `:28` — `torch.mm(a_norm, b_norm.transpose(0,1))`. Ou seja: normaliza e multiplica. É o produto escalar de vetores unitários, que é o cosseno (Fundamentos, I.5).

**O modo `it` decifrado.** `capframe_scores[None,:]` é um vetor-linha `[1,N]`; `capframe_scores[:,None]` é um vetor-coluna `[N,1]`. O produto dos dois é o **produto externo** `[N,N]` com entrada `(i,j) = s[i]·s[j]`. Logo:

```
sims[i][j] = txt_sims[i][j] · s[i] · s[j]
```

A leitura: *"só confio na similaridade entre as legendas i e j na medida em que ambas são confiáveis"*.

## 2. ★ O modo `it` **não** é um erro de mistura de espaços — correção de uma afirmação minha

Eu afirmei antes, nesta análise, que multiplicar `txt_sims` (espaço do sentence-transformer) por `capframe_scores` (espaço do BLIP) seria "comparar embeddings de espaços diferentes". **Testei e a afirmação estava errada.** Registro a correção aqui porque um relatório que esconde o próprio erro não serve.

**[D/V-R2a] A operação é `D K D`.** Com `D = diag(s)`, a linha 39 é algebricamente idêntica a `D · txt_sims · D`. Verificado.

**[D/V-R2b] Teorema:** se K é PSD, então `D K D` é PSD.
> **Prova.** `x'(DKD)x = (Dx)'K(Dx) ≥ 0`, pois K é PSD. ∎

**[J] A distinção que eu havia perdido:** o erro real seria calcular `cos(vetor_modeloA, vetor_modeloB)` — tratar **coordenadas** de espaços distintos como comparáveis. Usar um **escalar** de outro modelo como **peso** sobre uma matriz de Gram é uma reponderação de kernel, operação legítima e comum. São coisas categoricamente diferentes.

**[J] O que resta de crítica, e é fraco:** a escolha de multiplicar por `s[i]·s[j]` — em vez do mínimo, da média geométrica, ou de uma função mais suave — é arbitrária, e não há calibração entre as escalas dos dois modelos. Mas "arbitrário" não é "incorreto". O defeito real está em outro lugar (Parte III).

## 3. `capframe_scores` — a cadeia completa

### 3.1 De onde vêm os vetores

**[L]** `utils/sim_utils.py:34–55` (`_get_frame_features`) e `:58–75` (`_get_caption_features`).

| lado | caminho | linha da projeção |
|---|---|---|
| **frames** | `sim_model.vision_model(pixel_values)` → `[CLS]` → `vision_proj` → L2 | `:52` |
| **legendas** | `sim_model.text_encoder(input_ids, attention_mask)` → `[CLS]` → `text_proj` → L2 | `:74` |

O `[:, 0, :]` em ambas as linhas é a seleção do **token `[CLS]`** — o primeiro da sequência.

**★ [L] Uma precisão que importa: a cabeça ITM nunca é invocada.** Busquei por `itm_head`, `encoder_hidden_states`, `itm_score` em todo o repositório: **nenhuma ocorrência**. O `text_encoder` é chamado **sem** `encoder_hidden_states`, ou seja, **sem cross-attention**.

**[C] Por que isso é relevante.** BLIP (Li et al., ICML 2022) tem três objetivos de pré-treino:
- **ITC** (*Image-Text Contrastive*) — ativa os **encoders unimodais**; alinha os espaços encorajando **pares casados a terem representações similares em contraste com pares não-casados**;
- **ITM** (*Image-Text Matching*) — ativa o **text encoder com cross-attention**; é uma **classificação binária** via uma cabeça linear (*ITM head*) sobre a feature multimodal;
- **LM** — o decoder de geração.

O que o código do RefCap calcula é o **caminho ITC** (encoders unimodais + projeções + cosseno). **Não** é o *score* ITM.

**[J] Consequência de nomenclatura.** O modelo carregado é `blip-itm-base-coco` **[L:** `config/cfg.py:48`**]**, via `BlipForImageTextRetrieval` **[L:** `utils/model_utils.py:30`**]**, e o texto de ajuda do `prop_sim_type` diz *"similarities multiplied with blip itm-scores"* **[L:** `config/cfg.py:88`**]**. Mas o que se computa é a similaridade **contrastiva**, não o score da cabeça ITM. É imprecisão de nomenclatura no repositório — não um bug, mas induz ao erro quem lê a config antes do código.

### 3.2 A matriz cruzada e a diagonal

**[L]** `utils/sim_utils.py:78–92`:
```python
90:      ALL_SIMS = cap_features @ frame_features.t()     # matriz COMPLETA [N,N]
91:      sims = ALL_SIMS.diag()                            # só a DIAGONAL
92:      return sims, ALL_SIMS                             # devolve AS DUAS
```

`ALL_SIMS[i][j]` = cosseno entre a legenda *i* e o frame *j*. É uma **matriz de Gram cruzada** (Fundamentos, II.9).

**[V-R1a,R1b]** Reproduzido no LAB9 com d=4, incluindo a conferência de uma entrada termo a termo.

**Por que a diagonal.** A legenda *i* foi **gerada a partir do frame *i***, então o par casado é `(legenda_i, frame_i)`, que cai na posição `(i,i)`. **[J]** Isso é **convenção de indexação**, não propriedade algébrica — embaralhe uma das listas e os pares casados saem da diagonal.

**★ [V-R1d] A diagonal não é necessariamente o máximo da sua linha.** Verificado no exemplo sintético do LAB9: a legenda 0 casa melhor com o frame 2 do que com o próprio frame 0. Nada garante que `ALL[i][i] = max_j ALL[i][j]`.

### 3.3 A normalização min-max

**[L]** `pipeline/constructpipe/base.py:110–113`:
```python
110:     sims, _ = sim_utils.get_caption_frame_sims(...)   # ← ALL_SIMS DESCARTADO
111:     if self.cfg.itm_norm:
112:         sims = sim_utils.normalize_min_max(sims, dim=0)
113:     all_scores[video_name] = sims.cpu()
```

**[L]** `normalize_min_max` em `utils/sim_utils.py:30` — `(t − min)/(max − min)`. **[L]** `itm_norm` default `True` — `config/cfg.py:82–85`.

**★ [L] O achado da linha 110.** A função devolve **dois** valores; o segundo — a matriz cruzada completa `[N,N]` — é **descartado no underscore**. Das N² similaridades computadas, apenas N (a diagonal) sobrevivem.

**[V-R1e]** No exemplo sintético, a amplitude bruta de 0.0053 é esticada para 1.0 pelo min-max. **[V-R1f]** O argmax não muda — teorema da invariância monótona (Fundamentos, III.15; verificado em `LAB8-D3`).

---

# PARTE II — A ESTRUTURA DE DEPENDÊNCIA

## 4. O rastreio: quem consome `sims`

**[L]** Rastreei **todas** as ocorrências de `sims` e de `capframe_scores` dentro de `generate_proposal` (`QMPropGener.py:69–141`):

| linha | uso de `sims` |
|---|---|
| `:70` | `VID_LEN = sims.shape[-1]` — só para obter N |
| `:86` | `scores = F.conv2d(sims, weight=weight, ...)` — **o único uso funcional** |

**Não há outra ocorrência.** A seleção da legenda usa exclusivamente `capframe_scores`:
```python
128:     scores = capframe_scores[st_idx:ed_idx]     # ← nota: `scores` é REATRIBUÍDO aqui
130:     max_idx = torch.argmax(scores).item()
131:     max_idx += st_idx
133:     cap = metas['frame_captions'][str(max_idx)]['cap']
```

**[J] Observação de qualidade:** a linha 128 reatribui o nome `scores`, que até a linha 90 designava os scores de fronteira (saída da convolução). Dois significados para o mesmo nome no mesmo escopo — *shadowing*. Funciona, mas é uma mina para refatoração.

## 5. A resposta: a dependência é unidirecional e estreita

```
capframe_scores ──┬──► pondera a matriz (L39) ──► Foote (L86) ──► fronteiras ──► FAIXAS
                  │                                                                │
                  └──► argmax DENTRO da faixa (L128-130) ◄─────────────────────────┘
                                    │
                                    ▼
                            legenda escolhida (L133)
```

**A seleção depende da segmentação?** Sim — **mas apenas através da faixa**. A segmentação define o *domínio* `[st_idx, ed_idx]` sobre o qual o argmax opera. Nada mais.

**A dependência é invertida?** Não. É estritamente **segmentação → seleção**. A seleção nunca influencia as fronteiras.

**A seleção depende *puramente* da segmentação?** **Não** — e o "puramente" é o ponto. Ela depende de **duas entradas independentes**: a segmentação define **onde olhar**; o `capframe_scores` define **quem vence** ali dentro.

**Qual o papel da matriz na seleção?** **Nenhum.** Ela serve exclusivamente à segmentação. O `capframe_scores` é insumo **compartilhado** pelos dois ramos — mas isso é entrada comum, não dependência entre eles.

**[J] O corolário que importa para um caso de uso de "um segmento por vídeo":** com uma faixa única cobrindo o vídeo inteiro, a matriz de similaridade **não tem efeito nenhum** sobre a legenda escolhida. Todo o aparato de `calculate_similarities` e do kernel de Foote torna-se inerte.

## 6. Duas leituras possíveis da mesma matriz

A matriz `[N×N]` admite operadores independentes (Fundamentos, II.12):

| leitura | operador | pergunta |
|---|---|---|
| **local** | kernel de Foote **[C]** (Foote, ICME 2000) | *"ONDE o conteúdo muda?"* |
| **global** | soma/média das linhas | *"QUEM representa o conjunto?"* |

**[J]** O RefCap aplica **apenas a primeira**. A informação de centralidade — que responderia "qual legenda melhor representa o conjunto" — está no mesmo objeto e não é lida.

---

# PARTE III — OS DEFEITOS VERIFICADOS

## 7. Defeito 1 — a matriz cruzada é computada e descartada

**[L]** `sim_utils.py:90-92` computa `ALL_SIMS` completa e a devolve; `constructpipe/base.py:110` a descarta com `_`.

**[J] Por que isso importa.** `ALL_SIMS[i].mean()` responderia *"quão bem a legenda i descreve a cena inteira"* — que é uma pergunta diferente, e possivelmente mais útil, do que a que a diagonal responde. O custo já foi pago (a matriz foi calculada); só o resultado é jogado fora.

**[V-R1f]** No exemplo sintético do LAB9, o critério da diagonal e o da média da linha **divergem** — escolhem legendas diferentes. Isso é uma demonstração de que **os dois critérios não são equivalentes**, não uma medição de qual é melhor.

## 8. Defeito 2 — o viés estrutural da diagonal

**[C]** O objetivo ITC do BLIP treina explicitamente para que **pares casados** tenham alta similaridade e pares não-casados, baixa. Num lote de treino, os pares casados formam a diagonal da matriz de similaridade do lote.

**[J] A inferência que faço a partir disso** — e marco como julgamento, não como fato medido: `capframe_scores[i] = sim(legenda_i, frame_i)` não é uma medição independente, porque a legenda *i* foi **gerada a partir do** frame *i*. O que essa quantidade mede tem uma componente de "quão bem o par legenda-frame se alinha segundo o objetivo de treino do modelo", que não é a mesma coisa que "quão bem essa legenda representa a cena".

**[J] O que eu NÃO posso afirmar:** que esse viés produz escolhas ruins **nos seus dados**. Isso exigiria medir com dados reais e alguma referência — nenhum dos dois foi feito aqui. A afirmação é sobre o que a quantidade *é*, não sobre a magnitude do efeito prático.

## 9. ★ Defeito 3 — o min-max aniquila exatamente uma legenda por vídeo

Este é o defeito mais concreto da cadeia.

**[D] A consequência é aritmética e inevitável:** `normalize_min_max` mapeia o menor valor para **exatamente 0**. Como `itm_norm=True` é o default, **todo vídeo tem exatamente uma legenda com peso zero** (ou mais, sob empate no mínimo).

**[V-R3a]** Exemplo sintético: `[0.88, 0.91, 0.86, 0.93]` → `[0.286, 0.714, 0.000, 1.000]`.

**[V-R3b] E peso zero não rebaixa — anula.** Na matriz `D K D`, a linha **e** a coluna correspondentes ficam inteiramente zeradas. Verificado. A legenda com score bruto 0.86 — a 0.07 da melhor — é **removida da estrutura**, não apenas despriorizada. E o critério para isso é ser a pior **do seu próprio vídeo**, não ser ruim em termos absolutos.

**[V-R3c] Efeito na detecção de fronteiras.** Uma linha/coluna zerada faz aquela legenda parecer totalmente dissimilar de todas as outras — a assinatura que o kernel de Foote procura. No exemplo sintético, o pico da função de novidade **se deslocou** ao aplicar a ponderação.

**[J] A leitura:** o kernel pode detectar uma fronteira onde houve apenas "a legenda de menor score do vídeo". Chamo isso de *fronteira fantasma*. A magnitude do efeito em dados reais não foi medida.

## 10. Defeito 4 — `N=1` produz NaN; `N=2` é degenerado

**[V-R4a]** Com um único elemento, `max == min`, e a fórmula do min-max faz `0/0` → **NaN**.

**[V-R4b]** Com dois elementos, o resultado é **sempre** `[0.0, 1.0]`, independentemente dos valores brutos — verificado com `[0.10, 0.99]` e `[0.881, 0.882]`. A amplitude original é destruída.

**[V-R4c] E o NaN não estoura — propaga.** Toda comparação com NaN é `False` (IEEE 754), então guardas condicionais se comportam como se a condição nunca fosse satisfeita, e `argmax([nan])` retorna 0 sem erro.

**[J] Relevância prática:** `N` é a duração inteira em segundos **[L:** `dataset/viddataset.py:47`, `for i in range(int(duration))`**]**. Logo, cenas entre 1.0s e 1.99s produzem `N=1`, e cenas entre 2.0s e 2.99s produzem `N=2`. Para coleções de clipes curtos, esses dois casos não são raros — são a maioria.

## 11. Defeito 5 — a segmentação é degenerada para N≤5 e destrutiva para N≥6

Reproduzi `generate_proposal` (linhas 85–122) fielmente. Parâmetros **[L:** `config/cfg.py:56, 97–102`**]**: `prop_kernel_width=5`, `min_prop_size=3`, `prop_max_cnt=5`, `prop_min_cnt=2`.

**★ Nota sobre `prop_score_thr` — há dois valores, e ambos são reais.** **[L]** `config/cfg.py:94` traz o default da dataclass, **0.5**; **[L]** `scripts/construct.sh:16` define **0.2** e o passa explicitamente via `--prop_score_thr` (L45). Portanto o valor efetivo depende de como se invoca: **0.2** pelo script distribuído, **0.5** por `python construct.py` sem argumentos. **[V]** Rodei o teste exaustivo com os **dois** — as tabelas abaixo são **idênticas** para ambos, então a conclusão não depende dessa escolha.

**[V-R5a] Teste exaustivo** — todas as ordens de score possíveis:

| N | ordens testadas | segmentos obtidos |
|---|---|---|
| 1 | 1 | sempre 1 |
| 2 | 2 | sempre 1 |
| 3 | 6 | sempre 1 |
| 4 | 24 | sempre 1 |
| 5 | 120 | **sempre 1** |
| 6 | 720 | 1 ou 2 |
| 7 | 5.040 | 1 ou 2 |
| 8 | 40.320 | 1 ou 2 |

**Para N ≤ 5 o resultado é um único segmento cobrindo o vídeo inteiro, independentemente dos scores.** Isso é exaustivo, não amostral.

**A causa** são três travas atuando juntas:
- **[L:93–94]** `if id in [0, VID_LEN-1]: continue` — descarta as duas pontas;
- **[L:101–103]** exige distância ≥ `prop_kernel_width` (5) entre fronteiras;
- **[L:112–113]** absorve para 0 qualquer fronteira a menos de `min_prop_size` (3) do início.

**[V-R5b] Teste aleatório** — 2.000 sorteios por N, scores ~ N(0,1):

| N (≈ duração) | 1 segmento | 2 | 3+ | % que parte a cena |
|---|---|---|---|---|
| 5 | 2000 | 0 | 0 | 0.0% |
| 6 | 1486 | 514 | 0 | 25.7% |
| 8 | 1008 | 992 | 0 | 49.6% |
| 10 | 464 | 1536 | 0 | 76.8% |
| 15 | 42 | 985 | 973 | 97.9% |
| 20 | 3 | 203 | 1794 | 99.8% |
| 30 | 0 | 3 | 1997 | 100.0% |

**[J] A dupla implicação, que é o achado mais útil desta análise:**
- Para vídeos **curtos (≤5s)**, a detecção de fronteiras é **inerte** — o resultado seria idêntico se ela não existisse. E o kernel 11×11 convoluído sobre uma matriz 5×5 enxerga majoritariamente *padding*, o que torna os scores de fronteira pouco informativos.
- Para vídeos **de 6s em diante**, ela é **ativa e progressivamente agressiva**. Se a premissa for "cada vídeo já é o corte desejado", o comportamento passa a ser **destrutivo** — parte uma cena que se queria inteira.

**[J] Nota sobre os testes aleatórios:** os scores foram sorteados de uma normal, não medidos em dados reais. O teste mostra o comportamento do **algoritmo** sob entradas variadas; ele não estima a frequência de partição nos seus vídeos, que depende da distribuição real dos scores de novidade.

## 12. Defeito 6 — inconsistência de tipo nas chaves de `frame_captions`

**[L]** `pipeline/capgenerator/BlipCapGener.py:34` grava `res['frame_captions'][id]` com `id` **inteiro** (vindo de `enumerate`). **[L]** `pipeline/capgenerator/base.py:33–34` recarrega do `.jsonl`, e JSON converte chaves em **string**. **[L]** `QMPropGener.py:133` indexa sempre com `str(max_idx)`.

**[J]** Isso implica que a primeira execução (sem cache) e as seguintes (com cache) operam sobre tipos de chave diferentes no mesmo campo. Não executei o pipeline real para observar a falha; a inferência vem da leitura das três linhas.

---

# PARTE IV — SÍNTESE

## 13. Respostas diretas às perguntas de origem

| pergunta | resposta | base |
|---|---|---|
| Onde as legendas entram no cálculo? | `QMPropGener.py:34` — `txt_sim_model.encode(sentences)` | **[L]** |
| O que a matriz determina? | apenas as **fronteiras** (o domínio) | **[L:70,86]** |
| A seleção depende da segmentação? | sim, **só** através da faixa | **[L:128–133]** |
| A dependência é invertida? | não — unidirecional | **[L]** |
| Papel da matriz na seleção? | **nenhum** | **[L]** |
| Quem decide a legenda? | `argmax(capframe_scores[faixa])` | **[L:128–130]** |

## 14. Os seis defeitos, com severidade

| # | defeito | tipo | verificação |
|---|---|---|---|
| 1 | `ALL_SIMS` computada e descartada | oportunidade perdida | **[L:110]** |
| 2 | viés estrutural da diagonal | conceitual | **[C]** + **[J]** |
| 3 | min-max aniquila uma legenda/vídeo | **defeito** | **[V-R3]** |
| 4 | `N=1` → NaN; `N=2` degenerado | **defeito** | **[V-R4]** |
| 5 | segmentação inerte (N≤5) / destrutiva (N≥6) | **comportamento crítico** | **[V-R5]** |
| 6 | chaves int vs. str | inconsistência | **[L]** + **[J]** |

## 15. O que esta análise **não** estabelece

Registro explícito dos limites, porque um relatório que não os declara convida à leitura excessiva:

- **Não medi nada em dados reais do RefCap.** Todos os exemplos numéricos são sintéticos e rotulados como tais.
- **Não estabeleci que o critério da diagonal produz escolhas piores** que alternativas. Mostrei que os critérios *diferem* e argumentei *por que* a diagonal tem viés estrutural — a comparação de qualidade exigiria referências que não existem.
- **Não estimei a frequência** com que a partição indevida (Defeito 5) ocorreria numa coleção real; os testes usam scores sorteados, não medidos.
- **Não executei o pipeline** para observar o Defeito 6 em ação; ele decorre da leitura de três linhas.
- **Não avaliei o modo `vis`** além de constatar que existe e não usa legendas.

---

*Análise do mecanismo de similaridade, segmentação e seleção do RefCap. Toda afirmação carrega marca: **[L]** lida no código com arquivo e linha, **[V]** verificada em `LAB9` (ou `LAB8`), **[D]** demonstrada, **[C]** citada com fonte, **[J]** julgamento de engenharia. A conclusão estrutural — a matriz de similaridade serve exclusivamente à segmentação, e a seleção depende dela apenas através do domínio — decorre de um rastreio exaustivo dos usos de `sims` em `generate_proposal`. Inclui a correção de uma afirmação minha anterior sobre o modo `it`, que o teste refutou. A Parte 15 delimita o que a análise não estabelece.*
