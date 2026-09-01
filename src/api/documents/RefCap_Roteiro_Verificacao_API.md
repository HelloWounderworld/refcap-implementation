# Roteiro de Verificação — Do Zero ao Serviço no Ar
## Passo a Passo com Todos os Scripts, e o Que Fazer Quando Cada Um Falha

---

> **O que é este documento.** A sequência ordenada para colocar tudo de pé e confirmar que funciona, usando os scripts criados. Cada passo diz **o que rodar**, **o que esperar** e **o que fazer se falhar**.
>
> **A ordem não é arbitrária.** Vai do mais barato e mais provável de falhar para o mais caro. Os passos 1–4 não envolvem GPU nem modelos — se algo estiver errado ali, você descobre em segundos em vez de depois de minutos de carregamento.
>
> **Antes de tudo:** a Parte 0 traz a auditoria de conflitos.
>
> **★ ATUALIZADO (2ª revisão).** O `POST /jobs` processa de ponta a ponta **e agora é síncrono por padrão**: devolve o resultado completo em vez de 202 + `job_id`. Os passos afetados (1, 9) e a Parte 4 trazem a marca.

---

# PARTE 0 — Auditoria de conflitos (feita)

Você pediu para conferir se os scripts novos quebram algo. **[V] Onze verificações, todas limpas:**

| # | verificação | resultado |
|---|---|---|
| 1 | os **8** arquivos `.py` compilam | ✓ todos |
| 2 | grafo de imports | `app.py` → (carregador, jobs, ponte_refcap, **processamento**); os três diagnósticos **não importam nada do app** |
| 3 | colisão com módulos do RefCap | nenhuma |
| 4 | colisão com stdlib / pacotes instalados | nenhuma |
| 5 | serviço sobe após todas as mudanças | `/health` 200 |
| 6 | ciclo de job completo | POST 202 → GET `concluido` |
| 7 | suíte do `WholePropGenerator` | **48 passed** |
| 8 | pytest coleta algo de `api/` por engano? | **0 arquivos** |
| 9 | os 3 diagnósticos rodam standalone | ✓ |
| 10 | executam de fato (não só `--help`) | ✓ com códigos de saída corretos |
| 11 | rodar um diagnóstico afeta o app? | não — `/health` 200 depois |

**[J] Por que não há conflito:** os três diagnósticos importam **apenas stdlib** (`argparse`, `os`, `sys`, `pathlib`, `re`, `json`, `subprocess`). O `torch` e o `transformers` entram por *import tardio*, só quando de fato vão carregar algo. Eles não tocam no `app.py`, no `jobs.py` nem no `carregador.py`.

E o pytest não os coleta porque nenhum se chama `test_*.py`.

---

# PARTE 1 — Os arquivos e onde ficam

```
<projeto>/
└── src/                                  ← RefCap (ou o nome que você usa)
    ├── construct.py                      ← PATCH aplicado (Passo 2)
    ├── config/cfg.py                     ← "whole" nos choices
    ├── dataset/viddataset.py             ← PATCH do vídeo curto
    ├── pipeline/propgenerator/
    │   ├── __init__.py                   ← + linha de registro
    │   └── WholePropGener.py             ← seu componente
    ├── pytest.ini                        ← corrigido
    ├── test/whole_propgen/
    │   ├── conftest.py
    │   └── test_whole_propgen.py
    └── api/                              ← o serviço
        ├── app.py
        ├── carregador.py
        ├── jobs.py
        ├── ponte_refcap.py
        ├── processamento.py              ← ★ NOVO: contratos + pipeline
        ├── supervisord.conf
        ├── diagnostico_gpu.py
        ├── diagnostico_supervisord.py
        └── validar_modelos_locais.py
```

**[V] O `api/` pode ficar dentro **ou** ao lado do RefCap** — a descoberta é por marcador. Ambos testados.

---

# PARTE 2 — O roteiro

## Passo 1 — Aplicar os patches no RefCap

```bash
cd <raiz-do-RefCap>
git apply construct_reutilizavel.patch
git apply viddataset_video_curto.patch
```

