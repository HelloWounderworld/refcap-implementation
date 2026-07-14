# RefCap — Vetorização e Arquitetura de Busca
## Relatório Técnico Detalhado: Sentence-BERT, GloVe e a Estrutura de Recuperação

---

> **O que é este documento.** A dissecação teórica e prática dos dois processos de vetorização do RefCap (Sentence-BERT e GloVe) e da arquitetura de busca. Cada afirmação vem com **o trecho exato do código** (arquivo:linha) e a **formalização matemática** correspondente.
>
> **Três entregas:**
> 1. **§§1–3** — Onde e como ocorre a vetorização, com a matemática formal de cada um.
> 2. **§4** — A arquitetura de busca: **corrige uma hipótese comum** (a busca *não* é serial nem em árvore).
> 3. **§5** — **Um defeito matemático real** encontrado no ramo GloVe, verificado empiricamente.

---

## 1. Visão geral: dois paradigmas de vetorização

O RefCap vetoriza texto de **duas formas teoricamente opostas**, e entender essa oposição é entender por que ele funde os dois sinais.

| | **Sentence-BERT** | **GloVe** |
|---|---|---|
| **Natureza** | **Inferência** (forward pass de Transformer) | **Table lookup** (consulta a matriz) |
| **Contexto** | **Contextual**: $\mathbf{h}_i = f(t_1,\dots,t_L)$ | **Estático**: $E_g(w)$ fixo, sempre |
| **Unidade** | Frase inteira | Palavra isolada |
| **Dimensão** | 768 | 300 |
| **Vocabulário** | Aberto (sub-palavras) | **Fechado** (OOV é descartado) |
| **Captura** | Composição, ordem, sintaxe | Presença de conceitos |
| **Custo** | $O(L \cdot d^2)$ — caro | $O(1)$ — trivial |
| **Espaço treinado para** | O **cosseno** (objetivo siamês) | Log-coocorrência |

**A tese que justifica usar os dois:** eles **falham de formas complementares**. O SBERT dilui termos raros na média da frase; o GloVe (via `Max_Mean`) os captura sem diluição. É a clássica combinação **densa + léxica** da Recuperação de Informação — e a ablação do paper confirma: Full (18.31) > Sent (16.18) > Word (14.09).

---

## 2. Sentence-BERT: os momentos exatos e a matemática

### 2.1 O método — `capTree.py:95-98`

Existe **um único** ponto onde o Sentence-BERT roda:

```python
def encode_caps(self, caps: List[str], show_progress_bar=False):
    cap_features = self.cap_feature_model.encode(caps, ...)   # ← ★ O FORWARD PASS
    cap_features = torch.tensor(cap_features).to(self.cfg.device)
    return cap_features
```

Ele é chamado **exatamente duas vezes** em todo o sistema de recuperação.

### 2.2 Momento 1 — Vetorização do ÍNDICE (`capTree.py:114`)

```python
def compute_tree_feature(self, resume_video_names):
    ...
    self.build_relations()                              # ← achata a árvore em self.caps
    self.cap_features = self.encode_caps(self.caps, show_progress_bar=True)   # ★ [Np, 768]
    self.key_features = self.encode_keys(self.keys)
```

**O que entra:** `self.caps`, a lista plana de **todas as legendas de todos os eventos do corpus**, construída em `build_relations` (`capTree.py:71`):
```python
self.caps += node['caps']     # concatena as legendas de cada evento
```

**Quando:** uma vez, no bootstrap. É o forward pass **caro** (milhares de legendas).

### 2.3 Momento 2 — Vetorização da QUERY (`MixPipe.py:68`)

```python
desc_features = self.captree.encode_caps(descs)                            # ★ [Nq, 768]
sent_sims = sent_util.cos_sim(desc_features, self.captree.cap_features)    # [Nq, Np]
```

**É o mesmo método.** Isto é **essencial**: índice e query precisam viver no **mesmo espaço vetorial** para o cosseno ser semanticamente válido. Usar encoders diferentes produziria vetores incomparáveis.

**Quando:** por lote de queries. É o forward pass **barato** (uma frase curta).

### 2.4 A matemática do Sentence-BERT

Seja $c$ uma legenda (string), $E_s$ o encoder, $d = 768$.

