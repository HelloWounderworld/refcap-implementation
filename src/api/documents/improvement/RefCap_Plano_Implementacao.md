# Plano de Implementação — Cinco Etapas
## O Que Muda em Cada Arquivo, Como Verificar, e o Que Pode Dar Errado

---

> **O que é este documento.** O plano das mudanças acordadas, dividido em cinco etapas independentes. Cada uma diz **o que muda**, **em qual arquivo**, **como verificar antes de avançar** e **qual o risco**.
>
> **Por que em etapas.** Fazer tudo de uma vez esconde a origem de qualquer regressão. Com etapas, se algo quebrar você sabe exatamente o que foi — e pode voltar uma casa em vez de desfazer tudo.
>
> **A regra:** só avance quando o **portão de verificação** da etapa passar.

---

## O ponto de partida

| arquivo | linhas | papel hoje |
|---|---|---|
| `app.py` | 741 | ciclo de vida + 6 rotas + contratos + 2 rotas de teste |
| `processamento.py` | 451 | contratos, resolução de caminho, pesos, pipeline |
| `carregador.py` | 247 | os 4 modelos residentes |
| `jobs.py` | 154 | fila serializada, estado, webhook |
| `ponte_refcap.py` | 165 | `sys.path` e caminhos absolutos |
| 3 diagnósticos | 753 | standalone, sem relação com o serviço |

Mais, no RefCap: `construct.py` (com `build()`), `WholePropGener.py`, `viddataset.py`, `cfg.py`, `propgenerator/__init__.py`.

---

# ETAPA 1 — Contratos e nomes

**Risco: BAIXO.** Mexe só em nomes e estruturas de dados. Nenhuma lógica de pipeline muda.

## 1.1 O que muda

**Em `processamento.py`:**

| de | para |
|---|---|
| `class PedidoDeJob` | `class CaptionRequest` |
| `class ItemDeCena` | `class SceneItem` |
| `class RespostaDeCena` | `class SceneResponse` |
| `class PalavraChave` | `class Keyword` |
| `"resumo"` | `"summary"` |
| `"erros"` | `"errors"` |
| `"segundos"` | `"seconds"` |

**Campos que saem da requisição:**
- `collection` — agora derivado do `program_id`
- `limpar_cache` — vira `force`

**Campos que entram:**
- `force: bool = False`
- `error_code: str | None` e `message: str | None` no `SceneResponse`

**Campos que saem da resposta:**
- `job_id`

**Os cinco códigos de erro**, como constantes:
```python
class ErrorCode:
    INVALID_REQUEST = "INVALID_REQUEST"   # payload malformado, campo faltando
    FILE_NOT_FOUND  = "FILE_NOT_FOUND"    # o scene_video_path não existe
    SCENE_NOT_FOUND = "SCENE_NOT_FOUND"   # o caminho existe, sem vídeo com o scene_id
    CAPTION_FAILED  = "CAPTION_FAILED"    # rodou e não produziu legenda
    INTERNAL_ERROR  = "INTERNAL_ERROR"    # exceção inesperada
```

## 1.2 O `weight` fixo em 1.0

A função `ranquear_keywords` **não é apagada** — passa a:
1. filtrar as keywords, mantendo **só as que aparecem na legenda**
2. atribuir `weight = 1.0` a todas

O cálculo antigo (0.6 literal + 0.4 semântico) fica **preservado em comentário**, com a explicação de por que foi suspenso — para quando você voltar do estudo do GloVe.

**[J] Isso torna o `sentence_transformer` inútil para os pesos** — mas ele continua carregado, porque alimenta o sinal de `consensus` do `WholePropGenerator`. Nada muda no `carregador.py`.

## 1.3 Portão de verificação

```bash
pytest test/whole_propgen -v          # 48 passed — nada do RefCap mudou
python -c "from processamento import CaptionRequest, SceneResponse, ErrorCode"
```

E um teste manual dos dois formatos, confirmando que a resposta sai com `state`, `summary`, `seconds` e sem `job_id`.

## 1.4 O que pode dar errado

| risco | como evitar |
|---|---|
| um `.get("resumo")` esquecido em `app.py` | buscar por todos os nomes antigos antes de considerar a etapa pronta |
| o `force` não substituir todos os usos de `limpar_cache` | idem — inclui as rotas de diagnóstico |

---

# ETAPA 2 — Estrutura em disco + migração

