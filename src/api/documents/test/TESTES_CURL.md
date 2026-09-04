# Testes Manuais via `curl`
## Todas as Combinações, Caso a Caso

---

> **Para quando você quer testar à mão** — investigar um caso específico, ver a resposta crua, ou entender o comportamento sem a camada do script.
>
> **O `| python3 -m json.tool` é opcional.** Ele só formata a saída. O `curl` sozinho faz a requisição inteira; sem o pipe, a resposta vem numa linha só.
>
> **Convenções deste documento:**
> ```bash
> API=http://localhost:8000
> BASE=/tmp/teste_refcap        # criado por preparar_teste.sh
> PROG=prog_teste
> ```

---

# PARTE 1 — Antes de qualquer coisa

## 1.1 O serviço está no ar e com os modelos?

```bash
curl -s $API/health | python3 -m json.tool
```

```json
{
  "status": "ok",
  "service": "caption-api",
  "refcap_root": "/caminho/para/src",
  "models": {
    "ready": true,
    "device": "cuda",
    "models": [
      {"name": "cap_gen", "id": "...", "load_seconds": 12.4},
      {"name": "blip_itm", "id": "...", "load_seconds": 5.1},
      {"name": "sentence_transformer", "id": "...", "load_seconds": 2.3},
      {"name": "spacy", "id": "en_core_web_sm", "load_seconds": 0.9}
    ],
    "gpu": {
      "available": true,
      "allocated_mb": 2847.3,
      "cuda_visible_devices": "0"
    }
  },
  "queued_jobs": 0
}
```

**★ O campo que importa é `models.gpu.allocated_mb`:**

| valor | significa |
|---|---|
| **> 0 e estável** entre chamadas | modelos residentes na GPU ✓ |
| **0** com `ready: true` | os objetos existem, mas estão na **CPU** |
| `available: false` | o torch não vê GPU — veja `TESTES_DIAGNOSTICO.md` |

## 1.2 Só o número da GPU, para comparar antes/depois

```bash
curl -s $API/health | python3 -c "import sys,json;print(json.load(sys.stdin)['models']['gpu'].get('allocated_mb'))"
```

Rode antes e depois de processar. **O número deve ser o mesmo.**

---

# PARTE 2 — Legendagem: o caminho feliz

## 2.1 Uma cena

```bash
curl -X POST $API/caption -H 'Content-Type: application/json' -d '{
  "scene_id": "cena_01",
  "video_id": "vidA",
  "program_id": "prog_teste",
  "scene_video_path": "/tmp/teste_refcap/prog_teste/vidA/cena_01.mp4"
}'
```

**A resposta (HTTP 200) traz o resultado completo** — a chamada aguarda o processamento:

```json
{
  "state": "concluded",
  "program_id": "prog_teste",
  "summary": {"total": 1, "ok": 1, "errors": 0},
  "items": [
    {
      "scene_id": "cena_01",
      "scene_caption_en": "a woman preparing food in a kitchen",
      "keywords_en": [
        {"token": "woman",   "weight": 1.0},
        {"token": "kitchen", "weight": 1.0},
        {"token": "food",    "weight": 1.0}
      ],
      "model_name": "refcap",
      "model_version": "v1",
      "status": "success"
    }
  ],
  "groups": [...],
  "persisted": {"gravadas": 1, "jsonl": "...", "scenes": "..."},
  "seconds": 4.2
}
```

**Sobre o `keywords_en`:** só entram palavras **contidas na legenda**, todas com `weight: 1.0`. O cálculo de peso está suspenso até a decisão sobre o GloVe — a função existe e está documentada, mas inerte.

## 2.2 Lote — dois diretórios

```bash
curl -X POST $API/caption/batch -H 'Content-Type: application/json' -d '{
  "items": [
    {"scene_id":"cena_02","video_id":"vidA","program_id":"prog_teste",
     "scene_video_path":"/tmp/teste_refcap/prog_teste/vidA/cena_02.mp4"},
    {"scene_id":"cena_04","video_id":"vidB","program_id":"prog_teste",
     "scene_video_path":"/tmp/teste_refcap/prog_teste/vidB/cena_04.mp4"}
  ]
}'
```

**★ Confira o `groups` na resposta:**
```bash
curl -s -X POST $API/caption/batch -H 'Content-Type: application/json' -d '{...}' \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
for g in d['groups']:
    print(f\"{g['cenas']} cena(s) em {g['diretorio']}  (collection={g['collection']})\")
"
```
```
1 cena(s) em /tmp/teste_refcap/prog_teste/vidA  (collection=prog_teste)
1 cena(s) em /tmp/teste_refcap/prog_teste/vidB  (collection=prog_teste)
```

