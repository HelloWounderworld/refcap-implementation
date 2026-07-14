# `retrieve_service.py` — How To Use  · **v2 (auditado)**
## Manual completo do serviço de busca RefCap (warm-start REPL)

---

> **O que é este documento.** O manual de uso do `retrieve_service.py` v2 — o serviço que carrega o índice e os modelos **uma vez** e fica no terminal recebendo queries até você digitar `exit`. Cobre: pré-requisitos, todos os modos de uso, todas as flags, como interpretar (e desconfiar de) os resultados, diagnóstico de domínio, troubleshooting e uso como biblioteca.
>
> **O que ele NÃO é.** Não é o `retrieve.py`. O `retrieve.py` é um **avaliador de benchmark** (lê queries do `annos/`, compara com o gabarito, cospe Recall/IoU). Este é um **motor de busca** (recebe queries do usuário, devolve momentos). **O núcleo do RefCap não foi modificado.**
>
> **⚠️ Novidades da v2** (após auditoria que *executou* o caminho real — ver §10): quatro bugs corrigidos e uma flag removida. **Se você estava usando a v1, substitua-a.**

---

## 1. Pré-requisitos

Três coisas precisam existir antes da primeira execução. **O serviço valida as duas primeiras e falha cedo com mensagem clara** (melhoria da v2).

| Pré-requisito | Como verificar |
|---|---|
| **A `tree.json`** (a construção já rodou) | `ls results/construct/{collection}/{construct_name}/tree.json` |
| **O modelo do spaCy** (`en_core_web_sm`) | `python -c "import spacy; spacy.load('en_core_web_sm')"` |
| **GloVe** (`meta/glove.6B/glove.6B.300d.txt`, ~1GB) | `ls -lh meta/glove.6B/glove.6B.300d.txt` |

Se faltar o spaCy:
```bash
python -m spacy download en_core_web_sm
```

> **O serviço NÃO precisa de:** ffmpeg, BLIP, MiniGPT, nem dos vídeos originais. Aqui não há vídeo — só o texto que a construção produziu.

---

## 2. Uso básico (o caminho feliz)

```bash
python retrieve_service.py \
    --collection meu_corpus \
    --construct_name blip_window_it
```

Os dois argumentos **obrigatórios** localizam o índice — juntos formam o caminho `results/construct/{collection}/{construct_name}/tree.json`:
- `--collection` — o mesmo nome usado no `make_annos.py` e no `construct.py`.
- `--construct_name` — o nome do experimento de construção.

### O que você verá

**Fase 1 — Bootstrap** (uma vez; segundos a minutos, conforme o tamanho do corpus):
```
Iniciando serviço (device=cuda)...

[1/4] Carregando modelos de texto...
  → sentence-transformer (codifica legendas E queries)...
  → GloVe (lookup de vetores de palavras)...
[2/4] Carregando índice: results/construct/meu_corpus/blip_window_it/tree.json
      42 vídeo(s) no índice.
[3/4] Codificando o índice (forward pass do sentence-transformer)...
Total::  cap_cnt: 187, key_cnt: 3421, root_cnt: 42, node_cnt: 229
[4/4] Instanciando pipeline 'mix'...

✓ Serviço pronto em 23.4s (187 eventos indexados).
```

**Fase 2 — O REPL** (fica aqui até você sair):
```
======================================================================
  RefCap — Serviço de Busca
  Digite sua query (ex.: 'a person opens a door')
  Comandos: 'exit' / 'quit' para sair | Ctrl-D também funciona
======================================================================

🔎 > a person opens a door

  10 momento(s) em 87ms:

   1. [  12.0s →   19.0s]  score=1.000  vid_003
      └─ "a man in a plaid shirt stands in front of an open door"
   2. [  45.0s →   51.0s]  score=0.873  vid_017
      └─ "a person walking through a doorway in a hallway"
   ...

🔎 > exit
Encerrando.
```

**A assimetria é o ponto:** o bootstrap levou 23s; **cada query leva ~87ms**. É para isso que o serviço fica residente.

---

## 3. Todas as formas de uso

### 3.1 Sair — três maneiras
`exit` / `quit` / `sair` · `Ctrl-D` (EOF) · `Ctrl-C` — todas encerram limpo.

### 3.2 Controlar quantos resultados aparecem
```bash
--top_k 5      # mostra 5 em vez de 10
```
A busca sempre calcula o top-1000 internamente e aplica NMS; `--top_k` controla só a **exibição**.