**Risco: MÉDIO.** Muda **onde tudo é gravado**. É a etapa mais delicada.

## 2.1 O que muda

**Em `processamento.py`, na montagem do `cfg`:**

```python
cfg = montar_cfg(
    video_root=diretorio,
    collection=program_id,        # ← era: pedido > program_id > job_id
    construct_name="",            # ← era: f"job_{job_id[:12]}"
    ...
)
```

**Efeito nos cinco caminhos do RefCap:**
```
annos/{program_id}/vcmr.jsonl
meta/captions/{program_id}_blip.jsonl
meta/framefeatures/{program_id}.pt
meta/scores/{program_id}_blip.pt
results/construct/{program_id}/          ← sem subnível
```

**Em `resolver_cena`** — remover o fallback:

```python
# REMOVER: se o diretório tem UM vídeo só, usar esse mesmo sem o nome bater.
# Motivo: pode legendar o arquivo errado em silêncio. Melhor falhar com
# SCENE_NOT_FOUND.
```

**E isolar o identificador:**
```python
# ★ O ÚNICO ponto que conhece o formato do caminho.
# Se o formato da requisição mudar, mude AQUI e mais nada.
IDENTIFICADOR = "scene_id"      # ou "video_id__scene_id", se um dia repetir
```

## 2.2 O script de migração

Novo arquivo: `migrar_cache.py`

```bash
python migrar_cache.py --de teste_api --para meu_programa --simular
python migrar_cache.py --de teste_api --para meu_programa
```

Ele move **quatro** artefatos:
```
annos/{de}/                    → annos/{para}/
meta/captions/{de}_blip.jsonl  → meta/captions/{para}_blip.jsonl
meta/framefeatures/{de}.pt     → meta/framefeatures/{para}.pt
meta/scores/{de}_blip.pt       → meta/scores/{para}_blip.pt
```

**[J] O `--simular` é obrigatório na primeira vez.** Ele mostra o que faria sem tocar em nada, incluindo quantas cenas há em cada cache. Se o destino já existir, ele **recusa** em vez de sobrescrever — fundir dois caches é decisão sua, não do script.

## 2.3 Portão de verificação

```bash
# 1. simular a migração e conferir os pares
python migrar_cache.py --de <antigo> --para <program_id> --simular

# 2. migrar
python migrar_cache.py --de <antigo> --para <program_id>

# 3. confirmar que os caminhos novos existem
ls annos/<program_id>/ meta/captions/<program_id>_blip.jsonl

# 4. processar uma cena JÁ conhecida — deve ser PULADA pelo cache
curl -X POST .../caption -d '{"scene_id":"<uma_ja_processada>",...}'
```

**[J] O passo 4 é o que prova a migração.** Se a cena for reprocessada em vez de pulada, o cache não foi migrado corretamente.

## 2.4 O que pode dar errado

| risco | consequência | mitigação |
|---|---|---|
| migrar para um `program_id` que já tem cache | dois conjuntos misturados | o script **recusa** destino existente |
| esquecer um dos quatro artefatos | reprocessamento parcial silencioso | o `--simular` lista os quatro, com o status de cada |
| `construct_name=""` quebrar o `os.path.join` | caminho errado | **[V] já testado**: produz `results/construct/{program_id}` |
| o `retrieve.py` esperar o `construct_name` antigo | fora do escopo hoje | registrado como pendência |

---

# ETAPA 3 — Persistência do response

**Risco: MÉDIO.** Acrescenta escrita em disco e a fusão do `proposals.json`.

## 3.1 O que muda

**Novo arquivo: `persistencia.py`**

```python
def gravar_respostas(program_id, respostas, raiz) -> dict:
    """Grava nos DOIS formatos, sob results/response/{program_id}/."""

def ler_respostas(program_id, raiz, scene_ids=None) -> list:
    """Lê o persistido. Sem scene_ids, devolve tudo."""

def fundir_proposals(exp_dir, proposals_file) -> int:
    """Funde o proposals.json recém-escrito com o acumulado."""
```

**Os dois formatos:**
```
results/response/{program_id}/responses.jsonl        ← append, cumulativo
results/response/{program_id}/scenes/{scene_id}.json ← sobrescreve, leitura rápida
```

**Guarda tudo:** o contrato, o ranking completo, os diagnósticos, e um `timestamp`.

## 3.2 A fusão do `proposals.json`

**Onde:** em `processar_pedido`, **logo após cada `build()`** — não uma vez no fim.