**Confira:**
```bash
grep -n "def build" construct.py                    # deve existir
grep -n "setdefault" construct.py                   # linhas 2-3
grep -n "n_amostras" dataset/viddataset.py          # o max(1, ...)
grep -n '"whole"' config/cfg.py                     # nos choices
grep -n "WholePropGener" pipeline/propgenerator/__init__.py
grep -n "spacy_nlp" pipeline/propgenerator/WholePropGener.py   # ★ o reuso do spaCy
```

**Se algum faltar:** o patch não aplicou. Faça a edição à mão — cada uma está documentada no relatório correspondente.

---

## Passo 2 — Verificar que o CLI do RefCap não quebrou

```bash
cd <raiz-do-RefCap>
python construct.py --help
```

**Espere:** a lista de argumentos, sem erro. **[V] O patch preserva o CLI** — `main()` apenas delega para `build()`.

**Se falhar:** o `build()` foi extraído errado. Compare com o patch original.

---

## Passo 3 — A suíte do `WholePropGenerator`

```bash
cd <raiz-do-RefCap>
pytest test/whole_propgen -v
```

**Espere:** `48 passed`, em menos de um segundo.

**Este passo verifica muito mais do que parece.** Ele confirma que:
- o `WholePropGener.py` está no lugar certo
- a linha no `__init__.py` está lá (sem ela: **5 failed, 42 errors**)
- o `"whole"` está nos `choices`
- o registry do RefCap está intacto

**Se falhar com `ValueError: whole não registrado`:** falta a linha `from . import WholePropGener` no `__init__.py`.

**Se falhar com `ERROR: file or directory not found: #`:** comentário inline no `addopts` do `pytest.ini`. Use o `pytest.ini` corrigido.

---

## Passo 4 — Validar os modelos locais ★

**Este é o passo que mais evita dor de cabeça.** Não envolve GPU nem carrega nada.

```bash
cd <raiz-do-RefCap>/api
python validar_modelos_locais.py \
    --caption /caminho/local/blip-image-captioning-large \
    --itm     /caminho/local/blip-itm-base-coco \
    --st      /caminho/local/paraphrase-distilroberta-v2
```

**Espere:** `3 de 3 modelo(s) prontos para uso local`.

**Os três diagnósticos que ele dá, e o que fazer:**

| saída | causa | o que fazer |
|---|---|---|
| `⚠️ LAYOUT DE CACHE detectado` | você copiou a pasta `models--Org--nome/` | use o caminho que ele indica (`snapshots/<hash>/`) |
| `✗ FALTAM: ...` | a cópia veio incompleta | copie os arquivos que faltam do cache |
| `⚠️ parece um REPO-ID do Hub` | o caminho não é local | aponte para o diretório |

**Não conhece os caminhos?** Explore:
```bash
python validar_modelos_locais.py /caminho/dos/modelos
```

---

## Passo 5 — Conferir o ambiente e a GPU

```bash
cd <raiz-do-RefCap>/api
python diagnostico_gpu.py
```

**Espere:** bloco A com `torch.cuda.is_available() = True` e as GPUs listadas.

**Se `is_available() = False`:** o script lista as causas — build CPU-only do torch, `CUDA_VISIBLE_DEVICES=""`, ou driver incompatível. **Resolva antes de seguir.**

O bloco B mostra as variáveis de ambiente e avisa sobre `REFCAP_DEVICE=cpu`, `CUDA_VISIBLE_DEVICES` vazia e `REFCAP_CARREGAR_MODELOS=0`.

---

## Passo 6 — Carregar um modelo de verdade e medir a GPU

```bash
python diagnostico_gpu.py --carregar --manter \
    --modelo /caminho/local/blip-image-captioning-large
```

**Espere:**
```
antes  — alocado / reservado    0.0 MB / 0.0 MB
depois — alocado / reservado    XXXX MB / XXXX MB
delta alocado                   +XXXX MB
✓ O modelo OCUPA a GPU
PID deste processo: 12345
```

