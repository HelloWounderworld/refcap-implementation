# Requisições POST pelo Terminal — Cola Rápida
## Comandos `curl` prontos, validados contra a API real

---

> **Todos os comandos abaixo foram executados** contra um servidor uvicorn de verdade, com `curl` real. As saídas mostradas são as que apareceram.
>
> **Ajuste apenas os caminhos.** Os nomes dos campos são os que a API espera.
>
> ---
>
> ### ★ Sobre o `| python3 -m json.tool`
>
> **Ele NÃO é necessário.** O `curl` sozinho faz a requisição inteira. O pipe só
> **formata a resposta** para ficar legível.
>
> **[V] Verificado — `curl` puro, sem pipe:**
> ```bash
> curl -X POST http://localhost:8000/jobs -H 'Content-Type: application/json' -d '{...}'
> ```
> ```
> {"job_id":"...","estado":"concluido","resumo":{"total":1,"ok":1,"erros":0},"items":[{...}]}
> ```
> Funciona igual — só vem tudo numa linha.
>
> | você escreve | o que muda |
> |---|---|
> | `curl -X POST ...` | resposta crua, uma linha, com barra de progresso |
> | `curl -s -X POST ...` | o `-s` só **esconde a barra de progresso** |
> | `... \| python3 -m json.tool` | formata em várias linhas (precisa de python) |
> | `... \| jq` | idem, mais colorido (precisa de `jq` instalado) |
> | `... -o saida.json` | grava num arquivo em vez de mostrar |
>
> **[J] Use o pipe quando for LER a resposta**; omita quando for só disparar a
> requisição ou quando outro programa for consumir a saída.

---

## 0. Confirmar que o serviço responde

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Olhe o `modelos.gpu.alocado_mb`: **maior que zero** = modelos residentes na GPU.

---

## 1. LOTE — conjunto de vídeos

```bash
curl -s -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {"scene_id":"cena_01","video_id":"vidA","program_id":"prog1","scene_video_path":"/caminho/prog1/vidA/cena_01.mp4"},
      {"scene_id":"cena_02","video_id":"vidA","program_id":"prog1","scene_video_path":"/caminho/prog1/vidA/cena_02.mp4"},
      {"scene_id":"cena_04","video_id":"vidB","program_id":"prog1","scene_video_path":"/caminho/prog1/vidB/cena_04.mp4"}
    ]
  }' | python3 -m json.tool
```

**★ A resposta traz o RESULTADO COMPLETO** (a chamada aguarda o processamento):
```json
{
  "job_id": "9e8adacb...",
  "estado": "concluido",
  "resumo": {"total": 3, "ok": 3, "erros": 0},
  "items": [
    {
      "scene_id": "cena_01",
      "scene_caption_en": "a woman preparing food in a kitchen",
      "keywords_en": [
        {"token": "woman",   "weight": 0.6},
        {"token": "kitchen", "weight": 0.6},
        {"token": "food",    "weight": 0.6}
      ],
      "model_name": "refcap",
      "model_version": "v1",
      "status": "success"
    }
  ],
  "segundos": 12.4
}
```

**Nao daria para colocar a possibilidade de o status informar o seguinte, caso de algum erro, como abaixo?**

```json
{
  "job_id": "9e8adacb...",
  "estado": "concluido",
  "resumo": {"total": 3, "ok": 3, "erros": 0},
  "items": [
    {
      "scene_id": "cena_01",
      "scene_caption_en": "a woman preparing food in a kitchen",
      "keywords_en": [
        {"token": "woman",   "weight": 0.6},
        {"token": "kitchen", "weight": 0.6},
        {"token": "food",    "weight": 0.6}
      ],
      "model_name": "refcap",
      "model_version": "v1",
      "status": "error",
      "error_code": "INVALID_REQUEST",
      "message": "Invalid Request (alguma coisa do tipo...)"
    }
  ],
  "segundos": 12.4
}
```

**Sendo os erros de codigos sao como o seguinte**

```markdown
INVALID_REQUEST
CAPTION_FAILED
SCENE_NOT_FOUND
FILE_NOT_FOUND
INTERNAL_ERROR
```

**[V] Verificado com `curl` real:** `HTTP 200`, `estado: concluido`, `{"total": 3, "ok": 3, "erros": 0}`.

---

## 2. CENA ÚNICA — os campos no nível de cima

Sem o `items`. Aqui o `scene_video_path` aponta para um **diretório**:

```bash
curl -s -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "scene_id": "cena_solo",
    "video_id": "vidUnico",
    "program_id": "prog2",
    "scene_video_path": "/caminho/prog2/vidUnico"
  }' | python3 -m json.tool
```

---

## 2b. As mesmas duas, em `curl` PURO

Sem nenhum pipe — para colar e disparar:

```bash
# lote
curl -X POST http://localhost:8000/jobs -H 'Content-Type: application/json' -d '{"items":[{"scene_id":"cena_01","video_id":"vidA","program_id":"prog1","scene_video_path":"/caminho/prog1/vidA/cena_01.mp4"},{"scene_id":"cena_02","video_id":"vidA","program_id":"prog1","scene_video_path":"/caminho/prog1/vidA/cena_02.mp4"}]}'

# cena única
curl -X POST http://localhost:8000/jobs -H 'Content-Type: application/json' -d '{"scene_id":"cena_solo","video_id":"vidUnico","program_id":"prog2","scene_video_path":"/caminho/prog2/vidUnico"}'

# consultar
curl http://localhost:8000/jobs/COLE_O_JOB_ID
```