**Por quê:** com `construct_name=""`, todos os grupos escrevem no mesmo `exp_dir`. O grupo 2 sobrescreveria o `proposals.json` do grupo 1 **dentro da mesma requisição**.

```python
tree_meta = build(cfg, modelos.como_dict())
fundir_proposals(cfg.exp_dir, cfg.proposals_file)   # ← AQUI, dentro do laço
```

**Como funde:** lê o `proposals.json` (que tem só o grupo atual), lê o acumulado anterior, junta por `vid_name`, regrava. Cenas reprocessadas **sobrescrevem** as versões antigas.

## 3.3 O `force: true`

Limpa, **só das cenas indicadas**, os três caches:

| arquivo | operação |
|---|---|
| `meta/captions/{program_id}_blip.jsonl` | reescreve sem as linhas daquelas cenas |
| `meta/framefeatures/{program_id}.pt` | carrega o dict, remove as chaves, regrava |
| `meta/scores/{program_id}_blip.pt` | idem |

**[J] Aviso de custo:** as duas últimas carregam o tensor inteiro na memória. Num programa com centenas de cenas, isso pesa. É o preço do escopo cirúrgico que você escolheu — e como o `force` é manual, o custo só aparece quando você pede.

## 3.4 Portão de verificação

```bash
# 1. processar 2 cenas do vidA
curl -X POST .../caption/batch -d '{"items":[cena_01, cena_02]}'

# 2. processar 1 cena do vidB (MESMO program_id, outro diretório)
curl -X POST .../caption -d '{"scene_id":"cena_03","video_id":"vidB",...}'

# 3. ★ o proposals.json deve ter as TRÊS
python -c "import json; print(list(json.load(open('results/construct/<pid>/proposals.json'))))"

# 4. o responses.jsonl deve ter 3 linhas, e scenes/ 3 arquivos
wc -l results/response/<pid>/responses.jsonl
ls results/response/<pid>/scenes/

# 5. force numa cena — deve reprocessar SÓ ela
curl -X POST .../caption -d '{"scene_id":"cena_01",...,"force":true}'
```

**[J] O passo 3 é o coração desta etapa.** Sem a fusão, o `proposals.json` teria só a `cena_03`.

## 3.5 O que pode dar errado

| risco | mitigação |
|---|---|
| a fusão rodar fora do laço | o passo 3 do portão pega |
| `.jsonl` corrompido por escrita concorrente | a fila serializa — só um job escreve por vez |
| `force` remover a chave errada do `.pt` | testar com uma cena e conferir que as outras sobraram |
| duas requisições no mesmo `.jsonl` | a fila protege; documentar que é ela quem garante |

---

# ETAPA 4 — As rotas

**Risco: BAIXO.** Renomeia rotas e acrescenta o assíncrono automático.

## 4.1 O que muda

| de | para |
|---|---|
| `POST /jobs` | `POST /caption` — cena única |
| — | `POST /caption/batch` — lote ★ novo |
| `GET /jobs/{id}` | `GET /caption/{program_id}` — com filtro |
| `GET /jobs` | **remover** |
| `GET /teste/construct` | `GET /diagnostics/caption` |
| `GET /teste/construct-lote` | `GET /diagnostics/caption-batch` |
| `GET /health` | mantém, **traduzido** |

## 4.2 O assíncrono automático

```python
LIMIAR_ASSINCRONO = 30

if len(itens) > LIMIAR_ASSINCRONO or pedido.assincrono:
    # devolve o aceite; processa em segundo plano
    return {"state": "accepted", "program_id": ...,
            "scenes": [...], "check_at": f"/caption/{program_id}"}
```

O campo `assincrono` permanece como **override manual** — força um modo ou outro, útil para testar.

## 4.3 O `GET /caption/{program_id}`

```
GET /caption/prog1                            → todas as cenas
GET /caption/prog1?scene_id=cena_01           → uma
GET /caption/prog1?scene_id=cena_01&scene_id=cena_02   → várias
```

Programa inexistente → **200** com `{"program_id":..., "items": [], "summary": {"total": 0}}`.

## 4.4 O diagnóstico com `collection` próprio

As rotas `/diagnostics/*` usam `collection = "diagnostics"` — não o `program_id`. Assim você testa sem contaminar dados reais.

## 4.5 Portão de verificação

