# Caption API — Legendagem de Cenas com RefCap

Serviço HTTP que gera legendas em inglês para cenas de vídeo, usando o
[RefCap](https://github.com/BUAAPY/RefCap) com os modelos **residentes em
memória** — carregados uma vez, reutilizados em todas as requisições.

---

## O problema que o serviço resolve

O RefCap original é uma ferramenta de linha de comando: cada execução carrega
os modelos, processa, e morre. Para um vídeo isso custa ~20 s só de
carregamento — e para mil cenas, ~5,5 horas desperdiçadas.

Este serviço inverte isso:

```
              RefCap original                    Caption API
        ┌────────────────────────┐        ┌────────────────────────┐
        │  python construct.py   │        │  startup: carrega 1×   │
        │    carrega modelos     │        │  ────────────────────  │
        │    processa            │        │  POST /caption  →  ~3s │
        │    encerra             │        │  POST /caption  →  ~3s │
        └────────────────────────┘        │  POST /caption  →  ~3s │
           ~23 s por cena                 └────────────────────────┘
                                             ~3 s por cena
```

---

## A arquitetura em três camadas

```
┌─────────────────────────────────────────────────────────────────┐
│  CAMADA 1 — HTTP                                                │
│                                                                 │
│   rotas/caption.py        POST /caption, /caption/batch         │
│                           GET  /caption/{program_id}            │
│   rotas/health.py         GET  /health                          │
│   rotas/diagnostics.py    GET  /diagnostics/*                   │
│                                                                 │
│   Papel: traduzir HTTP em chamadas ao pipeline. Não conhece      │
│          o RefCap.                                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  CAMADA 2 — ORQUESTRAÇÃO                                        │
│                                                                 │
│   contratos.py       os modelos Pydantic e os códigos de erro   │
│   captioning.py      resolve caminhos, agrupa, chama o build,   │
│                      transforma a saída no contrato             │
│   persistencia.py    grava o estado, o summary e o histórico    │
│   jobs.py            fila serializada — um job por vez na GPU   │
│   estado.py          modelos, fila e configuração compartilhados │
│                                                                 │
│   Papel: tudo o que o serviço sabe fazer, sem HTTP.             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  CAMADA 3 — REFCAP                                              │
│                                                                 │
│   ponte_refcap.py    sys.path, caminhos absolutos, montar_cfg   │
│   carregador.py      os 4 modelos residentes                    │
│                              ↓                                  │
│   construct.build(cfg, pretrained_models)   ← o RefCap          │
│                                                                 │
│   Papel: isolar o serviço das particularidades do RefCap.       │
└─────────────────────────────────────────────────────────────────┘
```

**A regra que mantém isso limpo:** as rotas importam de `estado.py`, nunca de
`app.py`. É o que evita o import circular — o `app.py` importa as rotas, e as
rotas não importam o `app.py`.

---

## Os módulos, um a um

### `app.py` — ciclo de vida
Sobe o serviço, carrega os modelos no startup, registra as rotas, libera os
modelos no shutdown. **Nada mais.** É o arquivo que você lê primeiro para
entender o serviço, e o menor de todos.

### `estado.py` — o que todos compartilham
Os modelos residentes, a fila de jobs, e a configuração via ambiente.
Não importa ninguém — é o que permite que rotas e `app.py` compartilhem estado
sem se importarem mutuamente.

### `contratos.py` — o que entra e o que sai
Os modelos Pydantic (`CaptionRequest`, `SceneItem`, `SceneResponse`,
`Keyword`) e os cinco códigos de erro. **Quem consome a API só precisa ler
este arquivo.**

As duas formas de requisição — cena única e lote — são normalizadas numa lista
só pelo `como_itens()`, de modo que o processamento não tem dois caminhos.

### `captioning.py` — o pipeline
O coração. Em seis passos:

| # | passo | o que faz |
|---|---|---|
| 1 | **resolver** | do `scene_video_path` ao arquivo real; falha vira `FILE_NOT_FOUND` ou `SCENE_NOT_FOUND` |
| 2 | **agrupar** | por diretório — o RefCap lista **um** diretório por execução, então cenas de `video_id` diferentes exigem `build()` separados |
| 3 | **montar o cfg** | `collection = program_id`, `construct_name = ""` |
| 4 | **cache** | lê quem já está processado; o `force` limpa só as cenas pedidas |
| 5 | **build + fusão** | chama o RefCap e funde o `proposals.json` logo depois |
| 6 | **transformar** | do `proposals` ao contrato de resposta |

### `persistencia.py` — o que fica em disco
Grava o estado atual do programa, o registro de cada execução, e o que foi
substituído. Ver *Estrutura em disco*, abaixo.

### `carregador.py` — os quatro modelos
| modelo | para quê | onde |
|---|---|---|
| BLIP-caption | gera a legenda de cada frame | GPU |
| BLIP-ITM | mede imagem × texto | GPU |
| sentence-transformer | similaridade entre legendas | GPU |
| spaCy | extrai substantivos e verbos | RAM |

O GloVe **não** é carregado — ele só é usado no `retrieve`, que está fora do
escopo deste serviço.

### `jobs.py` — a fila
Um job por vez. Não é para throughput — é para **não haver dois processos
disputando a GPU**, e para que dois jobs não escrevam no mesmo arquivo ao
mesmo tempo.

### `ponte_refcap.py` — o isolamento
Põe a raiz do RefCap no `sys.path`, converte os caminhos relativos do `cfg.py`
em absolutos, e **recusa subir o serviço** se algum arquivo da API colidir com
um módulo de topo do RefCap (`pipeline`, `config`, `dataset`, `utils`…).

> Essa checagem existe porque um arquivo chamado `pipeline.py` dentro de `api/`
> sequestra o `import pipeline` do RefCap, e o `construct.py` quebra com
> `No module named 'pipeline.denoiser'` — um erro que só aparece no meio do
> captioning.

---

## As 7 etapas do `construct()` do RefCap

O que acontece dentro do `build()`, para uma cena:

```
1. caption_generator     BLIP legenda cada frame              ← cache
2. compute_frame_features embeddings dos frames               ← cache
3. compute_capframe_scores  scores brutos (legenda × frame)   ← cache
4. caption_denoiser      descarta legendas ruins              sem cache
5. compute_capframe_scores  scores das legendas filtradas     ← cache
6. proposal_generator    monta e ranqueia as propostas        sem cache
7. build_tree_meta       a estrutura hierárquica
```

As etapas 4 e 6 rodam sempre — mas só sobre as cenas da requisição, porque o
`annos` funciona como **seletor**: `vid_list = os.listdir(video_root) ∩ annos`.

---

## Estrutura em disco

```
<raiz-do-refcap>/
├── annos/{program_id}/vcmr.jsonl          o SELETOR da requisição
├── meta/                                   ★ O CACHE — não apague
│   ├── captions/{program_id}_blip.jsonl        legendas por frame
│   ├── framefeatures/{program_id}.pt           embeddings
│   └── scores/{program_id}_blip.pt             scores
├── results/
│   ├── construct/{program_id}/                 artefatos do build
│   │   ├── proposals.json                      fundido a cada build
│   │   ├── proposals_acumulado.json            o acumulado
│   │   ├── prop_sims.pt                        matrizes [N,N] por cena
│   │   └── tree.json
│   └── response/{program_id}/              ★ O QUE A API PRODUZ
│       ├── responses.jsonl                     uma linha: o programa inteiro
│       ├── scenes/{scene_id}.json              uma cena cada
│       ├── summary/summaries.json              uma entrada por requisição
│       └── history/history.jsonl               versões substituídas
```

### O que é cumulativo e o que não é

| artefato | comportamento |
|---|---|
| `meta/captions/*.jsonl` | append ✓ |
| `meta/framefeatures/*.pt` | carrega, acrescenta, regrava ✓ |
| `meta/scores/*.pt` | idem ✓ |
| `results/.../prop_sims.pt` | idem ✓ *(corrigido)* |
| `results/.../proposals.json` | sobrescrito pelo RefCap, **fundido** logo depois ✓ |
| `annos/{program_id}/vcmr.jsonl` | **sobrescrito** — é o seletor, não um registro |

> **O `meta/` é o ativo mais valioso.** Perdê-lo significa refazer todo o
> captioning. Num deploy em Docker, ele precisa de volume.

---

## O contrato

### Requisição

```json
{ "scene_id": "cena_01", "video_id": "vidA", "program_id": "prog_teste",
  "scene_video_path": "/dados/prog_teste/vidA/cena_01.mp4" }
```

Em lote: `{"items": [ {...}, {...} ]}`.

Opcionais: `force` (reprocessa, limpando o cache daquelas cenas),
`assincrono`, `proposal_generator`, `callback_url`.

**`collection` não é aceito** — ele é derivado do `program_id`. Aceitar um
override quebraria o isolamento entre programas.

### Resposta

```json
{ "state": "concluded", "program_id": "prog_teste",
  "summary": {"total": 1, "ok": 1, "errors": 0},
  "items": [{
    "scene_id": "cena_01",
    "scene_caption_en": "a woman preparing food in a kitchen",
    "keywords_en": [{"token": "woman", "weight": 1.0}],
    "model_name": "refcap", "model_version": "v1", "status": "success"
  }],
  "groups": [...], "persisted": {...}, "seconds": 4.2 }
```

### Os cinco códigos de erro

| código | quando |
|---|---|
| `INVALID_REQUEST` | payload malformado, campo faltando |
| `FILE_NOT_FOUND` | o caminho não existe |
| `SCENE_NOT_FOUND` | o caminho existe, mas não há vídeo com aquele `scene_id` |
| `CAPTION_FAILED` | o pipeline rodou e não produziu legenda |
| `INTERNAL_ERROR` | exceção inesperada |

Erros de **cena** vêm com HTTP 200, dentro do item. O HTTP só vira 4xx/5xx
quando a requisição inteira é inválida.

---

## Decisões de projeto, e por quê

### `collection = program_id`
Um identificador governa os cinco caminhos do RefCap. É isso que garante que
dois programas nunca compartilhem cache — e que a mesma `scene_id` em
programas diferentes não devolva a legenda errada.

### `construct_name = ""`
Colapsa o último nível do `exp_dir`, deixando os artefatos em
`results/construct/{program_id}/` — cumulativos por programa, em vez de um
diretório por execução.

### `weight = 1.0`, fixo
A ponderação anterior (0,6 literal + 0,4 semântico) foi **suspensa**, não
apagada: o `paraphrase-distilroberta-v2` foi treinado para comparar
*sentenças*, não palavras isoladas, e os pesos nunca foram calibrados. O
cálculo está preservado em comentário, com as alternativas a avaliar.

Como só entram palavras **literalmente presentes na legenda**, 1.0 é coerente:
não há gradação a expressar.

### Síncrono por padrão, assíncrono acima de 30 cenas
O gargalo não é processamento — é a **conexão HTTP**. Uma cena leva ~1–3 s,
então 30 já se aproximam do timeout típico de proxy. Acima disso a API devolve
202 e processa em segundo plano; nada se perde, o resultado fica persistido.

### O fallback removido
Havia um atalho: "se o diretório tem um vídeo só, use ele". Isso legendava o
arquivo errado **em silêncio**, devolvendo `status: success`. Hoje falha com
`SCENE_NOT_FOUND`.

---

## Os 5 patches no RefCap

O serviço não funciona com o RefCap intocado:

| arquivo | mudança |
|---|---|
| `construct.py` | `build(cfg, pretrained_models)` extraído — permite passar os modelos já carregados |
| `dataset/viddataset.py` | `max(1, int(duration))` — sem isso, vídeo < 1 s derruba o processo |
| `config/cfg.py` | `"whole"` nos choices do `proposal_generator` |
| `pipeline/propgenerator/__init__.py` | registro do `WholePropGenerator` |
| `pipeline/propgenerator/WholePropGener.py` | **novo** — o gerador de propostas |

---

## Rodar

```bash
cd api && python app.py               # desenvolvimento
uvicorn app:app --host 0.0.0.0 --port 8000   # produção
```

**Variáveis** (ver `estado.py`):
`REFCAP_CAPTION_MODEL`, `REFCAP_BLIP_ITM_MODEL`,
`REFCAP_SENTENCE_TRANSFORMER` — caminhos **absolutos** para os modelos locais;
`REFCAP_DEVICE`, `REFCAP_LIMIAR_ASSINCRONO`, `REFCAP_CARREGAR_MODELOS=0`
(sobe sem modelos, para testar rotas).

Em Docker, ver [`DOCKER.md`](api/DOCKER.md) — atenção especial ao bind-mount
das cenas e à persistência do `meta/`.

---

## Verificar que está funcionando

```bash
bash verificar_contrato.sh     # o contrato está íntegro? (42 checagens)
bash preparar_teste.sh         # mapeia as suas cenas
bash teste_manual.sh           # 20 combinações
```

Ver [`README_TESTES.md`](api/README_TESTES.md), [`TESTES_CURL.md`](api/TESTES_CURL.md)
e [`TESTES_DIAGNOSTICO.md`](api/TESTES_DIAGNOSTICO.md).

---

## Limites conhecidos

- **A função de `weight`** está suspensa até a decisão sobre o GloVe.
- **O `retrieve.py`** está fora do escopo; ele lê o `annos` e o `prop_sims`, e
  espera o `construct_name` no caminho.
- **Três arquivos são carregados inteiros** a cada requisição (legendas,
  features, scores). Com 10 cenas é irrelevante; com milhares, o `torch.load`
  passa a dominar o tempo de uma requisição de uma cena só.
- **A suíte de testes da API** cobre os cenários essenciais, não a totalidade.