**Passo 1 — Tokenização.** $c \mapsto (t_1, \dots, t_L)$, sub-palavras (WordPiece/BPE).

**Passo 2 — Contextualização (self-attention).** Cada camada do Transformer computa:

$$\text{Attn}(Q,K,V) = \mathrm{softmax}\!\left(\frac{QK^\top}{\sqrt{d_k}}\right)V$$

com $Q = HW_Q$, $K = HW_K$, $V = HW_V$ projeções dos estados ocultos $H$. Empilhando $L$ camadas, obtêm-se $\mathbf{h}_1, \dots, \mathbf{h}_L \in \mathbb{R}^d$.

> **A propriedade crucial:** $\mathbf{h}_i = f(t_1, \dots, t_L)$, **não** $f(t_i)$. O vetor de cada token depende de **todos os outros**. É isto que torna o embedding **contextual** — "banco" em *"sentei no banco"* difere de "banco" em *"fui ao banco sacar"*.

**Passo 3 — Pooling.** Os vetores de token viram um vetor de frase (mean pooling):

$$\mathbf{v}_c = \frac{1}{L}\sum_{i=1}^{L} \mathbf{h}_i \in \mathbb{R}^{768}$$

**Passo 4 — O espaço métrico treinado (SBERT ≠ BERT).** Este é o ponto teórico central. O modelo foi *fine-tuned* com **arquitetura siamesa** (Reimers & Gurevych, 2019), minimizando sobre pares $(a,b)$ com rótulo de similaridade $y$:

$$\mathcal{L} = \sum_{(a,b)} \left( \cos(\mathbf{v}_a, \mathbf{v}_b) - y \right)^2$$

> **Por que isto importa:** num BERT **cru**, o cosseno entre embeddings é uma medida **ruim** de similaridade semântica (o espaço não foi otimizado para isso). O SBERT resolve por construção: o espaço é **explicitamente treinado para que o cosseno corresponda à similaridade semântica**. É *por isso* que o RefCap usa SBERT, e não BERT.

**Passo 5 — A similaridade (Eq. 6 do paper).** Com $\mathbf{q} = E_s(T)$ (query) e $\mathbf{c}_h^i = E_s(c_h^i)$ (legenda do evento):

$$S_s(T, c_h^i) = \frac{\mathbf{q}^\top \mathbf{c}_h^i}{\|\mathbf{q}\|\,\|\mathbf{c}_h^i\|}$$

**Na forma matricial que o código executa** (`MixPipe.py:69`), com $\hat{\mathbf{Q}} \in \mathbb{R}^{N_q \times 768}$ e $\hat{\mathbf{C}} \in \mathbb{R}^{N_p \times 768}$ normalizados por linha:

$$\boxed{\;\mathbf{S} = \hat{\mathbf{Q}}\,\hat{\mathbf{C}}^\top \in \mathbb{R}^{N_q \times N_p}\;}$$

**Uma única multiplicação de matrizes** produz **todas** as $N_q \times N_p$ similaridades. (Guarde isto — é a chave da §4.)

---

## 3. GloVe: os momentos exatos e a matemática

### 3.1 Uma assimetria que a leitura superficial esconde

O GloVe é acessado em **dois lugares diferentes, com mecanismos distintos**.

### Momento A — Vetorização do ÍNDICE (`capTree.py:100-103`)

```python
def encode_keys(self, keys: List[str]):
    key_features = self.key_feature_model.vectors[[self.key_feature_model.stoi[w] for w in keys]]
    #              └── matriz GloVe ──┘  └── stoi: palavra → índice da linha ──┘
    return key_features.to(self.cfg.device)
```

**Isto NÃO é inferência — é indexação de matriz.** `stoi` (*string-to-index*) mapeia a palavra à linha; `vectors[i]` recupera o vetor. Nenhuma rede roda. Custo: $O(1)$ por palavra.

**Pré-requisito silencioso** (`capTree.py:78`):
```python
node['keys'] = list(filter(lambda x: x in self.key_feature_model.stoi, node['keys']))
```
Palavras **fora do vocabulário** são descartadas *antes* — porque `stoi[w]` daria `KeyError`. **Nomes próprios, jargão técnico e termos recentes desaparecem silenciosamente.**