**Dois grupos = dois `build()`.** É assim que deve ser: o RefCap lista **um diretório** por execução, então cenas de `video_id` diferentes exigem chamadas separadas.

## 2.3 ★ O vídeo curto — o teste do patch

```bash
curl -X POST $API/caption -H 'Content-Type: application/json' -d '{
  "scene_id": "cena_03",
  "video_id": "vidA",
  "program_id": "prog_teste",
  "scene_video_path": "/tmp/teste_refcap/prog_teste/vidA/cena_03.mp4"
}'
```

A `cena_03` tem **0,52 s**. Sem o patch `max(1, int(duration))` no `viddataset.py`, `int(0.52)` daria 0 frames e o `np.stack([])` derrubaria o processo com `ValueError: need at least one array to stack`.

**Se der `status: "success"`, o patch está aplicado.**

## 2.4 Modo assíncrono

Acima do limiar (default 30), a API muda sozinha. Para testar sem 31 cenas, force:

```bash
curl -X POST $API/caption -H 'Content-Type: application/json' -d '{
  "scene_id": "cena_01", "video_id": "vidA", "program_id": "prog_teste",
  "scene_video_path": "/tmp/teste_refcap/prog_teste/vidA/cena_01.mp4",
  "assincrono": true
}'
```

**A resposta (HTTP 202) é um recibo, não o resultado:**
```json
{
  "state": "accepted",
  "program_id": "prog_teste",
  "scenes": ["cena_01"],
  "total": 1,
  "check_at": "/caption/prog_teste",
  "reason": "requested"
}
```

O resultado aparece depois em `GET /caption/prog_teste`.

---

# PARTE 3 — O cache

## 3.1 Reprocessar: deve pular

Rode a **mesma** requisição da §2.1 de novo, cronometrando:

```bash
time curl -s -o /dev/null -X POST $API/caption -H 'Content-Type: application/json' -d '{
  "scene_id":"cena_01","video_id":"vidA","program_id":"prog_teste",
  "scene_video_path":"/tmp/teste_refcap/prog_teste/vidA/cena_01.mp4"}'
```

**Deve ser muito mais rápido** — o BLIP não roda. Confirme no `groups`:
```bash
... | python3 -c "import sys,json;print('em cache:', json.load(sys.stdin)['groups'][0]['estavam_em_cache'])"
```

## 3.2 `force: true` — reprocessar de propósito

```bash
time curl -s -X POST $API/caption -H 'Content-Type: application/json' -d '{
  "scene_id":"cena_01","video_id":"vidA","program_id":"prog_teste",
  "scene_video_path":"/tmp/teste_refcap/prog_teste/vidA/cena_01.mp4",
  "force": true}' | python3 -c "import sys,json;print('cache_limpo:', json.load(sys.stdin)['groups'][0].get('cache_limpo'))"
```

**Deve ser tão lento quanto a primeira vez.** Se for rápido, o cache não foi limpo.

## 3.3 ★ O `force` é cirúrgico — confirme

Depois do `force` na `cena_01`, as outras devem continuar em cache:

```bash
python3 -c "
import json
c = [json.loads(l)['vid_name'] for l in open('meta/captions/prog_teste_blip.jsonl') if l.strip()]
print('cenas no cache:', c)
"
```

**As outras cenas devem estar lá.** Se sumiram, o `force` apagou o arquivo inteiro em vez de remover uma chave — o que seria destrutivo num programa com centenas de cenas.

---

# PARTE 4 — Os cinco códigos de erro

## 4.1 `FILE_NOT_FOUND` — o caminho não existe

```bash
curl -X POST $API/caption -H 'Content-Type: application/json' -d '{
  "scene_id": "fantasma", "program_id": "prog_teste",
  "scene_video_path": "/tmp/nao_existe/x.mp4"
}'
```
```json
{"items": [{"scene_id": "fantasma", "status": "error",
            "error_code": "FILE_NOT_FOUND",
            "message": "caminho não encontrado: /tmp/nao_existe/x.mp4"}]}
```

## 4.2 `SCENE_NOT_FOUND` — o caminho existe, a cena não

```bash
curl -X POST $API/caption -H 'Content-Type: application/json' -d '{
  "scene_id": "cena_99", "program_id": "prog_teste",
  "scene_video_path": "/tmp/teste_refcap/prog_teste/vazio"
}'
```

**A distinção entre os dois códigos importa:** `FILE_NOT_FOUND` = o caminho não existe de todo; `SCENE_NOT_FOUND` = existe, mas não há vídeo com aquele `scene_id`.

