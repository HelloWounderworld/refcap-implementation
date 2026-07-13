# RefCap — `retrieve.py` em Detalhe
## Relatório Didático: o que cada etapa faz, e por que ela existe

---

> **O que é este documento.** A dissecação do **Estágio 2 (Recuperação)** do RefCap — não só o `retrieve.py`, mas toda a cadeia que ele aciona (`CapTree`, `DataSet4Test`, `MixPipe`, NMS, avaliação). O `retrieve.py` sozinho é *orquestração*; a substância está nos módulos que ele chama, então eles são tratados aqui como parte inseparável da história.
>
> **Como ler.** As §§1–3 dão o mapa. A §4 é o walkthrough passo a passo do `retrieve.py`. A §5 abre o `MixPipe` (onde a busca de fato acontece). A §6 fecha com o pós-processamento e a avaliação. As §§7–9 são a análise crítica: os achados, as armadilhas e as implicações para a sua adaptação.
>
> **Escopo.** Análise derivada da leitura direta do código do repositório, cruzada com as equações do paper. Dois **achados novos** desta releitura estão marcados em destaque (§7).

---

## 1. A pergunta que o Estágio 2 responde

A construção já rodou e produziu o `tree.json`: um índice em que **cada vídeo virou uma lista de eventos**, e cada evento carrega `(início, fim, legenda, palavras-chave)`.

A recuperação responde: **"dada uma consulta textual, quais eventos do corpus inteiro melhor correspondem a ela?"**

E a virada conceitual que torna isso possível — a tese do RefCap — é: **como o vídeo virou texto, a busca vídeo↔texto virou busca texto↔texto**. Toda a complexidade de alinhar pixels e linguagem foi paga na construção. Aqui, tudo é comparação de embeddings de texto.

Duas tarefas são avaliadas simultaneamente:
- **VCMR** (*Video Corpus Moment Retrieval*): achar o **evento** certo (vídeo + intervalo). É a tarefa principal.
- **VR / PRVR** (*Partially Relevant Video Retrieval*): achar o **vídeo** certo (sem localizar o trecho). É a tarefa secundária, derivada da mesma pontuação.

---

## 2. Vista de voo: as 7 etapas do `retrieve.py`

```
  [tree.json]  +  [consultas (annos/{collection}/vcmr.jsonl)]
        │                        │
        ▼                        ▼
  ┌─────────────────────────────────────────────────────────┐
  │ 1. SETUP        parse config, seed, cria pastas         │
  │ 2. COERÊNCIA    valida construct×retrieve (settings)    │
  │ 3. CARGA        modelos + CapTree + DataSet4Test        │
  │ 4. INDEXAÇÃO    compute_tree_feature (codifica o índice)│
  │ 5. BUSCA        pipeline.retrieval() ← O CORAÇÃO        │
  │ 6. PÓS-PROC     NMS temporal (deduplica sobreposições)  │
  │ 7. AVALIAÇÃO    Recall@K, IoU → metrics.json            │
  └─────────────────────────────────────────────────────────┘
        │
        ▼
  results/retrieve/{collection}/{retrieve_name}/
    ├── metrics.json      ← os números (Recall/IoU)
    └── vcmr_preds.json   ← OS MOMENTOS RECUPERADOS (o que interessa p/ produção)
```

**A distinção mais importante do documento inteiro:** as etapas **1–5 são o *método*** (produzem os momentos). As etapas **6–7 são *medição*** (NMS + métricas). Em um sistema de busca real, você quer 1–5 e pode dispensar 7. Confundir as duas é o erro que faz alguém achar que precisa de gabarito para *buscar* — não precisa; precisa só para *medir*.

---

## 3. As quatro peças que a recuperação monta

| Peça | Arquivo | O que é | Analogia |
|---|---|---|---|
| **`CapTree`** | `treebuilder/capTree.py` | O **índice**: carrega o `tree.json`, achata em listas, e codifica tudo em embeddings | O catálogo da biblioteca, já vetorizado |
| **`DataSet4Test`** | `dataset/dataset.py` | As **consultas** (+ gabarito, para avaliar) | A fila de perguntas dos leitores |
| **`MixPipe`** | `retrievepipe/MixPipe.py` | O **motor de busca**: compara consulta × índice | O bibliotecário que faz o match |
| **`eval_retrieval`** | `standalone_eval/eval.py` | A **régua**: mede se acertou | O avaliador que confere as respostas |

