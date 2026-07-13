# RefCap — Relatório de Evidências: Inferência na Recuperação
## Cada afirmação → o trecho exato do código → a asserção testável

---

> **O que é este documento.** Um relatório **verificável**. Cada afirmação que fiz sobre o `retrieve.py` está aqui ancorada no **trecho exato do código** (arquivo:linha), para você abrir em paralelo e confirmar por conta própria. E como você vai construir testes, cada afirmação também vem com a **asserção testável** correspondente, a camada (T0/T1/T2) e a técnica.
>
> **Como usar.** Abra o código ao lado. Cada §X.Y traz: *(a)* a afirmação, *(b)* o trecho-prova, *(c)* como confirmar você mesmo, *(d)* o teste que a trava.
>
> **Duas famílias de teste que você mencionou.** As §§2–5 cobrem os **testes de caracterização** (travar o comportamento atual do que você NÃO vai mudar). A §7 cobre os **testes de viabilidade** (scratch — provar que sua implementação vai funcionar antes de escrevê-la).

---

## 1. Sumário das afirmações a verificar

| # | Afirmação | Trecho-prova | Camada |
|---|---|---|---|
| A1 | O BLIP é **carregado mas NUNCA invocado** na recuperação | `capTree.py:24-25` (só atribuição) | T1 |
| A2 | Há **exatamente 2 forward passes**, ambos do sentence-transformer | `capTree.py:96` (via 114 e MixPipe:68) | T1 |
| A3 | O GloVe **não é forward pass** — é table lookup | `capTree.py:101` | T0 |
| A4 | O `ts` (gabarito) é **inerte ao scoring** | `MixPipe.py:61, 160` vs `139` | T1 |
| A5 | O corpus pesquisável é **acoplado às consultas** (bidirecional) | `capTree.py:108` + `dataset.py:38` | T1 |
| A6 | O `MixPipe` exige do dataset apenas um **contrato mínimo** (duck typing) | `MixPipe.py:71,149,171` + `__getitem__` | T1 |
| A7 | O `normalize_min_max` **destrói a magnitude absoluta** (sem limiar de confiança) | `MixPipe.py:128-129`, `sim_utils.py:30` | T0 |
| A8 | Não há treino (`no_grad`, sem `.backward()`) | `retrieve.py:278` | T0 |
| A9 | O índice codificado **não é cacheado** em disco | `capTree.py:105-116` (sem guard de path) | T1 |

---

## 2. A1 — O BLIP é carregado mas NUNCA invocado

### A afirmação
Na recuperação, o BLIP ocupa VRAM sem executar. Você pode não carregá-lo.

### O trecho-prova (`pipeline/treebuilder/capTree.py`, linhas 22–25)
```python
self.cap_feature_model = models["sentence_transformer"]   # ← USADO (linha 96)
self.key_feature_model = models["glove_model"]            # ← USADO (linha 101)
self.itm_feature_model = models["blip_itrtv_model"]       # ← ATRIBUÍDO E NUNCA USADO
self.itm_feature_processor = models["blip_itrtv_processor"]  # ← IDEM
```

### Como confirmar você mesmo
```bash
# Busque QUALQUER uso do BLIP em todo o caminho de recuperação:
grep -rn "itm_feature_model\|blip_itrtv" pipeline/retrievepipe/ pipeline/treebuilder/ retrieve.py
```
**Resultado esperado:** apenas as **duas linhas de atribuição** acima (`capTree.py:24-25`). Nenhuma linha chamando `self.itm_feature_model(...)`. Isso prova que ele é **atribuído, nunca invocado**.

Confirmação complementar — as únicas funções de `sim_utils` usadas na recuperação:
```bash
grep -rn "sim_utils\." pipeline/retrievepipe/
```
**Resultado:** só `normalize_min_max` (MixPipe:128,129,133,134; KeyPipe:93,113). As funções que *usam* o BLIP (`get_caption_frame_sims`, `_get_frame_features`) **não aparecem**.