### 3.3 Rodar em CPU
```bash
--device cpu
```
O default detecta GPU automaticamente. Em CPU, o bootstrap fica mais lento (codificar o índice); por query, ainda é rápido.

### 3.4 Trocar a estratégia de busca — **a ferramenta de diagnóstico mais útil**
```bash
--retrieve_pipeline mix    # padrão: funde sentença + palavras-chave
--retrieve_pipeline sent   # só SENTENÇA (embedding da frase inteira)
--retrieve_pipeline key    # só PALAVRAS-CHAVE (GloVe: substantivos + verbos)
```

**Por que experimentar:** rodar a mesma query nos três modos mostra, na prática, o que cada sinal contribui. `sent` captura *composição e ordem* ("homem abre porta" ≠ "porta abre homem"); `key` captura *presença de conceitos* (robusto a paráfrase); `mix` combina. **Se o `mix` der resultados estranhos, rodar `sent` e `key` separados diagnostica qual ramo está falhando.**

### 3.5 Ajustar o peso da fusão (α)
```bash
--retrieve_sent_ratio 0.5   # default: metade sentença, metade palavras
--retrieve_sent_ratio 1.0   # equivale a 'sent'
--retrieve_sent_ratio 0.0   # equivale a 'key'
--retrieve_sent_ratio 0.7   # pende para a sentença
```
**Quando mexer:** queries em frases completas e descritivas → aumente α. Queries como lista de termos ("porta, homem, abrir") → diminua α.

> ⚠️ **Ressalva:** α=0.5 é o default do paper, fixado **sem protocolo de validação declarado**. Não há garantia de ser ótimo no seu domínio — e, sem dados rotulados seus, você não tem como *medir* qual valor é melhor. Ajustar α é **exploração qualitativa**, não otimização.

### 3.6 Trocar a agregação de palavras-chave
```bash
--key_policy max_mean   # default: mede COBERTURA (média sobre as palavras da query)
--key_policy max_max    # mede o MELHOR ACERTO (max sobre as palavras da query)
```
`max_mean` premia eventos que casam com **todas** as palavras; `max_max` premia os que casam **muito bem com uma só**. A ablação do paper mostra `max_mean` vencendo (+1.19).

### 3.7 Ampliar o pool de candidatos
```bash
--max_vcmr_props 5000   # default: 1000
```
Mais candidatos antes do NMS = melhor chance de o momento certo estar no pool, ao custo de memória. Raramente precisa mexer.

### 3.8 Reprodutibilidade
```bash
--seed 42   # default
```
**Novo na v2** (a v1 não semeava — bug corrigido).

### 3.9 Ver todas as opções
```bash
python retrieve_service.py --help
```

---

## 4. ⚠️ Como interpretar os resultados (a seção mais importante)

Cada resultado tem quatro partes:
```
 1. [  12.0s →   19.0s]  score=1.000  vid_003
    └─ "a man in a plaid shirt stands in front of an open door"
    │        │             │            │
    │        │             │            └─ QUAL VÍDEO
    │        │             └─ o score (⚠️ ENGANOSO — leia abaixo)
    │        └─ o INTERVALO dentro do vídeo
    └─ A LEGENDA — o que o sistema "viu" nesse trecho
```

### O score é enganoso — **julgue pela LEGENDA**

> **Os scores são normalizados POR QUERY** (`MixPipe.py:128-129`, min-max). O **melhor resultado sempre fica perto de 1.000 — mesmo que seja completamente irrelevante**. O sistema **nunca diz "não encontrei nada"**.

**Na prática:** se você buscar "um elefante rosa dançando" num acervo de vídeos de escritório, você **ainda receberá 10 resultados com score alto**. Serão os "menos irrelevantes", não os relevantes.

**Como julgar de verdade:** **leia a legenda.** Ela é a representação real do que o sistema entendeu daquele trecho. Se ela descreve algo que casa com a sua query, o resultado é bom. Se não, o sistema não achou nada — independentemente do score.

> Isto não é defeito do serviço; é propriedade do RefCap (o min-max destrói a magnitude absoluta). Um limiar de "não achei" exigiria capturar os scores **brutos** (pré-normalização).

---

## 5. A legenda como diagnóstico de domínio (o teste mais valioso)

Além de julgar resultados, a legenda te diz se **o método serve ao seu domínio**:

- **Legendas fiéis e específicas** ("um homem de camisa xadrez abre uma porta") → o BLIP entendeu seus vídeos. **O método tem chance.**
- **Legendas genéricas ou erradas** ("uma pessoa em um quarto", repetidas em tudo) → o BLIP **não** lida com seu domínio. **Nenhum ajuste de α, `key_policy` ou pipeline conserta isso** — o gargalo está na *fonte* (o captioning), não na busca.