---

## 4. Walkthrough do `retrieve.py`, passo a passo

### Etapa 1 — Setup (`start_inference`, linhas 236–246)

```python
parser = HfArgumentParser(TestArguments)
cfg = parser.parse_args_into_dataclasses()[0]
seed_it(cfg.seed)
eval_res_dir = os.path.join(cfg.res_dir, cfg.retrieve_dir, cfg.collection, cfg.retrieve_name)
os.makedirs(eval_res_dir, exist_ok=True)
if os.path.exists(os.path.join(eval_res_dir, "metrics.json")):
    print("metrics.json already exists, please use another name...")
    return
```

**O que faz:** lê os parâmetros do `retrieve.sh`, fixa a semente (reprodutibilidade) e cria a pasta de resultados.

**Por que existe a checagem de `metrics.json`:** é uma **proteção contra sobrescrita acidental**. Se você já rodou um experimento com o mesmo `retrieve_name`, ele **aborta em vez de sobrescrever**. *Consequência prática:* para re-rodar, mude o `retrieve_name` ou apague a pasta antiga. É a primeira coisa que confunde quem re-executa.

### Etapa 2 — Validação de coerência construção×recuperação (linhas 249–260)

```python
build_settings_path = .../{construct_name}/settings.json
assert os.path.exists(build_settings_path)
shutil.copy(build_settings_path, .../build_settings.json)
check_names = ["collection", "num_samples"]
for name in check_names:
    assert eval_settings[name] == build_settings[name], f"{name} should be same..."
```

**O que faz:** carrega o `settings.json` congelado na construção, **copia-o** para a pasta de resultados, e **valida** que `collection` e `num_samples` batem entre as duas etapas.

**Por que existe (e é importante):** os dois estágios são desacoplados por disco — nada garante, a priori, que você esteja recuperando sobre o índice que pensa. Esta checagem é o **contrato entre os estágios**. Se você construiu com `collection=meu_corpus` e tenta recuperar com `collection=outro`, ele aborta em vez de produzir lixo silenciosamente. A cópia do `build_settings.json` serve à **rastreabilidade**: cada resultado carrega a configuração que o gerou.

> **Implicação direta para a sua adaptação:** o `collection` que você fixou no adapter precisa ser o **mesmo** aqui. Este `assert` é o que te avisa se você errar.

### Etapa 3 — Carga: modelos, índice e consultas (linhas 262–272)

```python
gt_anno_path   = os.path.join(cfg.anno_dir, cfg.collection, cfg.anno_file)   # annos/{col}/vcmr.jsonl
tree_meta_path = .../{construct_name}/tree.json
assert os.path.exists(tree_meta_path)

pretrained_models = load_pretrained_models(cfg)
captree      = CapTree(cfg, tree_meta_path, pretrained_models)
test_dataset = DataSet4Test(gt_anno_path, captree_meta=captree.tree_meta)
```

Três objetos nascem aqui:

**(a) `load_pretrained_models`** — carrega o **sentence-transformer** (codifica legendas e consultas), o **GloVe** (codifica palavras-chave) e o **BLIP-ITM**. Note: no stage `retrieve`, o modelo de *captioning* **não** é carregado (`cap_gen_model = None`) — faz sentido, já não se legenda nada aqui.

**(b) `CapTree(cfg, tree_meta_path, models)`** — o construtor **apenas carrega o `tree.json` em memória** e guarda referências aos modelos. Ele ainda **não codifica nada** (isso é a Etapa 4). Os atributos que serão preenchidos: `caps`, `keys`, `cap_to_nodeid`, `vidname_to_capids`, `nodeid_to_node`, etc.

**(c) `DataSet4Test(gt_anno_path, captree_meta=captree.tree_meta)`** — lê o `vcmr.jsonl` e extrai, por linha: `desc` (a **consulta**), `vid_name` + `ts` (o **gabarito**), `desc_name`/`desc_id` (identificadores).

