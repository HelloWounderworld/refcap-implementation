# Diagnóstico de Infraestrutura
## Quando o Serviço Não Sobe, ou os Modelos Não Ficam na GPU

---

> **Use este documento quando** o `/health` não responde, o `models.ready` é `false`, o `allocated_mb` é 0, ou o supervisord reinicia o serviço em loop.
>
> **Quatro scripts, cada um para um problema:**
>
> | script | quando |
> |---|---|
> | `validar_modelos_locais.py` | antes de subir, ou se o carregamento falhar |
> | `diagnostico_gpu.py` | `allocated_mb` = 0, ou a GPU não aparece |
> | `diagnostico_supervisord.py` | o serviço reinicia sozinho |
> | `migrar_cache.py` | mudou o `collection` e o cache "sumiu" |

---

# A ordem quando algo falha

**[J] Do mais barato ao mais caro.** Os dois primeiros não envolvem GPU nem carregamento — se o problema estiver ali, você descobre em segundos.

```
1. validar_modelos_locais.py     os caminhos estão certos?
2. diagnostico_gpu.py            o torch vê a GPU?
3. diagnostico_gpu.py --carregar --manter    carregar ocupa memória?
4. curl /health                  o serviço reporta o quê?
5. diagnostico_supervisord.py    (só se o serviço reiniciar sozinho)
```

---

# 1. `validar_modelos_locais.py`

**O problema que ele evita:** um caminho de modelo errado faz o `from_pretrained()` tentar baixar do Hub. Sem rede, falha — e no supervisord isso vira loop de reinício difícil de diagnosticar.

```bash
# ver o que existe
python validar_modelos_locais.py /caminho/dos/modelos

# validar os três
python validar_modelos_locais.py \
    --caption /caminho/local/blip-image-captioning-large \
    --itm     /caminho/local/blip-itm-base-coco \
    --st      /caminho/local/paraphrase-distilroberta-v2
```

**Espera:** `3 de 3 modelo(s) prontos para uso local`.

## ★ A armadilha do "movi do cache"

Existem **duas** estruturas possíveis, e só uma funciona:

```
✓ LAYOUT PLANO                    ✗ LAYOUT DE CACHE
  /modelos/blip-caption/            /modelos/models--Salesforce--blip.../
  ├── config.json                   ├── blobs/
  ├── model.safetensors             ├── refs/
  ├── preprocessor_config.json      └── snapshots/
  └── tokenizer_config.json             └── a1b2c3.../   ← os arquivos estão AQUI
```

Se você copiou a pasta `models--Org--nome/` inteira, o `from_pretrained()` **não aceita** aquele diretório. O script detecta e **te diz o caminho correto**:

```
⚠️ LAYOUT DE CACHE detectado
   USE ESTE CAMINHO:
       /modelos/models--Salesforce--blip.../snapshots/a1b2c3d4
```

## Os três diagnósticos

| saída | causa | correção |
|---|---|---|
| `⚠️ LAYOUT DE CACHE detectado` | copiou a estrutura do cache | use o caminho indicado |
| `✗ FALTAM: ...` | cópia incompleta | copie os arquivos que faltam |
| `⚠️ parece um REPO-ID do Hub` | não é caminho local | aponte para o diretório |

## ★ O modo offline

Acrescente ao `supervisord.conf`:
```ini
HF_HUB_OFFLINE="1",
TRANSFORMERS_OFFLINE="1",
```

**Por quê:** sem elas, um caminho errado faz o `from_pretrained()` **tentar a rede**. Num servidor sem saída, isso vira espera longa seguida de erro obscuro. Com elas, caminho errado dá erro **imediato e explícito**.

---

# 2. `diagnostico_gpu.py`

```bash
python diagnostico_gpu.py                    # só checa o ambiente
python diagnostico_gpu.py --carregar         # carrega e mede
python diagnostico_gpu.py --carregar --manter  # ★ fica vivo para o nvidia-smi
```

## Bloco A — o torch vê a GPU?

Se `torch.cuda.is_available()` for `False`, o script lista as causas:
- o torch instalado é o build **CPU-only**
- `CUDA_VISIBLE_DEVICES=""` (string vazia esconde **todas** as GPUs)
- driver NVIDIA ausente ou incompatível

