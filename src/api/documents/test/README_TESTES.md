# Guia de Testes — Índice
## Como Verificar que a Caption API Está Funcionando

---

> **Três documentos, três propósitos:**
>
> | documento | quando usar |
> |---|---|
> | **este** | visão geral, os scripts automáticos, e o que fazer quando algo falha |
> | [`TESTES_CURL.md`](TESTES_CURL.md) | testar caso a caso, à mão, com `curl` |
> | [`TESTES_DIAGNOSTICO.md`](TESTES_DIAGNOSTICO.md) | quando o serviço não sobe, ou os modelos não ficam na GPU |

---

# PARTE 1 — O caminho rápido

Três comandos, e você sabe se está tudo em ordem:

```bash
# 1. cria as cenas de teste (usa ffmpeg)
bash preparar_teste.sh

# 2. sobe o serviço COM os modelos — noutro terminal
cd api && python app.py

# 3. roda a bateria de 18 casos
bash teste_manual.sh
```

No fim, você vê:
```
  12 passou   0 falhou   1 pulado

  ✓ Todos os casos executados passaram.
```

Se algo falhar, o script diz **qual caso** e **o que veio em vez do esperado**.

---

# PARTE 2 — `preparar_teste.sh`

**O que faz:** cria vídeos reais com `ffmpeg` numa estrutura que exercita todos os casos.

```bash
bash preparar_teste.sh            # cria
bash preparar_teste.sh --limpar   # remove tudo
BASE=/outro/lugar bash preparar_teste.sh
```

**A estrutura:**

```
/tmp/teste_refcap/
├── prog_teste/
│   ├── vidA/
│   │   ├── cena_01.mp4   3.0s     caso normal
│   │   ├── cena_02.mp4   2.0s     caso normal
│   │   └── cena_03.mp4   0.52s    ★ testa o patch do vídeo curto
│   ├── vidB/
│   │   └── cena_04.mp4   3.0s     ★ OUTRO diretório — testa o agrupamento
│   └── vazio/                     ★ sem vídeos — testa SCENE_NOT_FOUND
└── prog_outro/
    └── vidX/cena_01.mp4  2.0s     ★ MESMO scene_id — testa o isolamento
```

**Cada cena tem um propósito.** Não são cinco vídeos quaisquer:

| cena | o que exercita |
|---|---|
| `cena_01`, `cena_02` | o caminho feliz, e o cache no reprocessamento |
| **`cena_03` (0,52 s)** | o patch `max(1, int(duration))` no `viddataset.py`. Sem ele, `np.stack([])` derrubaria o processo |
| **`cena_04` no `vidB`** | o agrupamento por diretório — dois `build()` numa requisição |
| **`vazio/`** | `SCENE_NOT_FOUND` |
| **`prog_outro/cena_01`** | o isolamento: mesmo `scene_id`, `collection` diferente |

Ao terminar, ele imprime a **duração real de cada stream** — que é o que o RefCap lê, e costuma diferir do que o player mostra:

```
prog_teste/vidA/cena_03.mp4    0.520s → 1 frame(s)
```

---

# PARTE 3 — `teste_manual.sh`

**O que faz:** 18 casos contra a API rodando, com PASS/FAIL por caso.

```bash
bash teste_manual.sh              # a bateria inteira
bash teste_manual.sh 10           # só o caso 10
API=http://outro:8000 bash teste_manual.sh
```

## Os 18 casos

**Parte 1 — caminho feliz**

| # | caso | espera |
|---|---|---|
| 1 | `POST /caption` (uma cena) | 200 + legenda + keywords |
| 2 | `POST /caption/batch` (2 diretórios) | 200, `groups` = 2 |
| 3 | assíncrono automático | 202 + `accepted` |
| 4 | **vídeo de 0,5 s** | 200 — prova o patch |

**Parte 2 — cache**

| # | caso | espera |
|---|---|---|
| 5 | reprocessar **sem** `force` | rápido; `estavam_em_cache: 1` |
| 6 | **com** `force` | mais **lento** — reprocessou |
| 7 | as outras cenas sobreviveram | ≥ 4 cenas persistidas |

**[J] O caso 6 mede o tempo de propósito.** Se ele levar o mesmo que o caso 5, o cache não foi limpo — e o `force` não está funcionando.

**Parte 3 — erros**

| # | caso | espera |
|---|---|---|
| 8 | caminho inexistente | `FILE_NOT_FOUND` |
| 9 | diretório sem a cena | `SCENE_NOT_FOUND` |
| 10 | **fallback removido** | `SCENE_NOT_FOUND` |
| 11 | pedido vazio | HTTP 400 ou 422 |
| 12 | **erro parcial no lote** | HTTP **200**, `ok=2 errors=1` |