## 4.3 ★ O fallback removido — o teste mais importante

O `vidB` tem **um** vídeo: `cena_04.mp4`. Peça outra cena apontando para o **diretório**:

```bash
curl -X POST $API/caption -H 'Content-Type: application/json' -d '{
  "scene_id": "cena_77", "program_id": "prog_teste",
  "scene_video_path": "/tmp/teste_refcap/prog_teste/vidB"
}'
```

**Deve dar `SCENE_NOT_FOUND`.**

Antes da Etapa 2, existia um fallback: "se o diretório tem um vídeo só, use ele". Isso legendava a `cena_04` e devolvia **`success`** — você receberia a legenda do vídeo errado, sem nenhum aviso.

## 4.4 `INVALID_REQUEST` — pedido vazio

```bash
curl -X POST $API/caption -H 'Content-Type: application/json' -d '{}'
```
HTTP **400** (ou 422, se o Pydantic pegar antes).

## 4.5 `CAPTION_FAILED` — o pipeline rodou e não produziu legenda

Difícil de forçar com vídeos válidos. Acontece quando o vídeo não decodifica, ou quando a cena não entra no `annos`. Se aparecer, a mensagem indica a causa.

## 4.6 ★ Erro parcial no lote — não derruba as outras

```bash
curl -X POST $API/caption/batch -H 'Content-Type: application/json' -d '{
  "items": [
    {"scene_id":"cena_01","video_id":"vidA","program_id":"prog_teste",
     "scene_video_path":"/tmp/teste_refcap/prog_teste/vidA/cena_01.mp4"},
    {"scene_id":"ruim","program_id":"prog_teste","scene_video_path":"/nada/x.mp4"},
    {"scene_id":"cena_02","video_id":"vidA","program_id":"prog_teste",
     "scene_video_path":"/tmp/teste_refcap/prog_teste/vidA/cena_02.mp4"}
  ]
}'
```

**Espera HTTP 200** com:
```json
{"summary": {"total": 3, "ok": 2, "errors": 1}}
```

**Note que é 200, não 500.** Uma cena ruim vira `status: "error"` **dentro** do item; o HTTP só vira 500 se o job inteiro falhar.

---

# PARTE 5 — Consultar o persistido

## 5.1 Todas as cenas de um programa

```bash
curl -s "$API/caption/prog_teste" | python3 -m json.tool
```

## 5.2 Uma cena

```bash
curl -s "$API/caption/prog_teste?scene_id=cena_01" | python3 -m json.tool
```

## 5.3 Várias cenas

```bash
curl -s "$API/caption/prog_teste?scene_id=cena_01&scene_id=cena_02" | python3 -m json.tool
```

## 5.4 Programa que nunca existiu

```bash
curl -s "$API/caption/programa_inventado" | python3 -m json.tool
```
```json
{"program_id": "programa_inventado", "items": [], "summary": {"total": 0, "ok": 0, "errors": 0}}
```

**HTTP 200, não 404** — assim o cliente trata um caso só, em vez de distinguir "não existe" de "existe e está vazio".

## 5.5 Só as legendas, em formato de tabela

```bash
curl -s "$API/caption/prog_teste" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for it in d['items']:
    kw = ', '.join(k['token'] for k in it.get('keywords_en', []))
    print(f\"{it['scene_id']:<12} {it['status']:<8} {it.get('scene_caption_en') or it.get('message','')}\")
    if kw: print(f\"{'':<12} keywords: {kw}\")
"
```

---

# PARTE 6 — ★ O isolamento entre programas

Este é o teste que confirma que o erro silencioso mais grave não existe.

```bash
# a MESMA scene_id, em OUTRO program_id
curl -X POST $API/caption -H 'Content-Type: application/json' -d '{
  "scene_id": "cena_01", "video_id": "vidX", "program_id": "prog_outro",
  "scene_video_path": "/tmp/teste_refcap/prog_outro/vidX/cena_01.mp4"
}'
```

Depois compare as duas:

```bash
echo "prog_teste:"; curl -s "$API/caption/prog_teste?scene_id=cena_01" \
  | python3 -c "import sys,json;print(' ', json.load(sys.stdin)['items'][0]['scene_caption_en'])"
echo "prog_outro:"; curl -s "$API/caption/prog_outro?scene_id=cena_01" \
  | python3 -c "import sys,json;print(' ', json.load(sys.stdin)['items'][0]['scene_caption_en'])"
```

**As legendas devem ser DIFERENTES** — são vídeos diferentes.

