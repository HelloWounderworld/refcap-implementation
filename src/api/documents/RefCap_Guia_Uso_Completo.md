# Guia de Uso — Do Terminal e da Interface FastAPI
## Passo a Passo com o `construct.py` Novo e os Modelos Residentes

---

> **O que é este documento.** Como usar, na prática, tudo o que foi construído: pelo terminal (CLI do RefCap) e pela interface do FastAPI. Cada caminho com o comando, o que esperar, e o que fazer quando falha.
>
> **A mudança central.** O `construct.py` agora tem **duas** portas de entrada:
>
> | porta | quem usa | carrega modelos? |
> |---|---|---|
> | `main()` | o CLI (`bash scripts/construct.sh`) | **sim** — a cada execução |
> | `build(cfg, modelos)` | a API | **não** — recebe os já carregados |
>
> Nenhuma das duas interfere na outra.

---

# PARTE 1 — Instalação dos arquivos

```
<raiz-do-RefCap>/
├── construct.py                        ← SUBSTITUIR pelo novo
├── config/cfg.py                       ← "whole" nos choices
├── dataset/viddataset.py               ← max(1, int(duration))
├── pipeline/propgenerator/
│   ├── __init__.py                     ← + from . import WholePropGener
│   └── WholePropGener.py               ← copiar
├── pytest.ini                          ← copiar
├── test/whole_propgen/
│   ├── conftest.py
│   └── test_whole_propgen.py
└── api/
    ├── app.py                          ← com a rota GET /teste/construct
    ├── carregador.py                   ← carrega os 4 (3 + spaCy)
    ├── jobs.py
    ├── ponte_refcap.py
    ├── supervisord.conf
    ├── diagnostico_gpu.py
    ├── diagnostico_supervisord.py
    └── validar_modelos_locais.py
```

**Confirme que os patches estão aplicados:**
```bash
cd <raiz-do-RefCap>
grep -c "def build" construct.py              # deve ser 1
grep -c "setdefault" construct.py             # deve ser 2
grep -c "n_amostras" dataset/viddataset.py    # deve ser 1
grep -c '"whole"' config/cfg.py               # deve ser >= 1
grep -c "WholePropGener" pipeline/propgenerator/__init__.py   # deve ser 1
```

---

# PARTE 2 — Caminho A: pelo terminal (o CLI de sempre)

**[J] O CLI não mudou.** Use quando for processar um lote grande de uma vez, sem serviço.

## A.1 Rodar o construct como antes

```bash
cd <raiz-do-RefCap>
bash scripts/construct.sh
```

**O que acontece:** `main()` → lê `sys.argv` → `build(cfg)` **sem** modelos → cai no `load_pretrained_models(cfg)` → comportamento idêntico ao de antes do patch.

## A.2 Usando o seu `WholePropGenerator`

No `scripts/construct.sh`:
```bash
proposal_generator=whole
caption_generator=blip
```

**O que muda:** um segmento por vídeo cobrindo `[0, duration]`, com o ranking de legendas no `proposals.json`.

## A.3 Onde os resultados aparecem

```
results/construct/{collection}/{construct_name}/
├── settings.json
├── proposals.json      ← ★ o ranking completo está aqui
├── prop_sims.pt
└── tree.json           ← a árvore final

meta/
├── captions/{collection}_blip.jsonl     ← cache de legendas
├── framefeatures/{collection}.pt
└── scores/{collection}_blip.pt
```

**Para ver o ranking:**
```bash
python -m json.tool results/construct/<collection>/<name>/proposals.json | head -60
```

## A.4 Rodar os testes

```bash
cd <raiz-do-RefCap>
pytest test/whole_propgen -v
```
Espere **48 passed**.

---

# PARTE 3 — Caminho B: pela interface FastAPI

## B.1 Subir o serviço

**Em desenvolvimento (à mão):**
```bash
cd <raiz-do-RefCap>/api
export REFCAP_CAPTION_MODEL=/caminho/local/blip-image-captioning-large
export REFCAP_BLIP_ITM_MODEL=/caminho/local/blip-itm-base-coco
export REFCAP_SENTENCE_TRANSFORMER=/caminho/local/paraphrase-distilroberta-v2
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
python app.py
```

**Em produção:**
```bash
supervisorctl reread && supervisorctl update
supervisorctl status refcap-api
```

## B.2 Confirmar que os modelos estão residentes

```bash
curl -s localhost:8000/health | python -m json.tool
```