### Momento B — Vetorização da QUERY (`MixPipe.py:33-52`)

Aqui a assimetria: o lookup e a similaridade estão **fundidos** na mesma função.

```python
def compute_similarities(self, word_list_1, word_list_2):
    def get_vecs(word_list):
        tmp_list = []
        for word in word_list:
            if word not in self.vecs.stoi:      # ← filtro OOV
                continue
            tmp_list.append(self.vecs.stoi[word])
        return self.vecs.vectors[tmp_list].numpy()    # ← ★ VETORIZAÇÃO (lookup)

    vec1 = get_vecs(word_list_1)     # palavras da QUERY
    vec2 = get_vecs(word_list_2)     # palavras do ÍNDICE  ← re-vetorizadas!
    dot = np.dot(vec1, vec2.T)                                        # [N1, N2]
    sims = dot / np.sqrt(np.sum(vec1**2)) / np.sqrt(np.sum(vec2**2))  # ← ⚠️ ver §5
```

Chamado em `MixPipe.py:82`:
```python
key_sims = self.compute_similarities(word_list_1=all_descs_keys, word_list_2=self.captree.keys)
```

> **Nota de ineficiência:** o `MixPipe` **re-vetoriza as keywords do índice a cada lote de queries** (`vec2 = get_vecs(self.captree.keys)`), ignorando o `key_features` já computado em `compute_tree_feature`. É trabalho redundante — mas barato (lookup), por isso passa despercebido.

### 3.2 De onde vêm as keywords da query (`MixPipe.py:79`)

```python
descs_keys = list(map(lambda x: tree_utils.extract_keys(self.nlp, ..., x, 10), descs))
```
O spaCy extrai **substantivos e verbos**, filtra pelo vocabulário GloVe e limita a 10 (`tree_utils.py:43-48`). Ex.: *"a person opens a door"* → `['person', 'door', 'open']`.

### 3.3 A matemática do GloVe

**O treino (offline, feito pelos autores do GloVe — Pennington et al., 2014).** Seja $X_{ij}$ o número de vezes que a palavra $j$ ocorre no contexto de $i$. O objetivo minimizado é:

$$J = \sum_{i,j=1}^{V} f(X_{ij}) \left( \mathbf{w}_i^\top \tilde{\mathbf{w}}_j + b_i + \tilde{b}_j - \log X_{ij} \right)^2$$

com $f$ ponderando (amortecendo) coocorrências muito frequentes.

> **A intuição teórica:** o objetivo força $\mathbf{w}_i^\top \tilde{\mathbf{w}}_j \approx \log P(j \mid i)$ — o **produto escalar aproxima o log da probabilidade de coocorrência**. A propriedade emergente é que **razões** de coocorrência viram **diferenças vetoriais**, dando origem à aritmética vetorial ($\text{rei} - \text{homem} + \text{mulher} \approx \text{rainha}$).

**A vetorização em si (o que o RefCap faz).** É uma função **determinística e estática**:

$$\boxed{\;E_g : \mathcal{V} \to \mathbb{R}^{300}, \qquad E_g(w) = \mathbf{G}[\,\text{stoi}(w),\, :\,]\;}$$

onde $\mathbf{G} \in \mathbb{R}^{400000 \times 300}$ é a matriz pré-treinada. **É uma consulta a uma tabela, não um cálculo.**

**Três consequências teóricas:**
1. **Não-contextual** — $E_g(w)$ é idêntico em qualquer frase; a polissemia colapsa ("banco" tem um só vetor).
2. **Vocabulário fechado** — $w \notin \mathcal{V} \Rightarrow$ descartado (perda silenciosa).
3. **Sem composição** — um conjunto de palavras não tem ordem nem estrutura sintática.

### 3.4 A similaridade e a agregação `Max_Mean` (Eqs. 7–8)

**Nível palavra (Eq. 7):**
$$S_w(k^T_l, k) = \big\langle E_g(k^T_l),\, E_g(k) \big\rangle$$

**Agregação `Max_Mean` (Eq. 8):**
$$S_w(T, K_h^i) = \frac{1}{|K_T|} \sum_{k^T_l \in K_T} \max_{k \in K_h^i} \big\{ S_w(k^T_l, k) \big\}$$