**Com `--manter`, o processo fica vivo.** Em outro terminal:
```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```
Você deve ver o PID na lista. **Ctrl+C encerra e a memória é liberada** — é esse o comportamento de "residente".

**Se `delta alocado` for ~0:** o modelo foi para a CPU. Confira `--device` e `CUDA_VISIBLE_DEVICES`.

**[J] Este passo é o que separa "o carregamento funciona" de "o serviço mantém".** Se ele passa, o problema (se houver) está no supervisord, não no modelo.

---

## Passo 7 — Subir o serviço à mão, sem modelos

```bash
cd <raiz-do-RefCap>/api
REFCAP_CARREGAR_MODELOS=0 python app.py
```

**Espere no log:**
```
iniciando serviço — RefCap em /caminho/para/src
REFCAP_CARREGAR_MODELOS=0 — subindo SEM os modelos
Uvicorn running on http://0.0.0.0:8000
```

Em outro terminal:
```bash
curl -s localhost:8000/health | python -m json.tool
```

**Espere:** `"servico": "ok"`, `"refcap_root"` apontando para o RefCap, `"pronto": false`.

**Se `refcap_root` estiver errado:** defina `REFCAP_ROOT`.

**Se `python app.py` não fizer nada:** você está numa versão antiga sem o bloco `__main__`. Use o `app.py` atualizado.

---

## Passo 8 — Subir o serviço à mão, COM os modelos

```bash
cd <raiz-do-RefCap>/api
export REFCAP_CAPTION_MODEL=/caminho/local/blip-image-captioning-large
export REFCAP_BLIP_ITM_MODEL=/caminho/local/blip-itm-base-coco
export REFCAP_SENTENCE_TRANSFORMER=/caminho/local/paraphrase-distilroberta-v2
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
python app.py
```

**Espere no log:** as três linhas de carregamento, com os tempos, e depois `modelos residentes prontos em XXs`.

**A verificação decisiva:**
```bash
curl -s localhost:8000/health | python -m json.tool
```
```json
"modelos": {
    "pronto": true,
    "device": "cuda",
    "modelos": [ {"nome": "cap_gen", ...}, ... ],
    "gpu": {
        "disponivel": true,
        "alocado_mb": 2847.3,        ← ★ deve ser > 0
        "cuda_visible_devices": "0"
    }
}
```

**★ A leitura do `alocado_mb`:**

| valor | significa |
|---|---|
| **> 0 e estável** entre chamadas | ✓ residente na GPU |
| **0** com `pronto: true` | os modelos foram para a **CPU** — veja `REFCAP_DEVICE` |
| `disponivel: false` | o torch não vê GPU — volte ao Passo 5 |

**Enquanto este processo viver, `nvidia-smi` deve mostrá-lo.** Confirme antes de ir para o supervisord.

---

## Passo 9 — ★ ATUALIZADO — Um job de ponta a ponta

Com o serviço do Passo 8 rodando. **Três formas de exercitar**, da mais simples à real:

**(a) Rota de teste, um vídeo — síncrona, resposta imediata:**
```bash
curl -s "localhost:8000/teste/construct?video=cena_01.mp4" | python -m json.tool
```

**(b) Rota de teste, um diretório inteiro:**
```bash
curl -s "localhost:8000/teste/construct-lote?diretorio=/dados/cenas&limite=3" | python -m json.tool
```
**[J] Use `limite` na primeira vez** — a rota é síncrona e um diretório grande estoura o timeout.

**(c) O caminho de produção — `POST /jobs`, nos formatos acordados:**

★ **A resposta traz o resultado completo** — não é mais preciso consultar depois.
```bash
# cena única
curl -s -X POST localhost:8000/jobs -H 'Content-Type: application/json' -d '{
  "scene_id":"cena_01","video_id":"vidA","program_id":"prog1",
  "scene_video_path":"/caminho/prog1/vidA/cena_01"
}'

# lote
curl -s -X POST localhost:8000/jobs -H 'Content-Type: application/json' -d '{
  "items":[
    {"scene_id":"cena_01","video_id":"vidA","program_id":"prog1","scene_video_path":"..."},
    {"scene_id":"cena_02","video_id":"vidB","program_id":"prog1","scene_video_path":"..."}
  ]
}'

```