### O teste que trava isto (T1 — integração com mock)
**Técnica:** injete um mock no lugar do BLIP que **lança exceção se for chamado**. Se a recuperação roda sem erro, o BLIP nunca foi invocado.
```python
class ExplodingModel:
    def __call__(self, *a, **kw):  raise AssertionError("BLIP foi INVOCADO!")
    def __getattr__(self, n):      raise AssertionError(f"BLIP.{n} acessado!")

models = {..., "blip_itrtv_model": ExplodingModel(), ...}
# rodar a recuperação → se passar, A1 está provado
```
> **Nota:** o `__getattr__` explosivo é forte demais (o `__init__` do CapTree *atribui* o objeto, o que é legal). Use um mock que só explode no `__call__`.

---

## 3. A2/A3 — Onde exatamente ocorre a inferência (forward pass)

### A afirmação
Há **exatamente dois** forward passes de rede neural, ambos do **mesmo** sentence-transformer, ambos fazendo `texto → vetor`. O GloVe **não** é forward pass.

### Os trechos-prova

**O único método que roda um forward pass** (`capTree.py:95-98`):
```python
def encode_caps(self, caps: List[str], show_progress_bar=False):
    cap_features = self.cap_feature_model.encode(caps, ...)   # ← FORWARD PASS (sentence-transformer)
    cap_features = torch.tensor(cap_features).to(self.cfg.device)
    return cap_features
```

**Ponto 1 — codificação do ÍNDICE** (`capTree.py:114`, dentro de `compute_tree_feature`):
```python
self.cap_features = self.encode_caps(self.caps, show_progress_bar=True)  # [Np, E]
```
Roda **uma vez**, no setup, sobre **todas** as legendas do corpus. É o forward pass **caro**.

**Ponto 2 — codificação da QUERY** (`MixPipe.py:68`, dentro de `retrieval`):
```python
desc_features = self.captree.encode_caps(descs)   # ← O PONTO QUE VOCÊ QUER
```
Roda **por lote de consultas**. É o forward pass **barato** — e **é exatamente aqui que a sua query vira vetor**.

**O contraste — GloVe NÃO é forward pass** (`capTree.py:100-103`):
```python
def encode_keys(self, keys: List[str]):
    key_features = self.key_feature_model.vectors[[self.key_feature_model.stoi[w] for w in keys]]
    #              └─────── indexação de tabela: stoi[palavra] → linha da matriz ───────┘
```
Isto é **table lookup** (busca numa matriz pré-computada), não inferência. Nenhuma rede roda.

### Como confirmar você mesmo
```bash
# Todas as chamadas de encode_caps (os únicos forward passes):
grep -rn "encode_caps\|\.encode(" pipeline/ | grep -v "def encode"
```
**Resultado esperado:** `capTree.py:114` (índice), `MixPipe.py:68` (query), e a definição em `capTree.py:96`. Mais nada.

### O teste que trava isto (T1 — spy de contagem)
**Técnica:** envolva `cap_feature_model.encode` com um espião que **conta chamadas e registra o input**.
```python
calls = []
real_encode = model.encode
def spy_encode(texts, **kw):
    calls.append(len(texts))     # quantos textos codificados
    return real_encode(texts, **kw)
model.encode = spy_encode

# Asserções:
# 1. após compute_tree_feature → len(calls)==1, calls[0]==Np (todo o corpus)
# 2. após retrieval de 1 batch → len(calls)==2, calls[1]==tamanho_do_batch
```
Isto **quantifica a assimetria de custo** (índice: milhares de textos; query: 1 texto) e prova que só há dois pontos.

---

## 4. A4/A5 — Gabarito inerte + o acoplamento (as duas verdades que sustentam sua adaptação)

### A4 — O `ts` NUNCA entra no scoring

**Trecho-prova (`MixPipe.py`):**
```python
# linha 61 — o ts é DESEMPACOTADO do batch:
desc_names, desc_ids, gt_vid_names, gt_vid_ids, descs, starts, ends = batch

# linhas 128-139 — o SCORING: só sentença + palavra. NENHUM starts/ends aqui:
esm_sims = sent_sims * ratio + key_sims_per_proposal * (1 - ratio)     # ← 130
topk_cap_sims, topk_cap_ids = torch.topk(esm_sims, max_vcmr_prop_cnts, dim=1)  # ← 139

# linha 160 — o ts é apenas ECOADO na saída:
gt_ts=[starts[i].item(), ends[i].item()],
```