**A resposta vem assim** (uma linha, JSON compacto, com o resultado inteiro):
```
{"job_id":"...","estado":"concluido","resumo":{"total":2,"ok":2,"erros":0},"items":[{"scene_id":"cena_01",...}]}
```

---

## 3. Consultar um job já feito (opcional)

**Não é mais necessário para obter o resultado** — o POST já o devolve. Serve
para RECONSULTAR um job antigo, ou para acompanhar um job assíncrono.

```bash
curl -s http://localhost:8000/jobs/COLE_O_JOB_ID_AQUI | python3 -m json.tool
```

**Saída real do lote:**
```json
{
  "estado": "concluido",
  "resumo": {"total": 3, "ok": 3, "erros": 0},
  "items": [
    {
      "scene_id": "cena_01",
      "scene_caption_en": "a woman preparing food in a kitchen",
      "keywords_en": [
        {"token": "woman",   "weight": 0.6},
        {"token": "kitchen", "weight": 0.6},
        {"token": "food",    "weight": 0.6},
        {"token": "knife",   "weight": 0.0},
        {"token": "dog",     "weight": 0.0}
      ],
      "model_name": "refcap",
      "model_version": "v1",
      "status": "success"
    }
  ]
}
```

---

## 4. ★ Modo ASSÍNCRONO — quando o lote é grande

O modo padrão segura a conexão até terminar. Para lotes longos (onde um proxy
poderia derrubar a conexão), acrescente `"assincrono": true`:

```bash
curl -X POST http://localhost:8000/jobs -H 'Content-Type: application/json' \
  -d '{"scene_id":"cena_solo","program_id":"prog2","scene_video_path":"/caminho/prog2/vidUnico","assincrono":true}'
```

**Resposta imediata (202):**
```json
{"job_id":"02bb2239...","estado":"na_fila","consultar_em":"/jobs/02bb2239..."}
```

Depois consulte com o `GET /jobs/{id}` da seção 3, ou informe `callback_url`
para ser avisado quando terminar.

**[V] Verificado:** `HTTP 202` no POST, e o `GET` depois trouxe `concluido`.

---

## 5. Só as legendas e keywords (sem o resto do JSON)

Direto da resposta do POST:

```bash
curl -s -X POST http://localhost:8000/jobs -H 'Content-Type: application/json' \
  -d '{"scene_id":"cena_01","program_id":"prog1","scene_video_path":"/caminho/cena_01.mp4"}' \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
for it in d['items']:
    kw = ', '.join(f\"{k['token']}({k['weight']})\" for k in it['keywords_en'][:5])
    print(f\"{it['scene_id']:<14} {it['status']:<8} {it.get('scene_caption_en') or it.get('erro','')}\")
    print(f\"{'':<14} keywords: {kw}\")
"
```

---

## 6. Quando dá erro — como aparece

**Saída real com um caminho inexistente:**
```json
[
  {
    "scene_id": "fantasma",
    "scene_caption_en": null,
    "keywords_en": [],
    "model_name": "refcap",
    "model_version": "v1",
    "status": "error",
    "erro": "não encontrei a cena 'fantasma' em /tmp/nao_existe/x (tentei como arquivo, com as extensões ('.mp4', '.mkv', '.avi', '.webm', '.mov', '.m4v'), e como diretório)"
  }
]
```

**Num lote, uma cena ruim não derruba as outras** — ela recebe `status: "error"` e o resumo mostra `{"total": 4, "ok": 3, "erros": 1}`.

---

## 7. Campos opcionais

Acrescente ao corpo de qualquer uma das duas formas:

```json
{
  "...": "...",
  "collection": "meu_lote",        // isola cache; default = program_id
  "proposal_generator": "qm",       // default "whole" (o seu)
  "limpar_cache": true,             // default false
  "callback_url": "http://seu-sistema/callback"
}
```

---

## 8. Listar os jobs recentes

```bash
curl -s http://localhost:8000/jobs | python3 -c "
import sys, json
for j in json.load(sys.stdin)['jobs'][:10]:
    print(f\"{j['job_id'][:12]}  {j['estado']:<12} {j['criado_em'][:19]}\")
"
```

---

## 9. As rotas de teste síncronas (resposta imediata, sem job)

```bash
# um vídeo — o arquivo precisa estar no video_root configurado
curl -s "http://localhost:8000/teste/construct?video=cena_01.mp4" | python3 -m json.tool

# um diretório inteiro — use limite na primeira vez
curl -s "http://localhost:8000/teste/construct-lote?diretorio=/caminho/cenas&limite=3" | python3 -m json.tool
```

**[J] A diferença:** as rotas de teste são **síncronas** (você espera a resposta) e trazem diagnóstico junto (`passos`, `modelos_reaproveitados`, `exp_dir`). O `POST /jobs` é **assíncrono** e devolve só o contrato.

---

## Notas

**As três formas de `scene_video_path`** — todas funcionam:
```
/caminho/vidA/cena_01.mp4    arquivo com extensão
/caminho/vidA/cena_01        sem extensão (tenta .mp4, .mkv, .avi, .webm, .mov, .m4v)
/caminho/vidA                diretório (procura pelo scene_id lá dentro)
```

**O agrupamento por diretório.** Cenas de `video_id` diferentes vão para diretórios diferentes, e a API chama o `build()` uma vez por diretório. No log você vê:
```
[job 9e8adacb] build() em /caminho/prog1/vidA: 2 cena(s), collection=prog1
[job 9e8adacb] build() em /caminho/prog1/vidB: 1 cena(s), collection=prog1
```

**O `collection`** sai do `program_id` quando você não informa — cenas do mesmo programa compartilham cache.