**Se o lote for grande** e você preferir não segurar a conexão:
```bash
curl -s -X POST localhost:8000/jobs -H 'Content-Type: application/json' -d '{
  "items":[ ... ], "assincrono": true
}'
# devolve 202 + job_id; consulte depois:
curl -s localhost:8000/jobs/<job_id> | python -m json.tool
```

**O que esperar nas três:** o mesmo contrato de saída.
```json
{
  "job_id": "9e8adacb...",
  "estado": "concluido",
  "resumo": {"total": 3, "ok": 3, "erros": 0},
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

**[V] Verificado com `curl` real:** `HTTP 200`, `estado: concluido`, `{"total": 3, "ok": 3, "erros": 0}`.

**★ A prova do reaproveitamento** está no campo `modelos_reaproveitados` das rotas de teste:
```json
{"gpu_alocado_mb_antes": 2847.3, "gpu_alocado_mb_depois": 2847.3}
```
Valores **próximos e > 0** = o `build()` usou os modelos que já estavam na GPU.

**Se `status: "error"`:** a mensagem diz a causa. As comuns:

| erro | causa |
|---|---|
| `não encontrei a cena '...'` | `scene_video_path` errado — a rota tenta arquivo, arquivo sem extensão, e diretório |
| `o pipeline não produziu legenda` | vídeo < 1 s (zero frames) ou não entrou no annos |

**Confirme que o serviço sobreviveu:**
```bash
curl -s localhost:8000/health | python -m json.tool | grep alocado_mb
```
`alocado_mb` **inalterado** — os modelos continuam residentes mesmo após uma falha.

---

## Passo 10 — Migrar para o supervisord

Só depois que os passos 8 e 9 passarem à mão.

**Ajuste o `supervisord.conf`:**
```ini
command=/caminho/ABSOLUTO/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
directory=/caminho/para/src/api
user=seu_usuario

environment=
    CUDA_VISIBLE_DEVICES="0",
    REFCAP_ROOT="/caminho/para/src",
    REFCAP_CAPTION_MODEL="/caminho/local/blip-image-captioning-large",
    REFCAP_BLIP_ITM_MODEL="/caminho/local/blip-itm-base-coco",
    REFCAP_SENTENCE_TRANSFORMER="/caminho/local/paraphrase-distilroberta-v2",
    HF_HUB_OFFLINE="1",
    TRANSFORMERS_OFFLINE="1",
    REFCAP_CARREGAR_MODELOS="1"
```

**★ O caminho do uvicorn precisa ser ABSOLUTO.** **[V] Verifiquei:** o supervisord herda o ambiente de quem o iniciou — dentro do processo filho, `VIRTUAL_ENV` fica **ausente** e o `sys.executable` é o python do **sistema**. Um `command=uvicorn ...` pegaria o binário errado.

```bash
supervisorctl reread
supervisorctl update
supervisorctl status refcap-api
```

**Espere:** `RUNNING   pid 12345, uptime 0:01:23`

---

## Passo 11 — Confirmar que ficou permanente

```bash
supervisorctl status refcap-api    # anote o PID
sleep 60
supervisorctl status refcap-api    # o PID mudou?
```

| resultado | significa |
|---|---|
| **mesmo PID, uptime crescendo** | ✓ permanente |
| **PID diferente** | ✗ loop de reinício → Passo 12 |
| `BACKOFF` ou `FATAL` | ✗ morrendo → Passo 12 |

E a confirmação final:
```bash
curl -s localhost:8000/health | python -m json.tool | grep alocado_mb
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

O PID do `supervisorctl status` deve aparecer no `nvidia-smi`.

---

## Passo 12 — Quando algo falha no supervisord

```bash
cd <raiz-do-RefCap>/api
python diagnostico_supervisord.py --logs /var/log/refcap-api
```