> **⚠️ O FILTRO OCULTO (`dataset.py:38`).** Aqui está algo que quase ninguém nota:
> ```python
> if captree_meta is not None and item['vid_name'] not in captree_meta:
>     continue
> ```
> O dataset **descarta consultas cujo vídeo não está na árvore**. É um filtro defensivo (não faz sentido perguntar sobre um vídeo não indexado) — mas, junto com a Etapa 4, cria um **acoplamento bidirecional** que é a armadilha central (§7.2).

### Etapa 4 — Indexação: `compute_tree_feature` (linha 274)

```python
captree.compute_tree_feature(resume_video_names=test_dataset.vid_name_to_id.keys())
```

Esta única linha faz **três coisas** (`capTree.py:105-116`), e é a etapa mais densa da recuperação:

**(i) PODA (linhas 106–110)** — filtra a árvore, mantendo **apenas os vídeos que aparecem nas consultas**:
```python
for vid_name, meta in self.tree_meta.items():
    if vid_name in resume_video_names:      # ← resume = os vídeos DAS CONSULTAS
        new_tree_meta[vid_name] = copy.deepcopy(meta)
self.tree_meta = new_tree_meta
```
> **⚠️ ESTA É A ARMADILHA DE ACOPLAMENTO** que venho sinalizando desde a análise de extração. **O corpus pesquisável é definido pelos vídeos que aparecem no arquivo de consultas.** Um vídeo indexado, mas não referenciado por nenhuma consulta, é **removido do índice** — logo, **nunca pode ser retornado**. No benchmark isso é inócuo (toda consulta tem seu vídeo, e o conjunto de vídeos das consultas = o corpus). **Em produção é fatal**: suas consultas não sabem em qual vídeo está a resposta, e se o `vcmr.jsonl` só tiver uma linha por vídeo (como o nosso adapter gera), tudo bem — mas se você alimentar consultas de usuário sem `vid_name` correto, o corpus encolhe ou quebra.

**(ii) ACHATAMENTO — `build_relations()` (linhas 47–93)** — percorre a árvore (BFS) e transforma a estrutura aninhada em **listas paralelas planas**:
- `self.caps` = [legenda do evento 0, legenda do evento 1, ...] — **todos os eventos do corpus, numa lista só**
- `self.keys` = [todas as palavras-chave de todos os eventos, concatenadas]
- `self.cap_to_nodeid` = mapeamento inverso (do índice na lista → o nó original)
- `self.vidname_to_capids` = {vídeo → quais eventos são dele}
- `self.prop_key_cnts` = quantas keywords cada evento tem

**Por que achatar?** Para poder fazer **uma única multiplicação de matrizes** contra todos os eventos do corpus de uma vez, em vez de iterar vídeo a vídeo. É a diferença entre busca vetorizada (rápida) e loop (lento). O `cap_to_nodeid` existe para você conseguir **voltar** do índice na matriz para o evento real (com seu `st`, `ed`, `vid_name`).

**Detalhe importante (linhas 78–79):** as keywords são **filtradas pelo vocabulário do GloVe** (`filter(lambda x: x in self.key_feature_model.stoi, ...)`) e **truncadas** em `max_key_cnt_per_proposal` (50). Palavras fora do GloVe são **silenciosamente descartadas** — uma limitação real (nomes próprios, jargão técnico, termos novos somem).

**(iii) CODIFICAÇÃO (linhas 114–115)** — o momento em que o índice vira números:
```python
self.cap_features = self.encode_caps(self.caps)   # sentence-transformer → [Np, E]
self.key_features = self.encode_keys(self.keys)   # GloVe → [Nk, 300]
```
Depois disto, o índice está **pronto para busca**: uma matriz `[Np, E]` de embeddings de legendas (Np = nº total de eventos no corpus) e uma matriz de embeddings de keywords.

> **Custo:** este é o gargalo de tempo/memória da recuperação. Codificar dezenas de milhares de legendas leva tempo e ocupa VRAM. Mas roda **uma vez**, e depois todas as consultas reusam.

### Etapa 5 — A busca (linha 276–279)

```python
infer_pipeline = get_retrievepipe_class(cfg.retrieve_pipeline)(cfg, captree, models)
with torch.no_grad():
    eval_epoch(infer_pipeline, test_dataset, cfg)
```

O `get_retrievepipe_class` resolve `"mix"` (padrão), `"sent"` ou `"key"` para a classe correspondente. O `torch.no_grad()` desliga o cálculo de gradientes — **não há treino aqui**; é inferência pura (economiza memória e tempo).