**A leitura teórica em duas etapas:**
- **MAX interno** — para cada palavra da query, encontre a palavra do evento que melhor casa. O paper enquadra isso como **Multiple Instance Learning**: o evento é um "saco" de palavras, e basta *uma* casar bem.
- **MÉDIA externa** — mede **cobertura** (*recall*): um evento que casa com **todas** as palavras da query vence um que casa perfeitamente com **uma só**. É por isso que `Max_Mean` supera `Max_Max` na ablação (+1.19).

Tecnicamente, isto é um ***soft term matching*** — uma versão "amaciada" do casamento exato de termos, onde "cachorro" pode casar com "cão" via proximidade no espaço GloVe.

---

## 4. A arquitetura de busca — **corrigindo a hipótese "serial / em árvore"**

> **Hipótese comum (e incorreta):** *"pela estrutura da `tree.json`, a busca parece ser feita em série, percorrendo a árvore."*
>
> **A realidade é o oposto**, e a correção envolve dois mal-entendidos.

### 4.1 Correção 1 — **A árvore é destruída antes da busca**

O `build_relations` (`capTree.py:47-93`) faz um BFS que **achata** a estrutura em listas planas:

```python
self.caps = []                 # ← TODOS os eventos do corpus, numa lista só
self.keys = []                 # ← TODAS as keywords, concatenadas
self.cap_to_nodeid = []        # ← mapeamento de VOLTA (índice → nó original)
```

> **Depois disto, não existe mais árvore.** Existe uma **lista plana** de $N_p$ eventos e uma **matriz** $[N_p, 768]$. A "busca pela árvore" **não acontece** — nem em série, nem em paralelo. A árvore é apenas o **formato de serialização em disco**; em memória, ela vira uma **tabela**.

O `cap_to_nodeid` é o preço do achatamento: permite **voltar** do índice na matriz para o evento real (`st`, `ed`, `vid_name`, legenda) — `MixPipe.py:144-151`.

### 4.2 Correção 2 — **A busca é uma multiplicação de matrizes**

Toda a busca de sentença acontece em **uma linha** (`MixPipe.py:69`):

```python
sent_sims = sent_util.cos_sim(desc_features, self.captree.cap_features)  # [Nq, Np]
```

Matematicamente: $\mathbf{S} = \hat{\mathbf{Q}}_{[N_q \times 768]} \cdot \hat{\mathbf{C}}^\top_{[768 \times N_p]}$

**Todas as $N_q \times N_p$ comparações são computadas de uma vez**, num único kernel de GPU. **Não há loop sobre eventos. Não há loop sobre queries.**

### 4.3 A medição empírica (paralelo vs serial)

Comparação executada (50 queries × 20.000 eventos = **1 milhão de comparações**):

| Abordagem | Tempo |
|---|---|
| **Matricial** (o que o RefCap faz) | **1,4 s** (CPU de sandbox) |
| **Serial** (loop duplo — a hipótese) | **~20 s** (estimado) |

**~14× mais rápido** — e isto em **CPU**. Em **GPU**, a diferença seria de **duas a três ordens de magnitude**: a multiplicação de matrizes é o caso de uso canônico do hardware (milhares de núcleos executando produtos escalares simultaneamente).

### 4.4 Onde HÁ loops seriais (e por que não importam)

Sendo preciso: **existem** loops no `MixPipe` — mas **nenhum itera sobre a comparação query×evento**.

| Linha | Loop | Itera sobre | Custo | Crítico? |
|---|---|---|---|---|
| 59 | `for batch in dataloader` | Lotes de queries | $N_q / \text{bsz}$ | Não |
| **70** | `for vid_name, cap_ids` | **Vídeos** (agregação max) | $O(N_v)$ | **Ineficiência menor** |
| 141 | `for i in range(Nq)` | Queries (**só formatar a saída**) | $O(N_q)$ | Não |
| 146 | `for node_id, score` | Top-1000 (só formatação) | Trivial | Não |

O loop da **linha 70** é o único vetorizável (é uma agregação `max` por grupo, que um `scatter_max` faria em paralelo). Mas ele itera sobre **vídeos** ($N_v$), não sobre o produto $N_q \times N_p$. **É uma ineficiência de segunda ordem.**