**[V] Testei contra um loop reproduzido**, e ele detecta:
```
stderr.log  → PIDs encontrados: 4 distintos
              ⚠️ MÚLTIPLOS PIDs — assinatura de LOOP DE REINÍCIO
              ⚠️ 4 linhas com sinal de erro: CUDA out of memory
supervisord → spawned: 4   exited: 4
              ✗ o supervisord DESISTIU (FATAL)
```

**As causas mais comuns, na ordem:**

| erro no stderr | causa | correção |
|---|---|---|
| `CUDA out of memory` | outro processo ocupa a GPU | `nvidia-smi`; libere ou troque `CUDA_VISIBLE_DEVICES` |
| erro ao carregar modelo | caminho errado | volte ao Passo 4 |
| `ModuleNotFoundError` | venv errado | caminho **absoluto** do uvicorn |
| `Permission denied` | `user=` sem acesso | ajuste permissões da GPU / dos modelos |
| tentativa de rede | falta `HF_HUB_OFFLINE=1` | acrescente ao `environment=` |

E sempre:
```bash
supervisorctl tail -f refcap-api stderr
```

---

# PARTE 3 — Tabela de referência rápida

| passo | comando | espera |
|---|---|---|
| 1 | `git apply` os 2 patches | sem erro |
| 2 | `python construct.py --help` | lista de args |
| 3 | `pytest test/whole_propgen -v` | **48 passed** |
| 4 | `python validar_modelos_locais.py --caption ... --itm ... --st ...` | **3 de 3** |
| 5 | `python diagnostico_gpu.py` | `cuda.is_available() = True` |
| 6 | `python diagnostico_gpu.py --carregar --manter` | `delta alocado > 0` |
| 7 | `REFCAP_CARREGAR_MODELOS=0 python app.py` | `/health` 200 |
| 8 | `python app.py` (com modelos) | `alocado_mb > 0` |
| 9a | `curl ".../teste/construct?video=X.mp4"` | contrato + `alocado_mb` estável |
| 9b | `curl ".../teste/construct-lote?diretorio=D&limite=3"` | `{"items":[...]}` |
| 9c | `curl -X POST .../jobs` (formato acordado) | **HTTP 200 + resultado completo** |
| 9d | idem com `"assincrono": true` | 202 + `job_id` |
| 10 | `supervisorctl update` | `RUNNING` |
| 11 | comparar PID após 60 s | mesmo PID |
| 12 | `python diagnostico_supervisord.py` | (só se falhar) |

---

# PARTE 4 — ★ ATUALIZADO — O que este roteiro não cobre

**Resolvido desde a versão anterior:**
- ~~o `processar_job` com o bloco por preencher~~ → implementado
- ~~a decisão de isolamento~~ → `collection` = pedido > `program_id` > `job_id`
- ~~o formato da requisição~~ → cena única e lote, ambos aceitos

**[J] Ainda em aberto:**

- **Não testei com GPU real nesta sessão.** Validei a lógica dos diagnósticos e o serviço sem modelos. *(Você confirmou o carregamento residente no `nvidia-smi`.)*
- **Não processei um vídeo de verdade.** Os testes usaram um `build()` falso para verificar o **fluxo**: agrupamento por diretório, escrita do annos, detecção de cache, formato de saída.
- **Não cobre upload de arquivo** — o pedido traz **caminhos**, não os arquivos.
- **Os pesos das keywords (0.6/0.4) não foram calibrados** — sem dados anotados.
- **Sem limite de tamanho de lote** nem timeout por job. As rotas de teste são **síncronas**: use `limite` antes de rodar um diretório grande.

---

*Roteiro de doze passos, do patch ao serviço no ar. A ordem vai do mais barato ao mais caro: os passos 1–4 não envolvem GPU nem carregamento, então falhas de configuração aparecem em segundos. Os passos 5–9 validam à mão antes de envolver o supervisord — que é onde o diagnóstico fica mais difícil. A Parte 0 traz a auditoria de conflitos: onze verificações confirmando que os scripts novos são standalone e não interferem no serviço.*