### Fluxo de validação recomendado
```
1. Rode o serviço com o seu micro-corpus (5–10 vídeos).
2. Digite queries cujas respostas você CONHECE (você viu o vídeo).
3. Para cada uma, pergunte:
      a) O momento certo apareceu no top-10?
      b) A LEGENDA descreve fielmente o trecho?
      c) Os intervalos [início→fim] fazem sentido?
4. Diagnóstico:
      (a) sim + (b) sim  → o método funciona no seu domínio ✓
      (a) não + (b) sim  → legendas boas, matching falhando
                           → teste --retrieve_pipeline sent / key
                             e ajuste --retrieve_sent_ratio
      (b) não            → GARGALO NA FONTE: o BLIP não entende seus vídeos
                           → considere trocar o VLM (fora do escopo do serviço)
```

---

## 6. Usar o serviço em código (para além do REPL)

O `search()` é o **núcleo reutilizável**; o REPL é só uma casca em volta dele.

```python
from retrieve_service import ServiceConfig, SearchService
import argparse

args = argparse.Namespace(
    collection="meu_corpus", construct_name="blip_window_it",
    res_dir="results", construct_dir="construct", tree_file="tree.json",
    sentence_transformer="paraphrase-distilroberta-v2",
    glove_model="meta/glove.6B/glove.6B.300d.txt", meta_dir="meta",
    retrieve_pipeline="mix", key_policy="max_mean", retrieve_sent_ratio=0.5,
    max_vcmr_props=1000, max_key_cnt_per_proposal=50, device="cuda", seed=42,
)
cfg = ServiceConfig(args)
service = SearchService(cfg)          # ← bootstrap (uma vez)

results = service.search("a person opens a door", top_k=5)
for r in results:
    print(r["vid_name"], r["start"], r["end"], r["score"], r["caption"])
```

**Formato de retorno:**
```python
[{"vid_name": str, "start": float, "end": float, "score": float, "caption": str}, ...]
```

### Batch de queries
```python
for q in ["a person opens a door", "someone is cooking", "a car driving"]:
    print(f"\n=== {q} ===")
    for r in service.search(q, top_k=3):
        print(f"  {r['vid_name']} [{r['start']:.0f}-{r['end']:.0f}s] {r['caption']}")
```

### Virar uma API HTTP (o próximo passo natural — zero retrabalho)
```python
from fastapi import FastAPI
app = FastAPI()
service = SearchService(cfg)          # carregado UMA vez, no startup do servidor

@app.get("/search")
def search(q: str, top_k: int = 10):
    return service.search(q, top_k=top_k)
```
É a **mesma função `search()`**. Foi para isso que o REPL foi construído assim.

---

## 7. Troubleshooting

| Sintoma | Causa | Solução |
|---|---|---|
| `tree.json não encontrada` | A construção não rodou, ou `--collection`/`--construct_name` errados | `ls results/construct/*/*/tree.json` e use os nomes exatos |
| `Modelo do spaCy ausente` | `en_core_web_sm` não instalado | `python -m spacy download en_core_web_sm` |
| Erro carregando GloVe / `torchtext` | GloVe ausente, ou `torchtext` incompatível | Baixe o GloVe; use as versões pinadas do `requirements.txt` |
| `OSError: libtorchtext.so` | Versão do torch incompatível com o torchtext | Ambiente errado — ative o `refcap-test` |
| `CUDA out of memory` | Corpus grande + a matriz densa do ramo de keywords | `--device cpu` ou reduza `--max_key_cnt_per_proposal` |
| Bootstrap lento | Codificar o índice é o gargalo (esperado) | Normal para corpus grande |
| Resultados ruins, **legendas boas** | O matching está falhando | Teste `sent` / `key` separados; ajuste α |
| Resultados ruins, **legendas ruins** | **O BLIP não entende seu domínio** | **Gargalo na fonte — nenhum ajuste de busca resolve** |
| Erro numa query específica | Query vazia, ou sem substantivos/verbos no GloVe | O serviço **não cai**; reporta e continua. Reformule |

> **Robustez:** um erro em *uma* query **não derruba o serviço** — o estado warm é caro demais para perder.

---

## 8. Referência completa das flags