O `eval_epoch` (linha 182) chama `pipeline.retrieval(test_dataset)`, que é **onde tudo acontece**. Abrimos isso na §5.

---

## 5. O coração: `MixPipe.retrieval()` — como a busca funciona

Este é o método mais importante da recuperação. Ele processa as consultas **em lotes** (`eval_query_bsz=50`) e, para cada lote, calcula **duas famílias de similaridade** e as **funde**.

### 5.1 O ramo de SENTENÇA (linhas 67–74)

```python
desc_features = self.captree.encode_caps(descs)                          # a consulta vira embedding
sent_sims = sent_util.cos_sim(desc_features, self.captree.cap_features)  # [Nq, Np]  ← consulta × TODOS os eventos
```

**O que faz:** codifica a consulta com o **mesmo** sentence-transformer que codificou as legendas (crucial — precisam viver no mesmo espaço vetorial) e calcula o **cosseno da consulta contra todos os eventos do corpus** de uma vez. O resultado `sent_sims` é uma matriz `[Nq, Np]`: para cada consulta, um score contra cada evento.

**É a Eq. 6 do paper:** $S_s(T, c_h^i) = \langle E_s(T), E_s(c_h^i)\rangle$.

Em seguida (linhas 70–74), a **agregação para nível-vídeo**:
```python
for vid_name, cap_ids in self.captree.vidname_to_capids.items():
    vid_id = test_dataset.vid_name_to_id[vid_name]
    rel_sims = sent_sims[:, cap_ids]          # os eventos DESTE vídeo
    sims = torch.max(rel_sims, dim=1)[0]      # ← MAX sobre os eventos
    sent_scores[:, vid_id] = sims
```
**Por que MAX:** o score de um vídeo é o do seu **melhor evento**. Faz sentido para "relevância parcial" — se *qualquer* trecho do vídeo responde à consulta, o vídeo é relevante. É a Eq. 10 do paper.

### 5.2 O ramo de PALAVRA-CHAVE (linhas 79–124)

Aqui a lógica é mais elaborada. Três passos:

**(a) A consulta vira keywords (linha 79):**
```python
descs_keys = [tree_utils.extract_keys(self.nlp, vocab, x, 10) for x in descs]
```
O spaCy extrai **substantivos e verbos** da consulta, filtra pelo vocabulário do GloVe, e limita a 10. Ex.: *"a person opens a door"* → `['person', 'door', 'open']`.

**Por que substantivos e verbos:** são os portadores de conteúdo semântico. Artigos, preposições e adjetivos são descartados — reduz ruído e o custo da matriz.

**(b) Similaridade palavra-a-palavra (linha 82):**
```python
key_sims = self.compute_similarities(all_descs_keys, self.captree.keys)  # [Nkq, Nkt]
```
Cosseno GloVe entre **cada palavra da consulta** e **cada palavra do índice**. É a Eq. 7.

**(c) A agregação `Max_Mean` (linhas 88–104)** — a parte mais densa do código, e a que implementa a Eq. 8:

O código constrói uma matriz esparsa `S` de forma `[Nq·max_QN, Np·max_PN]` (consultas×palavras vs eventos×palavras), preenche-a por *scatter* (`S[X, Y] = key_sims.reshape(-1)`), e depois faz:

```python
S_perquery_perevent = S.reshape(Nq, max_QN, Np, max_PN).permute(0,2,1,3)  # [Nq, Np, max_QN, max_PN]
S_perquery_maxevent = S_perquery_perevent.max(dim=3)[0]                    # ← MAX sobre as palavras do EVENTO
key_sims_per_proposal = S_perquery_maxevent.sum(dim=2) / descs_keys_cnts   # ← MÉDIA sobre as palavras da CONSULTA
```

**Traduzindo a intuição (isto é o `Max_Mean`):**
1. **MAX interno** — para cada palavra da consulta, encontre a palavra do evento que melhor casa com ela. (*"a palavra 'door' da consulta casa com qual palavra deste evento? A que der o maior score."*) O paper enquadra isso como **Multiple Instance Learning**: o evento é um "saco" de palavras, e basta *uma* casar bem.
2. **MÉDIA externa** — some esses melhores-casamentos sobre **todas** as palavras da consulta e divida pelo número delas. (*"em média, quão bem cada palavra da minha consulta encontrou correspondente neste evento?"*)