**Como confirmar:**
```bash
grep -n "starts\|ends" pipeline/retrievepipe/MixPipe.py
```
**Resultado esperado:** aparece **só nas linhas 61 (desempacote) e 160 (eco)**. Nunca em `esm_sims`, `topk`, `cos_sim` ou qualquer cálculo.

**Teste (T1):** rode a mesma query duas vezes com `ts` dummy **diferentes** (`[0,0]` vs `[99,99]`) → as `predictions` devem ser **idênticas**. Se mudarem, A4 é falsa.

### A5 — O acoplamento BIDIRECIONAL (a armadilha que você precisa desarmar)

**Trecho-prova 1 — a árvore é podada pelas consultas (`capTree.py:105-110`):**
```python
def compute_tree_feature(self, resume_video_names):
    new_tree_meta = {}
    for vid_name, meta in self.tree_meta.items():
        if vid_name in resume_video_names:      # ← resume = vídeos DAS CONSULTAS
            new_tree_meta[vid_name] = copy.deepcopy(meta)
    self.tree_meta = new_tree_meta              # ← A ÁRVORE É SUBSTITUÍDA pela podada
```
E quem passa `resume_video_names` (`retrieve.py:274`):
```python
captree.compute_tree_feature(resume_video_names=test_dataset.vid_name_to_id.keys())
#                                               └── vem das CONSULTAS ──┘
```

**Trecho-prova 2 — as consultas são filtradas pela árvore (`dataset.py:38-39`):**
```python
if captree_meta is not None and item['vid_name'] not in captree_meta:
    continue                                    # ← descarta a consulta
```

**Conclusão:** corpus pesquisável ≡ {vídeos da árvore} ∩ {vídeos das consultas}.

**Como confirmar:** leia as duas linhas acima. Depois rastreie: quem popula `vid_name_to_id`? (`dataset.py:55`, a partir do `vcmr.jsonl`).

**Teste (T1 — o teste crítico da sua adaptação):**
```
Setup:  árvore com vídeos {A, B, C}; consultas mencionando só {A}
Asserção (comportamento ATUAL): após compute_tree_feature, a árvore tem SÓ {A}
                                → B e C são INBUSCÁVEIS
Asserção (comportamento DESEJADO, após sua adaptação):
                                a árvore mantém {A,B,C} → todos buscáveis
```
Este teste é o que **prova que sua correção funcionou**.

---

## 5. A6 — O contrato mínimo do dataset (a chave da sua implementação)

### A afirmação
O `MixPipe` **não exige um `DataSet4Test` real**. Ele exige um objeto que satisfaça um contrato mínimo. Isso é *duck typing*, e é o que te permite injetar suas queries **sem tocar no núcleo**.

### O trecho-prova — TODOS os usos de `test_dataset` no `MixPipe`
```bash
grep -n "test_dataset\." pipeline/retrievepipe/MixPipe.py
```
**Resultado (verificado):**
```
71:   vid_id = test_dataset.vid_name_to_id[vid_name]
149:  vid_id = test_dataset.vid_name_to_id[vid_name]
171:  video2idx = test_dataset.vid_name_to_id
```
**Apenas `vid_name_to_id`** — três usos, todos do mesmo atributo.

Mais o que o `DataLoader` exige (`MixPipe.py:56`):
```python
dataloader = DataLoader(test_dataset, batch_size=..., num_workers=..., ...)
```
→ o objeto precisa de `__getitem__` e `__len__`.

E o formato que `__getitem__` deve devolver (`dataset.py:74-77`, e como é desempacotado em `MixPipe.py:61`):
```python
return desc_name, desc_id, vid_name, vid_id, desc, ts[0], ts[1]   # 7 elementos, nesta ordem
```