| Flag | Default | O que faz |
|---|---|---|
| `--collection` | **(obrigatório)** | Nome da collection (o mesmo da construção) |
| `--construct_name` | **(obrigatório)** | Nome do experimento de construção |
| `--top_k` | `10` | Quantos resultados exibir |
| `--device` | auto (`cuda` se houver) | `cuda` ou `cpu` |
| `--seed` | `42` | Semente (reprodutibilidade) — **novo na v2** |
| `--retrieve_pipeline` | `mix` | `mix` / `sent` / `key` |
| `--key_policy` | `max_mean` | `max_mean` / `max_max` |
| `--retrieve_sent_ratio` | `0.5` | α: peso da sentença (1−α = palavras) |
| `--max_vcmr_props` | `1000` | Candidatos antes do NMS |
| `--max_key_cnt_per_proposal` | `50` | Keywords por evento no índice |
| `--sentence_transformer` | `paraphrase-distilroberta-v2` | Modelo de embedding de texto |
| `--glove_model` | `meta/glove.6B/glove.6B.300d.txt` | Caminho do GloVe |
| `--meta_dir` | `meta` | Cache do GloVe |
| `--res_dir` / `--construct_dir` / `--tree_file` | `results` / `construct` / `tree.json` | Componentes do caminho do índice |

> **Removida na v2:** `--cache_index` (era código morto — salvava vetores e nunca os restaurava).

---

## 9. O que o serviço faz por baixo

```
BOOTSTRAP (1x, caro)                     POR QUERY (ms, barato)
├─ valida spaCy (falha cedo)             ├─ query → encode (forward pass)
├─ carrega sentence-transformer          ├─ cos_sim contra TODOS os eventos
├─ carrega GloVe                         ├─ keywords (spaCy) → GloVe → Max_Mean
├─ carrega tree.json → CapTree           ├─ fusão: α·sent + (1-α)·key
├─ vid_name_to_id ← da ÁRVORE ⚠️         ├─ topk
├─ CODIFICA o índice (o gargalo)         ├─ NMS temporal
└─ instancia MixPipe (intocado)          └─ (vídeo, início, fim, score, legenda)
```

**⚠️ O detalhe que faz tudo funcionar:** `vid_name_to_id` é construído a partir da **árvore** (todos os vídeos indexados), **não das queries**. Isso desarma a armadilha do RefCap (`capTree.py:108`), onde a árvore seria podada para conter só os vídeos mencionados nas queries — o que, num sistema de busca real, zeraria o corpus.

**Só há dois forward passes:** codificar o índice (uma vez) e codificar a query (por busca). Ambos do **sentence-transformer**. O GloVe é *table lookup*; o BLIP **nunca é invocado** (por isso a v2 não o carrega).

---

## 10. O que mudou da v1 para a v2 (auditoria)

A v1 foi escrita validando só o contrato do `QueryDataset`. Uma auditoria que **executou o caminho real** encontrou cinco problemas:

| # | Problema | Impacto | Correção na v2 |
|---|---|---|---|
| **C1** | `from retrieve import ...` — o `retrieve.py` executa `os.environ["CUDA_VISIBLE_DEVICES"]='0'` **no topo do módulo** | **Bug crítico:** forçava a GPU 0, sobrescrevendo `--device` silenciosamente | Usa `utils.temporal_nms` diretamente; não importa nada de `retrieve.py` |
| **C2** | Faltava `seed_it()` (o `retrieve.py` original chama, l.240) | Reprodutibilidade perdida | Chama `seed_it(--seed)` |
| **C3** | O `MixPipe.__init__` (l.31) recarrega o GloVe | **~1GB duplicado em RAM** | Injeta a instância já carregada |
| **C4** | Dependência do spaCy não validada | Quebrava com erro obscuro no meio do bootstrap | `check_spacy_model()` valida antes, com mensagem clara |
| **C5** | `--cache_index` salvava mas nunca restaurava | Código morto enganoso | Flag removida |

**Se você estava usando a v1, substitua-a.** O C1 em particular pode ter feito o serviço rodar na GPU errada sem você perceber.

---

### Regras de ouro
1. **Julgue pela LEGENDA, não pelo score** — o score é normalizado por query e sempre parece alto.
2. **Mesmo `collection` + `construct_name`** da construção — é o que localiza o índice.
3. **O bootstrap é caro, a query é barata** — mantenha o serviço rodando.
4. **Legendas ruins = gargalo na fonte** — nenhum ajuste de busca conserta captioning ruim.
5. **`search()` é o núcleo reutilizável** — o REPL é só uma casca; a API HTTP usa a mesma função.
6. **O núcleo do RefCap não foi modificado** — toda a adaptação vive no `QueryDataset` e no `SearchService`.