**Por que média e não max no nível externo:** a média mede **cobertura** (*recall*) — um evento que casa bem com *todas* as palavras da consulta vence um que casa perfeitamente com *uma só*. É por isso que `Max_Mean` supera `Max_Max` na ablação (+1,19): exigir cobertura é melhor que premiar um único acerto.

O mesmo padrão se repete (linhas 110–124) para agregar ao **nível-vídeo**.

### 5.3 A FUSÃO (linhas 128–135) — a Eq. 9

```python
sent_sims = sim_utils.normalize_min_max(sent_sims, dim=1)                    # normaliza [0,1]
key_sims_per_proposal = sim_utils.normalize_min_max(key_sims_per_proposal, dim=1)
esm_sims = sent_sims * ratio + key_sims_per_proposal * (1 - ratio)           # ← A FUSÃO (α=0.5)
```

**Por que normalizar antes de fundir:** os dois sinais vivem em escalas diferentes (cosseno de sentence-transformer vs média de cossenos GloVe). Somá-los cru daria peso arbitrário a um deles. O **min-max por consulta** (`dim=1`) coloca ambos em [0,1], tornando o `α` um peso interpretável.

**Por que fundir:** os dois ramos capturam coisas diferentes e **complementares** — a sentença captura *composição e ordem* ("*homem abre porta*" ≠ "*porta abre homem*"); as palavras-chave capturam *presença de conceitos* com robustez a paráfrase. A ablação confirma: a fusão (18,31) supera sentença-só (16,18) e palavra-só (14,09).

> **Nota crítica (o defeito do min-max):** normalizar por consulta **destrói a magnitude absoluta**. Uma consulta cuja melhor correspondência no corpus é péssima terá, ainda assim, seu melhor evento normalizado para 1,0. **O sistema nunca diz "não encontrei nada relevante"** — sempre retorna um ranking. Para produção, isso significa que você não tem um limiar de confiança natural; precisaria derivá-lo dos scores *brutos* (pré-normalização).

### 5.4 A seleção e a saída (linhas 138–164)

```python
topk_cap_sims, topk_cap_ids = torch.topk(esm_sims, max_vcmr_prop_cnts, dim=1)   # top-1000 eventos
for i in range(Nq):
    sel_node_ids = self.captree.cap_to_nodeid[sel_cap_ids].tolist()   # ← o mapeamento inverso
    for node_id, score in zip(sel_node_ids, sel_cap_sims):
        node = self.captree.nodeid_to_node[node_id]
        preds.append([vid_id, node['st'], node['ed'], score, node['vid_name'], node['caps'][0]])
```

Aqui o `cap_to_nodeid` **paga a dívida**: converte os índices da matriz de volta para os **eventos reais**, recuperando `st`, `ed`, `vid_name` e a **legenda**.

**O formato de saída — o que você recebe:**
```python
{
  "desc_id": ..., "desc": "a person opens a door",
  "gt_vid_name": ..., "gt_ts": [...],        # ← gabarito, só ECOADO (nunca usado no scoring)
  "predictions": [[vid_id, st, ed, score, vid_name, caption], ...]   # ← OS MOMENTOS
}
```

> **Confirmação decisiva para a sua adaptação:** o gabarito (`gt_vid_name`, `gt_ts`) é **apenas copiado para a saída** (linhas 159–160). Ele **nunca entra no `topk`** (linha 139) nem em qualquer cálculo de score. **O método jamais consome a supervisão** — exatamente o que provamos instrumentando a construção, agora confirmado na recuperação.

---

## 6. Pós-processamento e avaliação

### 6.1 NMS temporal (`eval_epoch`, linhas 204–206)

```python
vcmr_res_dict_nmsed['VCMR'] = post_processing_vcmr_nms(vcmr_res_dict['VCMR'], nms_thd=0.5,
                                                       max_before_nms=1000, max_after_nms=100)
```

**O problema que resolve:** o top-1000 vem cheio de **eventos sobrepostos** do mesmo vídeo (ex.: `[10s–20s]` e `[11s–21s]`, quase idênticos). Sem filtro, o top-10 se enche de duplicatas do mesmo trecho, desperdiçando as posições do ranking.