**Resolva isto antes de seguir.**

## Bloco B — as variáveis de ambiente

Ele avisa sobre os três casos que mais confundem:

| variável | aviso |
|---|---|
| `CUDA_VISIBLE_DEVICES=""` | **esconde todas as GPUs** |
| `CUDA_VISIBLE_DEVICES=1` | o "device 0" do processo é a GPU **física 1** — confira essa linha no `nvidia-smi` |
| `REFCAP_DEVICE=cpu` | os modelos vão para a CPU |
| `REFCAP_CARREGAR_MODELOS=0` | o serviço sobe **sem** modelos |

## ★ O modo `--manter`

```bash
python diagnostico_gpu.py --carregar --manter --modelo /caminho/local/blip-caption
```

Ele carrega, mede antes/depois, imprime o **PID** e **fica vivo**, reportando a memória a cada 5 s.

Em outro terminal:
```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

**Você deve ver aquele PID.** Ctrl+C encerra e a memória é liberada — é esse o comportamento de "residente".

**[J] Este é o passo que separa "o carregamento funciona" de "o serviço mantém".** Se ele passa, o problema (se houver) está no supervisord, não no modelo.

---

# 3. `diagnostico_supervisord.py`

**O sintoma:** o `nvidia-smi` mostra memória que aparece e some, ou o serviço "carrega mas não fica permanente".

```bash
supervisorctl status refcap-api
```

| resultado | significa |
|---|---|
| `RUNNING pid 1234, uptime 0:15:32` | ✓ vivo; se o uptime **cresce**, está estável |
| `RUNNING pid 5678, uptime 0:00:03` | ⚠️ acabou de subir — consulte de novo em 30 s: se o **PID mudar**, é loop |
| `BACKOFF Exited too quickly` | ✗ morrendo logo após subir |
| `FATAL too many start retries` | ✗ desistiu |

```bash
python diagnostico_supervisord.py --logs /var/log/refcap-api
```

## ★ A assinatura do loop de reinício

```
stderr.log  → PIDs encontrados: 4 distintos
              ⚠️ MÚLTIPLOS PIDs — assinatura de LOOP DE REINÍCIO
              ⚠️ 4 linhas com sinal de erro: CUDA out of memory
supervisord → spawned: 4   exited: 4
              ✗ o supervisord DESISTIU (FATAL)
```

**O mesmo carregamento repetido, com PIDs diferentes.** É isso que faz parecer que "carregou mas não ficou".

## As causas mais comuns

| erro no stderr | causa | correção |
|---|---|---|
| `CUDA out of memory` | outro processo ocupa a GPU | `nvidia-smi`; libere ou troque `CUDA_VISIBLE_DEVICES` |
| erro ao carregar modelo | caminho errado | volte ao script 1 |
| `ModuleNotFoundError` | venv errado | **caminho absoluto** do uvicorn no `command=` |
| `Permission denied` | `user=` sem acesso | ajuste permissões da GPU / dos modelos |
| tentativa de rede | falta `HF_HUB_OFFLINE=1` | acrescente ao `environment=` |

## ★ Três armadilhas do supervisord, verificadas

**1. O venv não é herdado.** Dentro do processo filho, `VIRTUAL_ENV` fica **ausente** e o `sys.executable` é o python do **sistema**. O supervisord herda o ambiente de quem o iniciou — normalmente o init, não o seu shell.

**Por isso o `command=` precisa do caminho absoluto:**
```ini
command=/caminho/ABSOLUTO/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```

**2. O `startsecs` não é limite de carga.** Processo vivo carregando modelos **conta como rodando**. O que ele controla: se o processo **morrer** antes de `startsecs`, conta como falha de start e retenta.

**3. Nunca use `--reload`.** Ele recria o processo a cada mudança de arquivo — recarregando os modelos junto, o que anula o estado permanente.

---

# 4. `migrar_cache.py`

**Quando usar:** você mudou o `collection` (a Etapa 2 passou a usar o `program_id`) e o cache antigo ficou órfão.

```bash
# ver o que existe
python migrar_cache.py --listar