### 4.5 Análise de complexidade completa

Seja $N_q$ = queries no lote, $N_p$ = eventos no corpus, $N_v$ = vídeos, $E = 768$, $L$ = tokens por frase.

| Etapa | Complexidade | Paralelizado? | Onde |
|---|---|---|---|
| Codificar índice (**bootstrap**) | $O(N_p \cdot L \cdot E^2)$ | Sim (batched) | `capTree.py:114` |
| Codificar query | $O(L \cdot E^2)$ | Sim | `MixPipe.py:68` |
| **Similaridade de sentença** | $O(N_q \cdot N_p \cdot E)$ — **1 matmul** | **Sim (GPU)** | `MixPipe.py:69` |
| Similaridade de keywords | $O(N_{kq} \cdot N_{kt} \cdot 300)$ — 1 matmul | Sim | `MixPipe.py:82` |
| Agregação `Max_Mean` | $O(N_q \cdot N_p \cdot \text{maxQN} \cdot \text{maxPN})$ | Sim (tensor ops) | `MixPipe.py:101-104` |
| Agregação por vídeo | $O(N_v)$ — **loop serial** | **Não** | `MixPipe.py:70` |
| `topk` | $O(N_p \log k)$ | Sim | `MixPipe.py:139` |

> **⚠️ O gargalo real NÃO é tempo — é MEMÓRIA.** A matriz `S` do ramo de keywords (`MixPipe.py:90`) tem forma $[N_q \cdot \text{maxQN},\; N_p \cdot \text{maxPN}]$. Para $N_p = 20.000$ e 50 keywords/evento, isso é $\sim 10^6$ colunas — **gigabytes de VRAM**. É *por isso* que `eval_query_bsz` existe: para **trocar tempo por memória**.

### 4.6 Por que o achatamento é a decisão correta

*Pergunta natural:* por que não manter a árvore e **podar hierarquicamente** (achar o vídeo primeiro, depois o evento dentro dele)?

**Resposta teórica:** numa **busca exaustiva**, o achatamento é **estritamente superior**. A poda hierárquica só compensa quando permite **evitar** comparações — mas introduz o risco de **perder o resultado certo** (se o vídeo for descartado no primeiro nível, seus eventos nunca são avaliados). Com $N_p$ na casa das dezenas de milhares, **comparar tudo custa uma matmul** — mais barato *e* mais correto que a travessia.

É a mesma razão pela qual sistemas de busca vetorial modernos (FAISS, ScaNN) usam **índices planos** quando o corpus cabe na memória, e só recorrem a estruturas hierárquicas (HNSW) na escala de bilhões de vetores.

---

## 5. ⚠️ O defeito matemático no ramo GloVe (achado verificado)

### 5.1 O que o código faz vs. o que deveria fazer

Em `compute_similarities` (`MixPipe.py:49-50`):

```python
sims = dot / np.sqrt(np.sum(vec1**2)) / np.sqrt(np.sum(vec2**2))
```

Matematicamente, isto é:

$$\text{sims} = \frac{\mathbf{V}_1 \mathbf{V}_2^\top}{\|\mathbf{V}_1\|_F \cdot \|\mathbf{V}_2\|_F}$$

onde $\|\cdot\|_F$ é a **norma de Frobenius da matriz inteira** — um **único escalar global**.

Mas o **cosseno correto** (o que a Eq. 7 do paper especifica) normaliza **por par de vetores**:

$$\cos\big(\mathbf{v}_1^{(i)}, \mathbf{v}_2^{(j)}\big) = \frac{\mathbf{v}_1^{(i)\top}\mathbf{v}_2^{(j)}}{\big\|\mathbf{v}_1^{(i)}\big\| \cdot \big\|\mathbf{v}_2^{(j)}\big\|}$$

**São coisas diferentes.**

### 5.2 Demonstração numérica (executada)

Com $\mathbf{v}_1 = [3,0,0]$ e $\mathbf{v}_2 = [1,0,0]$ — **vetores idênticos em direção**, logo cosseno verdadeiro = **1.0**:

| | Resultado |
|---|---|
| **Fórmula do código** | **0.3464** ❌ |
| **Cosseno correto** | **1.0000** ✓ |