**Como funciona** (`filter_vcmr_by_nms`, linhas 34–63): agrupa as predições por vídeo; dentro de cada vídeo, aplica *Non-Maximum Suppression* — mantém a de maior score e **descarta** as que se sobrepõem a ela com IoU > 0,5; depois reordena tudo entre os vídeos e corta no top-100.

**Por que é essencial:** é o que faz o top-K conter **momentos distintos**, não variações do mesmo. É pós-processamento padrão em detecção (a mesma ideia do NMS em detecção de objetos).

> **Nota:** o `compute_temporal_iou` (`temporal_nms.py:18`) usa uma união aproximada — o próprio comentário admite *"not the correct union though"*. Impacto pequeno, mas é uma imprecisão real.

### 6.2 Métricas (linhas 208–222)

```python
metrics = eval_retrieval(vcmr_res_dict_nmsed, test_dataset.cap_data, iou_thds=(0.1,0.3,0.5,0.7), ...)
```

**A regra de acerto:** uma predição conta como correta se **(1)** o `vid_name` bate com o gabarito **e (2)** o IoU temporal com o `ts` supera o limiar. Reporta-se **Recall@{1,10,100}** para cada IoU.

**Por que múltiplos IoUs:** medem rigor crescente de localização. IoU=0,1 é "achou o vídeo e chegou perto"; IoU=0,7 é "acertou o intervalo com precisão".

E o **VR** (linhas 189–201): usa `retrieved_video_indices` (o ranking de vídeos) contra `gt_descid_to_vidid`, produzindo R@1/5/10/100 e mAP.

**Saídas finais:**
- `metrics.json` — os números.
- `vcmr_preds.json` — **os momentos recuperados**. É *este* o arquivo que interessa para um sistema de busca.

---

## 7. Achados críticos (o que a análise revelou)

### 7.1 🐛 BUG REAL no `retrieve.py` — `basic_utils` não é importado

Nas linhas 255, 261 e 265, o código chama `basic_utils.load_json(...)` e `basic_utils.save_json(...)`. Mas o topo do arquivo importa apenas:
```python
from utils.basic_utils import save_json     # importa a FUNÇÃO, não o MÓDULO
```
**Não há `import utils.basic_utils as basic_utils`.** Isso deveria causar `NameError: name 'basic_utils' is not defined` ao rodar.

**Por que "funciona" mesmo assim:** por acidente de import transitivo — `pipeline/retrievepipe/base.py` faz `import utils.basic_utils as basic_utils`, e o `from pipeline.retrievepipe import *` (linha 18 do `retrieve.py`) pode arrastar esse nome para o namespace, dependendo dos `__all__`/`__init__`. **É frágil e depende da ordem de import.** Se você reorganizar os imports, quebra. *Recomendação:* adicione `import utils.basic_utils as basic_utils` explicitamente no topo do seu `retrieve.py`.

### 7.2 ⚠️ O acoplamento BIDIRECIONAL corpus↔consultas (a armadilha central)

Dois filtros trabalham em direções opostas e se travam mutuamente:

- **`CapTree.compute_tree_feature` (capTree.py:108)** — poda a **árvore**, mantendo só vídeos que aparecem **nas consultas**.
- **`DataSet4Test.__init__` (dataset.py:38)** — descarta **consultas** cujos vídeos não estão **na árvore**.

**O resultado:** o corpus pesquisável ≡ a interseção {vídeos da árvore} ∩ {vídeos das consultas}. **Em produção isso é um defeito estrutural:** o usuário não sabe em qual vídeo está a resposta, então a consulta não pode "declarar" seu vídeo. Se o `vcmr.jsonl` de consultas não listar todos os vídeos, **o corpus encolhe silenciosamente** — e o `test_dataset.vid_name_to_id[vid_name]` (MixPipe:71, 149) daria `KeyError` para vídeos da árvore ausentes do dataset.

> **Como o nosso adapter interage com isso:** o `make_annos.py` gera **uma linha por vídeo** do seu corpus. Então `resume_video_names` = todos os seus vídeos → a árvore **não é podada**. Funciona. Mas quando você alimentar **consultas reais de usuário**, precisará garantir que `vid_name_to_id` contenha **todos** os vídeos da árvore (não os das consultas) — é a **Cirurgia** que fica para a fase de recuperação.