Se saírem iguais, o `collection` não isolou: o segundo programa teria reaproveitado o cache do primeiro, devolvendo a legenda errada com `status: "success"`.

**Confirme no disco que os caches são separados:**
```bash
ls meta/captions/
# prog_teste_blip.jsonl    prog_outro_blip.jsonl    ← dois arquivos
```

---

# PARTE 7 — As rotas de diagnóstico

Elas rodam o pipeline **e** devolvem diagnóstico junto: `passos`, `modelos_reaproveitados`, `exp_dir`, ranking completo.

**★ Usam um `collection` próprio (`diagnostics`)** — não o `program_id`. Você testa sem contaminar dados reais.

## 7.1 Um vídeo

```bash
curl -s "$API/diagnostics/caption?video=cena_01.mp4" | python3 -m json.tool
```

O `video` é o nome do arquivo no `video_root` **configurado** — não um caminho completo.

**Parâmetros:** `collection`, `proposal_generator` (`whole` ou `qm`), `force`.

## 7.2 Um diretório inteiro

```bash
curl -s "$API/diagnostics/caption-batch?diretorio=/tmp/teste_refcap/prog_teste/vidA&limite=2" \
  | python3 -m json.tool
```

**Parâmetros:** `diretorio`, `collection`, `proposal_generator`, `force` (default `false`), `limite`, `extensoes`.

**[J] Use `limite` na primeira vez.** A rota é síncrona; um diretório grande estoura o timeout.

## 7.3 ★ A prova do reaproveitamento dos modelos

```bash
curl -s "$API/diagnostics/caption?video=cena_01.mp4" | python3 -c "
import sys,json
d = json.load(sys.stdin)
m = d['modelos_reaproveitados']
print('antes :', m['gpu_alocado_mb_antes'])
print('depois:', m['gpu_alocado_mb_depois'])
"
```

**Valores próximos e maiores que zero** = o `build()` usou os modelos que já estavam na GPU, sem recarregar nada.

## 7.4 Comparar os dois geradores de proposta

```bash
for g in whole qm; do
  echo "=== $g ==="
  curl -s "$API/diagnostics/caption?video=cena_01.mp4&proposal_generator=$g&collection=cmp_$g" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(' ', d.get('scene_caption_en'))"
done
```

**Use `collection` diferente em cada um** — senão o segundo reaproveita os artefatos do primeiro.

## 7.5 Confirmar que o diagnóstico não contamina

```bash
ls annos/
# prog_teste  prog_outro  diagnostics    ← os três, separados
```

---

# PARTE 8 — Campos opcionais da requisição

Válidos em `/caption` e `/caption/batch`:

| campo | default | para quê |
|---|---|---|
| `force` | `false` | reprocessa, limpando o cache **daquelas cenas** |
| `assincrono` | `false` | força um modo; acima do limiar já muda sozinho |
| `proposal_generator` | `"whole"` | `"qm"` para comparar com o original |
| `callback_url` | — | POST no seu endpoint quando terminar |

**Exemplo com todos:**
```bash
curl -X POST $API/caption/batch -H 'Content-Type: application/json' -d '{
  "items": [ ... ],
  "force": true,
  "assincrono": true,
  "proposal_generator": "whole",
  "callback_url": "http://seu-sistema/callback"
}'
```

**`collection` NÃO é aceito** — ele é derivado do `program_id`. Aceitar um override quebraria o isolamento.

---

# PARTE 9 — Sequência recomendada

Se for testar tudo à mão, nesta ordem:

```
1.  /health                          modelos residentes?
2.  anote o allocated_mb
3.  POST /caption (cena_01)          o caminho feliz
4.  POST /caption/batch (2 dirs)     o agrupamento
5.  POST /caption (cena_03, 0.5s)    ★ o patch do vídeo curto
6.  POST /caption (cena_01) de novo  ★ deve ser RÁPIDO (cache)
7.  POST /caption (cena_01) + force  ★ deve ser LENTO
8.  confira o cache: as outras sobreviveram?
9.  os 4 erros (Parte 4)
10. GET /caption/{pid} + filtros
11. ★ o isolamento (Parte 6)
12. /diagnostics/* (Parte 7)
13. /health de novo                  ★ allocated_mb IGUAL ao do passo 2
```

**O passo 13 é o fecho:** se o `allocated_mb` for o mesmo do início, os modelos ficaram residentes o tempo todo — nenhuma requisição recarregou nada.

---

*Testes manuais via `curl`. Para a bateria automática, veja `README_TESTES.md`; para problemas de infraestrutura, `TESTES_DIAGNOSTICO.md`.*