**Olhe estes três campos:**
```json
"modelos": {
    "pronto": true,                      ← os 4 objetos existem
    "device": "cuda",
    "modelos": [
        {"nome": "cap_gen", "segundos": 12.4},
        {"nome": "blip_itm", "segundos": 5.1},
        {"nome": "sentence_transformer", "segundos": 2.3},
        {"nome": "spacy", "segundos": 0.9}
    ],
    "gpu": {
        "alocado_mb": 2847.3             ← ★ > 0 = na GPU
    }
}
```

**[J] O `alocado_mb` é o que responde de verdade.** `pronto: true` só diz que os objetos existem; se `alocado_mb` for 0, eles estão na CPU.

## B.3 ★ Rodar o construct num vídeo — pela interface

**Pelo navegador (Swagger):**
```
http://seu-servidor:8000/docs
```
Localize `GET /teste/construct`, clique em **Try it out**, preencha `video` e execute.

**Pelo terminal:**
```bash
curl -s "localhost:8000/teste/construct?video=cena_001.mp4" | python -m json.tool
```

**Os quatro parâmetros:**

| parâmetro | default | para quê |
|---|---|---|
| `video` | *(obrigatório)* | nome do arquivo em `video_root` |
| `collection` | `teste_api` | isola os artefatos deste teste |
| `proposal_generator` | `whole` | use `qm` para comparar com o original |
| `limpar_cache` | `true` | apaga os caches antes, forçando processamento real |

## B.4 Como ler a resposta

```json
{
  "ok": true,
  "video": "cena_001.mp4",
  "segundos": 8.4,

  "passos": [
    "vídeo encontrado: /root/Charades_v1/cena_001.mp4",
    "annos escrito: /caminho/annos/teste_api/vcmr.jsonl",
    "caches limpos: 3",
    "cfg montado (collection=teste_api, propgen=whole)",
    "build() concluído"
  ],

  "propostas": [
    { "st": 0.0, "ed": 4.0,
      "legenda": "a woman standing in a kitchen",
      "keywords": ["woman", "kitchen", "standing"] }
  ],

  "ranking": {
    "rank_by": "scene_score",
    "n_raw": 4,
    "n_distinct": 3,
    "ranking": [ {"cap": "...", "scene_score": ..., "self_score": ...}, ... ]
  },

  "modelos_reaproveitados": {
    "gpu_alocado_mb_antes":  2847.3,
    "gpu_alocado_mb_depois": 2847.3
  }
}
```

**★ A prova que você procura está em `modelos_reaproveitados`.** Se os dois valores forem **próximos e maiores que zero**, o `build()` usou os modelos que já estavam na GPU — não recarregou nada.

**[J] Se `depois` for muito maior que `antes`**, algo carregou modelo durante o build. Nesse caso, confira se o `pretrained_models` chegou completo.

**O campo `passos`** é o diagnóstico: se falhar no meio, ele mostra até onde chegou.

## B.5 Comparar os dois geradores de proposta

```bash
curl -s "localhost:8000/teste/construct?video=cena_001.mp4&proposal_generator=whole&collection=cmp_whole" \
  | python -c "import json,sys; d=json.load(sys.stdin); print('WHOLE:', [p['legenda'] for p in d['propostas']])"

curl -s "localhost:8000/teste/construct?video=cena_001.mp4&proposal_generator=qm&collection=cmp_qm" \
  | python -c "import json,sys; d=json.load(sys.stdin); print('QM   :', [p['legenda'] for p in d['propostas']])"
```

**[J] Use `collection` diferente em cada um** — senão o segundo reaproveitaria os artefatos do primeiro.

## B.6 ★ ATUALIZADO — O caminho de produção: `POST /jobs`

**A resposta traz o resultado completo** — a chamada aguarda o processamento.

```bash
# cena única
curl -X POST http://localhost:8000/jobs -H 'Content-Type: application/json' -d '{
  "scene_id": "cena_01", "video_id": "vidA", "program_id": "prog1",
  "scene_video_path": "/caminho/prog1/vidA/cena_01.mp4"
}'

# lote
curl -X POST http://localhost:8000/jobs -H 'Content-Type: application/json' -d '{
  "items": [
    {"scene_id":"cena_01","video_id":"vidA","program_id":"prog1","scene_video_path":"..."},
    {"scene_id":"cena_02","video_id":"vidB","program_id":"prog1","scene_video_path":"..."}
  ]
}'
```

**A resposta (HTTP 200):**
```json
{
  "job_id": "9e8adacb...",
  "estado": "concluido",
  "resumo": {"total": 2, "ok": 2, "erros": 0},
  "items": [
    {
      "scene_id": "cena_01",
      "scene_caption_en": "a woman preparing food in a kitchen",
      "keywords_en": [{"token":"woman","weight":0.6}, ...],
      "model_name": "refcap", "model_version": "v1", "status": "success"
    }
  ]
}
```