### 7.3 Sem limiar de confiança (o min-max destrói a magnitude)

`normalize_min_max(dim=1)` normaliza **por consulta**. O melhor evento sempre vira 1,0, mesmo que seja péssimo em termos absolutos. **O sistema nunca retorna "nada relevante"** — sempre há um ranking. Para produção, um limiar de "não encontrei" precisaria vir dos scores **brutos**.

### 7.4 Custo de memória do ramo de keywords

`S = torch.zeros((Nq*max_QN, Np*max_PN))` (MixPipe:90). Para um corpus grande (Np na casa das dezenas de milhares × 50 keywords), essa matriz densa pode ocupar **gigabytes de VRAM** por lote. É o gargalo de escala da recuperação. Mitigação: reduzir `eval_query_bsz`.

### 7.5 GloVe descarta silenciosamente

Palavras fora do vocabulário GloVe são filtradas **sem aviso**, tanto no índice (capTree:78) quanto na consulta (extract_keys:46). Nomes próprios, jargão técnico e termos recentes **desaparecem** do ramo de keywords. É a escolha mais datada do sistema.

---

## 8. Guia de configuração (`retrieve.sh`)

| Parâmetro | O que controla | Como pensar |
|---|---|---|
| `construct_name` | **Qual índice usar** (`tree.json`) | Deve bater com o da construção |
| `collection` | Dataset/corpus | Deve bater com a construção (validado por `assert`) |
| `retrieve_name` | Nome deste experimento | **Mude a cada re-execução** (senão aborta, §4.1) |
| `retrieve_pipeline` | `mix` (padrão) / `sent` / `key` | `mix` é o melhor; `sent`/`key` são ablações |
| `key_policy` | `max_mean` (padrão) / `max_max` | `max_mean` mede cobertura; vence na ablação |
| `retrieve_sent_ratio` | α da fusão (0,5) | 1,0 = só sentença; 0,0 = só palavras |
| `max_vcmr_props` | Candidatos antes do NMS (1000) | Mais = melhor recall, mais custo |
| `eval_query_bsz` | Consultas por lote (50) | **Reduza se estourar VRAM** (§7.4) |

---

## 9. O que isto significa para o seu sistema de busca

**As etapas que você mantém (1–5):** carregar o índice, codificar a consulta, calcular similaridade, fundir, selecionar top-K. **É o motor de busca.**

**A etapa que você mantém, mas ajusta (6 — NMS):** essencial para não devolver duplicatas. Mantenha.

**A etapa que você descarta (7 — avaliação):** só faz sentido com gabarito. Em produção, você para no `vcmr_preds.json`.

**As três adaptações necessárias** (a "Cirurgia 2/3" que mapeamos):
1. **Alimentar consultas do usuário** — em vez de ler `desc` do `vcmr.jsonl`, receber o prompt em runtime.
2. **Desacoplar o corpus** — popular `vid_name_to_id` a partir dos vídeos **da árvore**, não das consultas (§7.2).
3. **Pular a avaliação** — chamar `pipeline.retrieval()` + NMS, e salvar as predições, sem `eval_retrieval`.

**A boa notícia, confirmada nesta leitura:** o *scoring* (o que produz os momentos) **nunca toca o gabarito**. Os três ajustes são de encanamento — o motor de busca permanece intacto.

---

## 10. Síntese: o mapa mental

```
tree.json ──► CapTree ──[poda + achata + CODIFICA]──► matriz [Np, E] de eventos
                                                              │
consulta ──► sentence-transformer ──► vetor ─────────────────►│ cosseno
         └─► spaCy → keywords → GloVe ──► vetores ───────────►│ Max_Mean
                                                              │
                                                    normaliza + funde (α=0.5)
                                                              │
                                                          top-1000
                                                              │
                                                      NMS temporal (0.5)
                                                              │
                                                     top-100 momentos
                                                     [vídeo, st, ed, score, legenda]
```

**A tese em uma frase:** porque a construção transformou vídeo em texto, a recuperação é **uma comparação de embeddings de texto em duas granularidades (sentença + palavra), fundidas, ranqueadas e deduplicadas** — sem treino, sem rótulo, e com uma legenda explicando cada resultado.