### **O CONTRATO COMPLETO** (o que seu `QueryDataset` precisa implementar)
```python
class QueryDataset:
    def __init__(self, queries: List[str], tree_meta: dict):
        # ⚠️ A CORREÇÃO: vid_name_to_id vem da ÁRVORE, não das queries
        self.vid_name_to_id = {v: i for i, v in enumerate(tree_meta.keys())}
        self.queries = queries

    def __getitem__(self, i):
        # 7 elementos na ordem exata; ts/vid dummy (são inertes — A4)
        return (f"q{i}", i, "DUMMY", 0, self.queries[i], 0.0, 0.0)

    def __len__(self):
        return len(self.queries)
```
**Isso é tudo.** Nenhuma outra propriedade do `DataSet4Test` é usada pelo `MixPipe`.

### O teste que valida o contrato (T1 — o teste de viabilidade da sua ideia)
Passe o `QueryDataset` acima ao `MixPipe.retrieval()` **real** (com modelos mockados) e asserte que ele devolve `(vr_indices, vcmr_res_dict)` sem erro, e que `vcmr_res_dict["VCMR"][0]["predictions"]` tem o formato `[vid_id, st, ed, score, vid_name, cap]`. **Se este teste passa, sua implementação é viável.**

---

## 6. A7/A8/A9 — Três verdades operacionais

### A7 — Sem limiar de confiança (o min-max destrói a magnitude)
**Trecho (`MixPipe.py:128-129` + `sim_utils.py:30`):**
```python
sent_sims = sim_utils.normalize_min_max(sent_sims, dim=1)   # ← por QUERY (dim=1)
# sim_utils.py:30:
def normalize_min_max(t, dim):
    return (t - t.min(dim, keepdim=True)[0]) / (t.max(dim, keepdim=True)[0] - t.min(dim, keepdim=True)[0])
```
**Consequência:** o melhor evento de **cada query** vira 1.0, **mesmo que seja péssimo**. O sistema **nunca diz "não encontrei"**.

**Teste (T0 — lógica pura):** alimente `normalize_min_max` com um tensor cujos valores absolutos são todos baixos (ex.: `[0.01, 0.02, 0.03]`) → a saída contém `1.0`. **Documenta o defeito.**

**Implicação para você:** se quiser um limiar "não achei", capture `sent_sims`/`key_sims` **antes** da linha 128 (os scores brutos).

### A8 — Não há treino
**Trecho (`retrieve.py:278`):**
```python
with torch.no_grad():
    eval_epoch(infer_pipeline, test_dataset, cfg)
```
**Confirmação:** `grep -rn "backward\|optimizer\|\.train()" retrieve.py pipeline/retrievepipe/` → **nada**. Inferência pura.

### A9 — O índice codificado NÃO é cacheado
**Trecho (`capTree.py:105-116`):** `compute_tree_feature` **não tem** guard `if os.path.exists(...)`. Contraste com a construção, que **tem** (ex.: `compute_frame_features`).
**Consequência:** cada startup do `retrieve.py` **re-codifica todo o corpus**. Para um serviço, é desperdício.
**Sua otimização:** serialize `cap_features`/`key_features` em `.pt` e carregue prontos. **Fora do núcleo** — no seu código.

---

## 7. Plano de testes (as duas famílias que você mencionou)

### 7.1 Testes de CARACTERIZAÇÃO (travar o que você NÃO vai mudar)
Objetivo: se você (ou um update do upstream) quebrar o comportamento atual, o teste avisa.

| Teste | Camada | Prova | Asserção |
|---|---|---|---|
| `test_blip_never_invoked` | T1 | A1 | Mock explosivo no BLIP → recuperação roda sem erro |
| `test_two_forward_passes` | T1 | A2 | Spy em `encode` → exatamente 2 chamadas (índice + query) |
| `test_glove_is_lookup` | T0 | A3 | `encode_keys` não chama `.encode()`; só indexa `vectors` |
| `test_ts_inert_to_scoring` | T1 | A4 | `ts` dummy diferente → predições idênticas |
| `test_minmax_destroys_magnitude` | T0 | A7 | Valores baixos → saída contém 1.0 |
| `test_no_training` | T0 | A8 | Grep/AST: sem `backward`/`optimizer` no caminho |
| `test_output_schema` | T1 | — | `predictions[i]` tem 6 campos na ordem certa |

