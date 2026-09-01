# Requisições POST pelo Terminal — Cola Rápida
## Comandos `curl` prontos, validados contra a API real

---

> **Todos os comandos abaixo foram executados** contra um servidor uvicorn de verdade, com `curl` real. As saídas mostradas são as que apareceram.
>
> **Ajuste apenas os caminhos.** Os nomes dos campos são os que a API espera.

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

**Resposta imediata (202):**
```json
{
    "job_id": "9e8adacb756b4ab0ba570279e2d34478",
    "estado": "na_fila",
    "consultar_em": "/jobs/9e8adacb756b4ab0ba570279e2d34478"
}
```

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

## 3. Consultar o resultado

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

## 4. POST + consulta automática, numa linha só

Sem copiar o `job_id` à mão:

```bash
JID=$(curl -s -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"scene_id":"cena_solo","video_id":"vidUnico","program_id":"prog2","scene_video_path":"/caminho/prog2/vidUnico"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

echo "job: $JID"

# aguarda terminar e mostra o resultado
until curl -s "http://localhost:8000/jobs/$JID" \
      | python3 -c "import sys,json; e=json.load(sys.stdin)['estado']; print(e); exit(0 if e in ('concluido','falhou') else 1)"; do
  sleep 3
done

curl -s "http://localhost:8000/jobs/$JID" | python3 -m json.tool
```

---

## 5. Só as legendas e keywords (sem o resto do JSON)

```bash
curl -s "http://localhost:8000/jobs/$JID" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for it in d['resultado']['items']:
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