# SEMPRE simule primeiro
python migrar_cache.py --de teste_api --para meu_programa --simular

# só então migre
python migrar_cache.py --de teste_api --para meu_programa
```

**Move quatro artefatos:**
```
annos/{de}/                     →  annos/{para}/
meta/captions/{de}_blip.jsonl   →  meta/captions/{para}_blip.jsonl
meta/framefeatures/{de}.pt      →  meta/framefeatures/{para}.pt
meta/scores/{de}_blip.pt        →  meta/scores/{para}_blip.pt
```

**O `--simular` mostra os quatro com a contagem de cenas**, sem tocar em nada.

**Se o destino já tiver artefatos, ele RECUSA** — fundir dois caches é decisão sua, não do script. Uma fusão errada misturaria cenas de programas diferentes.

## ★ O teste que prova a migração

```bash
curl -X POST $API/caption -H 'Content-Type: application/json' -d '{
  "scene_id": "<uma_ja_processada>", "program_id": "<program_id>",
  "scene_video_path": "..."}'
```

**Ela deve ser PULADA** — rápida, sem rodar o BLIP. Se for reprocessada, o cache não foi encontrado no caminho novo.

**Nota:** o `results/construct/{de}/` **não** é migrado de propósito. Ele é área de trabalho da última execução; o que importa preservar é o **cache**, que evita rodar o BLIP de novo.

---

# 5. Árvore de decisão

```
O /health responde?
├── NÃO → o serviço não está no ar
│         supervisorctl status refcap-api
│         └── BACKOFF/FATAL? → diagnostico_supervisord.py
│
└── SIM → models.ready é true?
    ├── NÃO → subiu com REFCAP_CARREGAR_MODELOS=0? remova a variável
    │         ou o carregamento falhou → veja o stderr
    │
    └── SIM → models.gpu.allocated_mb > 0?
        ├── NÃO → os modelos estão na CPU
        │         confira REFCAP_DEVICE e diagnostico_gpu.py
        │
        └── SIM → ele CRESCE entre requisições?
            ├── SIM → algo recarrega modelo a cada chamada
            │         confira que o build recebe o dicionário
            │
            └── NÃO → ✓ está tudo certo
                      o nvidia-smi mostra o PID do serviço?
                      ├── NÃO → CUDA_VISIBLE_DEVICES remapeia os índices;
                      │         você pode estar olhando a GPU física errada
                      └── SIM → ✓ residente e confirmado
```

---

# 6. Verificações rápidas de uma linha

```bash
# os modelos estão na GPU?
curl -s $API/health | python3 -c "import sys,json;print(json.load(sys.stdin)['models']['gpu'])"

# quantos jobs na fila?
curl -s $API/health | python3 -c "import sys,json;print(json.load(sys.stdin)['queued_jobs'])"

# o PID do serviço aparece no nvidia-smi?
supervisorctl status refcap-api
nvidia-smi --query-compute-apps=pid,used_memory --format=csv

# o allocated_mb muda entre duas chamadas?
for i in 1 2; do curl -s $API/health | python3 -c "import sys,json;print(json.load(sys.stdin)['models']['gpu'].get('allocated_mb'))"; sleep 2; done

# os patches do RefCap estão aplicados?
grep -c "def build" construct.py                   # 1
grep -c "setdefault" construct.py                  # 2
grep -c "n_amostras" dataset/viddataset.py         # 1
grep -c '"whole"' config/cfg.py                    # >= 1
grep -c "spacy_nlp" pipeline/propgenerator/WholePropGener.py   # >= 1
```

---

# 7. Os limites deste documento

**[J]**

- Os quatro scripts foram **testados quanto à lógica** — inclusive reproduzindo um loop de reinício real com supervisord — mas **não** contra uma GPU de verdade neste ambiente.
- A árvore de decisão cobre os casos que encontramos; um sintoma fora dela pede investigação direta no `stderr`.
- O `migrar_cache.py` foi testado com artefatos simulados, não com um cache real de centenas de cenas.

---

*Diagnóstico de infraestrutura. Para os testes funcionais da API, veja `README_TESTES.md` e `TESTES_CURL.md`.*