### 5.3 O impacto no RANKING (o que de fato importa)

Um contra-argumento razoável seria: *"o escalar global é o mesmo para toda a matriz, então não altera a ordem"*. **Testei isso**, com vetores de normas heterogêneas (como são os do GloVe real — palavras frequentes têm normas maiores):

```
Ranking pelo CÓDIGO  : [2 1 0 5 7 6 4 3]
Ranking pelo COSSENO : [1 2 0 5 7 6 3 4]
→ Rankings IDÊNTICOS? False        ← ⚠️ O RANKING MUDA
```

**Por que o ranking muda:** a divisão por um escalar global é uma transformação monotônica e, sozinha, *não* alteraria a ordem. **Mas o viés de norma permanece embutido no produto escalar bruto.** O cosseno **cancela** a norma dos vetores; o `dot` puro **não**:

| palavra | norma | `dot` (código) | cosseno verdadeiro |
|---|---|---|---|
| 1 | 1.0 | +1.93 | **+0.287** |
| 2 | 2.0 | **+3.03** | +0.225 |

A palavra 2 tem `dot` maior **só porque sua norma é maior** — mas o cosseno verdadeiro mostra que a palavra 1 está **direcionalmente mais próxima**. **O código inverte o ranking.**

### 5.4 A consequência teórica

O ramo de keywords **não está medindo similaridade de cosseno** — está medindo o **produto escalar escalado por uma constante global**. Isso significa:

- **Palavras com vetores GloVe de norma maior** (tipicamente as **mais frequentes** no corpus de treino do GloVe) ficam **sistematicamente enviesadas para cima**.
- O sistema tende a favorecer casamentos com palavras comuns em detrimento de palavras raras mas **direcionalmente mais próximas** — exatamente o oposto do que se quer numa busca (termos raros são os mais discriminativos).

**Atenuação parcial:** o `normalize_min_max` posterior (`MixPipe.py:129`) e a fusão com o ramo de sentença suavizam o impacto final. Mas o **viés de norma entre palavras permanece**, e o ranking do ramo GloVe diverge do que a Eq. 7 do artigo especifica.

**Classificação:** é uma **divergência real entre o código e o paper**, na mesma categoria do bug de colisão de sentinela que encontramos no denoiser (`window.py:27,33`). Não invalida o método, mas é um defeito de implementação que o artigo não descreve.

---

## 6. Síntese

**Vetorização — dois paradigmas opostos e complementares:**

- **Sentence-BERT** (`capTree.py:96`, chamado em `capTree.py:114` e `MixPipe.py:68`): inferência contextual via Transformer. O espaço é **treinado com objetivo siamês para que o cosseno meça similaridade semântica**. Captura composição e ordem. Custo $O(L \cdot d^2)$.

- **GloVe** (`capTree.py:101` e `MixPipe.py:42`): **table lookup** estático sobre uma matriz pré-treinada em coocorrências globais. Não-contextual, vocabulário fechado, sem composição. Captura presença de conceitos. Custo $O(1)$.

- **A fusão** (Eq. 9) é a clássica combinação **densa + léxica** da Recuperação de Informação, e a ablação confirma sua superioridade.

**Busca — nem serial, nem em árvore:**

- A árvore é **achatada** em listas planas (`build_relations`) e **deixa de existir** em memória.
- A busca inteira é **uma multiplicação de matrizes** que computa **todas** as comparações query×evento simultaneamente. ~14× mais rápido que serial em CPU; ordens de magnitude em GPU.
- Os loops existentes iteram sobre **vídeos** (agregação) ou **formatam a saída** — nunca sobre o produto $N_q \times N_p$.
- **O gargalo é memória, não tempo** (a matriz densa do ramo de keywords).

**Um defeito real:** a normalização em `compute_similarities` usa a **norma de Frobenius global** em vez do **cosseno por par**, introduzindo viés de norma e **alterando o ranking** — verificado empiricamente.

---

*Próximo passo sugerido:* um scratchpad que **instrumenta** a busca sobre o seu corpus real, medindo tempo e memória de cada etapa (encode, matmul de sentença, matriz de keywords, `topk`), para você ver empiricamente onde os recursos vão — e, se quiser, quantificar o impacto do defeito da §5 no seu ranking.