**Para lotes grandes — o modo assíncrono:**
```bash
curl -X POST http://localhost:8000/jobs -H 'Content-Type: application/json' -d '{
  "items": [ ... ], "assincrono": true
}'
# -> 202 + job_id
curl http://localhost:8000/jobs/<job_id>
```

**[J] Quando usar cada um:** o síncrono segura a conexão até terminar — simples e direto, mas um proxy pode derrubar conexões muito longas. O assíncrono evita isso, ao custo de uma consulta a mais.

**Campos opcionais** em qualquer das formas: `collection`, `proposal_generator`, `limpar_cache`, `callback_url`, `assincrono`.

---

---

# PARTE 4 — Os scripts de diagnóstico

| script | quando usar | comando |
|---|---|---|
| `validar_modelos_locais.py` | antes de subir, ou se o carregamento falhar | `--caption <dir> --itm <dir> --st <dir>` |
| `diagnostico_gpu.py` | se o `alocado_mb` for 0 ou a GPU não aparecer | `--carregar --manter` |
| `diagnostico_supervisord.py` | se o serviço reiniciar em loop | `--logs /var/log/refcap-api` |

**[J] A ordem quando algo falha:** valide os modelos → cheque a GPU → só então investigue o supervisord. Os dois primeiros são baratos e cobrem a maioria dos casos.

---

# PARTE 5 — Erros comuns e o que fazer

| erro | causa | correção |
|---|---|---|
| `404` com `"vídeo não encontrado"` | nome errado ou `video_root` errado | a resposta traz `video_root` e os primeiros arquivos de lá |
| `503 modelos ainda não carregados` | serviço subiu com `REFCAP_CARREGAR_MODELOS=0` | remova a variável e reinicie |
| `KeyError: 'blip_itrtv_model'` | dicionário incompleto | os **3** modelos são obrigatórios |
| `"VID CNT: 0"` no log, sem propostas | o vídeo não entrou no `annos` | a rota de teste escreve sozinha; no CLI, use o `make_annos.py` |
| `ValueError: need at least one array to stack` | vídeo com menos de 1 s | confirme o patch do `viddataset.py` |
| `alocado_mb` cresce a cada chamada | algo está recarregando modelo | confira se o `build()` recebeu o dicionário |
| serviço reinicia em loop | ver `diagnostico_supervisord.py` | causa mais comum: caminho de modelo errado |

---

# PARTE 6 — Referência rápida

```bash
# ---------- TERMINAL ----------
bash scripts/construct.sh                       # lote, CLI de sempre
pytest test/whole_propgen -v                    # 48 passed
python -m json.tool results/construct/<col>/<name>/proposals.json

# ---------- SERVIÇO ----------
python app.py                                   # subir à mão
supervisorctl status refcap-api                 # estado no supervisord
curl -s localhost:8000/health | python -m json.tool

# ---------- TESTE PELA API ----------
curl -s "localhost:8000/teste/construct?video=NOME.mp4" | python -m json.tool
http://seu-servidor:8000/docs                   # Swagger, com Try it out

# ---------- PRODUÇÃO ----------
curl -s -X POST localhost:8000/jobs -H 'Content-Type: application/json' \
     -d '{"videos":["NOME.mp4"]}'
curl -s localhost:8000/jobs/<job_id> | python -m json.tool

# ---------- DIAGNÓSTICO ----------
python validar_modelos_locais.py --caption <d> --itm <d> --st <d>
python diagnostico_gpu.py --carregar --manter
python diagnostico_supervisord.py --logs /var/log/refcap-api
```

---

# PARTE 7 — Limites deste guia

**[J]**

- **Nada foi executado com GPU ou vídeo real** nesta sessão. Validei estrutura, rotas, códigos de retorno e a lógica do reaproveitamento com objetos falsos.
- ~~O `POST /jobs` está incompleto~~ → **implementado**, síncrono por padrão, nos dois formatos acordados.
- ~~A decisão de isolamento~~ → **resolvida**: `collection` = pedido > `program_id` > `job_id`.
- **Sem limite de tamanho de lote nem timeout por job.** No modo síncrono, um lote muito grande pode esbarrar em timeout de proxy — use `"assincrono": true`.
- **Sem upload de arquivo** — os vídeos precisam já estar em `video_root`.
- **Os tempos e valores de exemplo** na Parte 3 são ilustrativos, não medidos.

---

*Guia de uso dos dois caminhos: o CLI, que não mudou, e a API, que reaproveita os modelos residentes. O ponto central é o `GET /teste/construct`, que roda o pipeline completo num vídeo e devolve — além do ranking — a medida de GPU antes e depois do `build()`, que é a prova de que nada foi recarregado.*