**[J] O caso 10 merece atenção.** O `vidB` tem **um** vídeo (`cena_04`); pedir `cena_77` apontando para o diretório deve **recusar**. Antes da Etapa 2, isso legendava a `cena_04` e devolvia `success` — silenciosamente errado.

**[J] E o caso 12 confirma que uma cena ruim não derruba o lote:** HTTP 200, com o erro dentro do item.

**Parte 4 — consulta**

| # | caso | espera |
|---|---|---|
| 13 | `GET /caption/{pid}` | todas as cenas |
| 14 | com 1 filtro | 1 cena |
| 15 | com 2 filtros | 2 cenas |
| 16 | programa inexistente | **200** + lista vazia (não 404) |

**Parte 5 — isolamento**

| # | caso | espera |
|---|---|---|
| 17 | mesmo `scene_id`, programas diferentes | legendas **distintas** |
| 18 | `/diagnostics/caption` | responde; cria `annos/diagnostics/` |

**[J] O caso 17 imprime as duas legendas lado a lado.** Se saírem iguais, o isolamento por `collection` falhou — e é o erro silencioso mais grave que existiria.

## Sobre o caso 3 (assíncrono)

Ele exige o limiar baixo:

```bash
REFCAP_LIMIAR_ASSINCRONO=2 python app.py
```

Sem isso, o caso é **pulado com aviso** — em vez de exigir 31 cenas reais só para exercitá-lo.

---

# PARTE 4 — O que conferir no disco

O script termina listando isto, mas vale ter à mão:

```bash
cd <raiz-do-RefCap>

ls annos/                              # prog_teste, prog_outro, diagnostics
ls meta/captions/                      # prog_teste_blip.jsonl, prog_outro_blip.jsonl
ls results/construct/prog_teste/       # proposals.json, tree.json, *.pt
ls results/response/prog_teste/scenes/ # um .json por cena
```

## As quatro verificações que valem o olho

**1. A fusão do `proposals.json` funcionou**
```bash
python -c "import json;print(sorted(json.load(open('results/construct/prog_teste/proposals.json'))))"
```
Deve listar **todas** as cenas processadas. Se tiver só as do último lote, a fusão não rodou.

**2. O histórico guarda todas as versões**
```bash
wc -l results/response/prog_teste/responses.jsonl
ls results/response/prog_teste/scenes/ | wc -l
```
O `.jsonl` deve ter **mais linhas** que `scenes/` tem arquivos — o `force` gerou uma versão nova da mesma cena.

**3. Uma cena guarda tudo**
```bash
python -m json.tool results/response/prog_teste/scenes/cena_01.json
```
Deve ter `scene_caption_en`, `keywords_en`, `timestamp`, e dentro de `diagnostics`: `ranking`, `n_raw`, `n_distinct`, `warning`.

**4. Os modelos continuam residentes**
```bash
curl -s localhost:8000/health | python -m json.tool | grep allocated_mb
```
Rode **antes e depois** da bateria. O número deve ser **o mesmo** — se crescer, algo está recarregando modelo a cada requisição.

---

# PARTE 5 — Quando algo falha

| sintoma | provável causa | onde olhar |
|---|---|---|
| pré-voo: "serviço não respondeu" | o serviço não está no ar | suba com `python app.py` |
| pré-voo: `models.ready: False` | subiu com `REFCAP_CARREGAR_MODELOS=0` | remova a variável |
| caso 4 falha (vídeo curto) | patch do `viddataset` não aplicado | `grep n_amostras dataset/viddataset.py` |
| caso 6 tão rápido quanto o 5 | o `force` não limpou o cache | veja `cache_limpo` na resposta |
| caso 10 devolve `success` | o fallback antigo ainda está lá | `grep "último recurso" api/pipeline.py` |
| caso 17: legendas iguais | o `collection` não isolou | confira que é `program_id`, não fixo |
| `allocated_mb` cresce | modelos recarregando | veja [`TESTES_DIAGNOSTICO.md`](TESTES_DIAGNOSTICO.md) |

---

# PARTE 6 — Os limites deste guia

**[J]**

- Os scripts foram **validados sintaticamente** e o `preparar_teste.sh` foi executado, mas a bateria completa **não** foi rodada ponta a ponta contra um serviço com GPU real — isso depende do seu ambiente.
- Os tempos citados (~1–3 s por cena) são estimativa, não medição.
- A bateria testa o **contrato e o fluxo**, não a **qualidade** das legendas. Se o BLIP produzir uma legenda ruim, todos os 18 casos passam.
- Não há teste de carga nem de concorrência real — a fila é serializada por projeto, e testá-la exigiria disparar requisições simultâneas.

---

*Guia de testes da Caption API. Comece pela Parte 1; se algo falhar, a Parte 5 aponta onde olhar. Para testar caso a caso à mão, veja `TESTES_CURL.md`; para problemas de infraestrutura (GPU, supervisord, modelos), veja `TESTES_DIAGNOSTICO.md`.*