| verificação | espera |
|---|---|
| `POST /caption` com 1 cena | 200 + contrato |
| `POST /caption/batch` com 3 | 200 + `items` com 3 |
| `POST /caption/batch` com 31 | **202** + aceite |
| `GET /caption/{pid}` | todas as cenas |
| `GET /caption/{pid}?scene_id=X` | só X |
| `GET /caption/inexistente` | 200 + lista vazia |
| `GET /diagnostics/caption` | funciona, e **não** cria artefatos sob o `program_id` |
| `GET /health` | 200, em inglês, com `gpu.allocated_mb` |

---

# ETAPA 5 — Reorganização

**Risco: MÉDIO.** Move código entre arquivos. Nenhuma lógica nova.

**[J] Vem por último de propósito:** as etapas 1–4 mexem em arquivos que ainda vão mudar de lugar. Reorganizando antes, cada etapa anterior mexeria duas vezes. Deixando por último, movemos só código já testado.

## 5.1 A divisão proposta

```
api/
├── app.py              ciclo de vida + registro das rotas        (~80 linhas)
├── contratos.py        os modelos Pydantic + ErrorCode
├── pipeline.py         o processamento (hoje processamento.py)
├── persistencia.py     o diretório de response (etapa 3)
├── rotas/
│   ├── caption.py      POST /caption, /caption/batch, GET /caption/{pid}
│   ├── health.py       GET /health
│   └── diagnostics.py  GET /diagnostics/*
├── carregador.py       (sem mudança)
├── jobs.py             (sem mudança)
└── ponte_refcap.py     (sem mudança)
```

## 5.2 A deduplicação

Hoje as rotas de diagnóstico repetem lógica de `processamento.py`. Passam a chamar **a mesma função**, mudando só o que devolvem:

```python
resultado = pipeline.processar(pedido, ...)

# produção:   devolve resultado["items"]
# diagnóstico: devolve resultado + passos, gpu antes/depois, exp_dir
```

## 5.3 Portão de verificação

```bash
pytest test/whole_propgen -v     # 48 passed
```
E **repetir os portões das etapas 1 a 4** — se todos passarem depois de mover o código, a reorganização foi limpa.

## 5.4 O que pode dar errado

| risco | mitigação |
|---|---|
| import circular entre `rotas/` e `app.py` | usar `APIRouter`; as rotas não importam o `app` |
| estado global (`modelos`, `registro`) inacessível nas rotas | injetar via `app.state` ou dependência do FastAPI |
| um endpoint esquecido no caminho | comparar a lista de rotas antes e depois |

---

# Resumo das cinco etapas

| # | etapa | arquivos tocados | risco | portão |
|---|---|---|---|---|
| 1 | contratos e nomes | `processamento.py`, `app.py` | baixo | 48 testes + resposta em inglês sem `job_id` |
| 2 | disco + migração | `processamento.py`, **`migrar_cache.py`** ★ | **médio** | cena conhecida é **pulada** após migrar |
| 3 | persistência | **`persistencia.py`** ★, `processamento.py` | médio | `proposals.json` com as três cenas |
| 4 | rotas | `app.py` | baixo | os 8 casos da tabela 4.5 |
| 5 | reorganização | todos | **médio** | os portões de 1 a 4, de novo |

**Dois arquivos novos:** `migrar_cache.py` (etapa 2) e `persistencia.py` (etapa 3).

**O RefCap não é tocado em nenhuma etapa.** As mudanças nele — `build()`, `setdefault`, `spacy_nlp`, `max(1, int(duration))`, `WholePropGener` — já estão aplicadas e validadas.

---

# O que este plano não cobre

**[J]**

- **Suíte de testes da API** — nesta fase, só os cenários essenciais. A suíte completa fica para depois do 09/09.
- **Documentação de build** para usuário novo — mesma coisa.
- **A função de `weight`** — fica documentada e inerte até você concluir o estudo do GloVe.
- **O `retrieve.py`** — fora do escopo; se um dia for usado, o `construct_name=""` precisa ser considerado lá.
- **Nada foi testado com GPU ou vídeo real** nas etapas planejadas — os portões precisam ser executados por você, no ambiente real.

---

*Plano de cinco etapas para as mudanças acordadas. Cada uma tem portão de verificação próprio, e a ordem foi escolhida para que uma falha seja rastreável: as etapas de risco médio (2, 3, 5) ficam separadas por etapas de risco baixo, e a reorganização vem por último para mover só código já validado.*