### 7.2 Testes de VIABILIDADE (scratch — provar sua implementação ANTES de escrevê-la)
Objetivo: confirmar que sua ideia funciona, sem construir o serviço inteiro.

| Scratch | O que prova | Como |
|---|---|---|
| `scratch_duck_typing.py` | **Que o `QueryDataset` funciona** | Passa o objeto mínimo (§5) ao `MixPipe.retrieval()` real (modelos mockados) → sai `predictions` |
| `scratch_corpus_decoupling.py` | **Que a armadilha foi desarmada** | Árvore {A,B,C} + query mencionando só {A}; com `vid_name_to_id` da ÁRVORE → B e C permanecem buscáveis |
| `scratch_no_blip.py` | **Que o serviço roda sem carregar BLIP** | `models` sem `blip_itrtv_model` → `CapTree.__init__` quebra? (spoiler: sim, pelo `models["blip_itrtv_model"]` — você precisará passar um placeholder) |
| `scratch_index_cache.py` | **Que o cache de índice é válido** | Codifica → salva `.pt` → recarrega → asserta que os vetores são idênticos |
| `scratch_raw_scores.py` | **Que dá para extrair scores brutos** | Intercepta antes da linha 128 → tem magnitude absoluta |

> **⚠️ Achado antecipado (o `scratch_no_blip`):** o `CapTree.__init__` faz `models["blip_itrtv_model"]` **incondicionalmente** (`capTree.py:24`). Se você omitir a chave, dá `KeyError` — mesmo o BLIP nunca sendo usado. **Solução no seu código:** passe `{"blip_itrtv_model": None, "blip_itrtv_processor": None, ...}`. Como nunca é invocado (A1), `None` basta. **Este é exatamente o tipo de coisa que o scratch revela antes de você perder tempo.**

---

## 8. Roteiro de leitura em paralelo (para você confirmar tudo)

Abra os arquivos nesta ordem, com este relatório ao lado:

1. **`retrieve.py:262-279`** (`start_inference`) — veja os 4 objetos nascerem. Confirme A8 (linha 278).
2. **`pipeline/treebuilder/capTree.py:14-45`** (`__init__`) — confirme A1 (linhas 24-25: BLIP atribuído).
3. **`capTree.py:95-116`** (`encode_caps`, `encode_keys`, `compute_tree_feature`) — confirme A2 (forward pass, linha 96/114), A3 (lookup, linha 101), A5 (poda, linha 108), A9 (sem cache).
4. **`dataset/dataset.py:37-56` e `74-77`** — confirme A5 (filtro, linha 38) e A6 (o contrato, linha 77).
5. **`pipeline/retrievepipe/MixPipe.py:54-75`** — confirme A2 (linha 68: **o ponto que você quer**) e A6 (linha 71).
6. **`MixPipe.py:128-164`** — confirme A7 (linhas 128-129), A4 (linha 139 vs 160), e o formato de saída (linhas 152-162).

---

## 9. Síntese: as 3 verdades que habilitam sua implementação

1. **O ponto de inferência da query é `MixPipe.py:68`** (`encode_caps(descs)`), e o modelo é o **sentence-transformer** — não o BLIP. É leve e é o que você mantém residente.
2. **O `MixPipe` aceita qualquer objeto que satisfaça o contrato mínimo** (`vid_name_to_id` + `__getitem__`/`__len__` devolvendo 7 campos) — então você injeta suas queries **sem tocar no núcleo** (A6).
3. **O gabarito é inerte** (A4) e **o BLIP nunca roda** (A1) — então `ts` dummy e BLIP `None` são seguros.

**O que resta fazer:** desarmar o acoplamento (A5) populando `vid_name_to_id` a partir da **árvore**, e (opcional) cachear o índice (A9). Ambos no *seu* código.
