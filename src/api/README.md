# O Terreno Preparado — API FastAPI para o RefCap
## Relatório Detalhado: Arquitetura, Cada Arquivo Parte por Parte, e o Que Foi Testado

---

> **O que é este documento.** A explicação do esqueleto de serviço criado para o RefCap: como ele se encaixa no repositório sem modificá-lo, o que cada um dos cinco arquivos faz — parte por parte — e por que cada decisão foi tomada.
>
> **O que o esqueleto entrega hoje.** Supervisord sobe o FastAPI; o FastAPI carrega os três modelos **uma vez**; o serviço fica em estado permanente aceitando POSTs assíncronos com `job_id`, consulta por GET e webhook opcional.
>
> **O que falta.** Um bloco claramente marcado dentro de `processar_job`, onde entrará o seu pipeline (tratar a requisição, conferir/atualizar annos, decidir `collection`, chamar `build()`). **Nada do resto muda quando você preenchê-lo** — foi essa a razão de separar assim.

---

## Protocolo de verificação

| Marca | Significa |
|---|---|
| **[L]** | Lido no código do RefCap — arquivo e linha |
| **[V]** | Verificado por execução nesta sessão |
| **[J]** | Julgamento ou decisão de projeto |

---

# PARTE 1 — A arquitetura em uma página

## 1.1 O fluxo completo

```
supervisord
    │  (define CUDA_VISIBLE_DEVICES, REFCAP_ROOT, ... no environment=)
    ▼
uvicorn app:app  ──►  FastAPI
                        │
                        ├─ STARTUP (uma vez)
                        │     ponte_refcap.preparar_sys_path()   ← src/ no sys.path
                        │     ModelosResidentes.carregar()       ← os 3 modelos → GPU
                        │     ► a partir daqui: ESTADO PERMANENTE
                        │
                        ├─ POST /jobs
                        │     registro.criar()        → devolve job_id (202) na hora
                        │     BackgroundTasks         → executa depois de responder
                        │        └─ registro.executar()
                        │              async with trava:          ← UM job por vez
                        │                  asyncio.to_thread(processar_job)
                        │              └─ (fora da trava) webhook
                        │
                        ├─ GET /jobs/{id}   → estado + resultado
                        ├─ GET /jobs        → lista
                        ├─ GET /health      → modelos prontos? fila?
                        │
                        └─ SHUTDOWN
                              ModelosResidentes.liberar()
```

## 1.2 Os cinco arquivos e seus papéis

| arquivo | responsabilidade única |
|---|---|
| `ponte_refcap.py` | fazer o RefCap ser importável e seus caminhos resolverem certo |
| `carregador.py` | carregar os modelos uma vez e mantê-los residentes |
| `jobs.py` | fila serializada, estado dos jobs, entrega de webhook |
| `app.py` | ciclo de vida, rotas HTTP, e o ponto de extensão do seu pipeline |
| `supervisord.conf` | subir o processo com o ambiente correto |

**[J] A separação não é decorativa.** Cada arquivo resolve um problema distinto e pode ser testado isoladamente. O `jobs.py`, por exemplo, não sabe o que é o RefCap — recebe uma função e a executa. Foi isso que permitiu testar a fila com uma tarefa falsa (Parte 7).

## 1.3 A regra que governa tudo: não modificar o RefCap

Exceto por **um patch mínimo** no `construct.py` (Parte 6), nada do RefCap é alterado. O serviço:
- **importa** `pipeline/`, `dataset/`, `utils/`, `config/` — que **[L]** são limpos de efeito colateral de import;
- **não importa** `retrieve.py` — nada de retrieval nesta API;
- **monta** o `cfg` por conta própria em vez de deixar o RefCap ler `sys.argv`.

---

# PARTE 2 — `ponte_refcap.py` (118 linhas)

**Responsabilidade:** fazer o RefCap ser importável e seus caminhos resolverem para dentro dele.

Este é o arquivo que resolve as **duas armadilhas** que descobrimos na análise.

## 2.1 Armadilha 1 — como importar o RefCap

**[L] O RefCap usa imports absolutos de topo:**
```python
from pipeline.denoiser import *
import utils.basic_utils as basic_utils
```

**[V] Testei as duas formas possíveis**, com a estrutura `projeto/src/` + `projeto/api/`:

| forma | `sys.path` recebe | import escrito como | resultado |
|---|---|---|---|
| **A** | `.../src` | `from pipeline... import` | **✓ funciona** |
| **B** | `...` (o pai) | `from src.pipeline... import` | **✗ `ModuleNotFoundError: No module named 'utils'`** |

A Forma B é **estruturalmente impossível**: se você importa como `src.pipeline`, o `import utils.basic_utils` interno não resolve, porque ali `utils` seria `src.utils`.

**A implementação (linhas 39–62):**
```python
_AQUI = pathlib.Path(__file__).resolve().parent
RAIZ_REFCAP = pathlib.Path(os.environ.get("REFCAP_ROOT", _AQUI.parent / "src")).resolve()
_MARCADOR = pathlib.Path("pipeline") / "propgenerator" / "base.py"

def preparar_sys_path() -> None:
    _validar_raiz()
    caminho = str(RAIZ_REFCAP)
    if caminho not in sys.path:
        sys.path.insert(0, caminho)
```

**[J] Três decisões aqui:**

1. **Default por convenção, sobrescrita por ambiente.** Sem configurar nada, assume `<pai-do-api>/src`. Com `REFCAP_ROOT` definido (no supervisord, num container), respeita.
2. **Validação por marcador.** Confere que `pipeline/propgenerator/base.py` existe naquele caminho. Se não existir, levanta erro **explicativo** em vez de deixar o import falhar com uma mensagem obscura três camadas adiante.
3. **Idempotente.** Pode ser chamada várias vezes sem duplicar entradas no `sys.path`.

**[V] Verificado na réplica:** `RAIZ_REFCAP detectada: /tmp/proj/src`, marcador presente.

## 2.2 Armadilha 2 — os caminhos do `cfg` são relativos

**[L]** O `config/cfg.py` traz defaults relativos:
```
anno_dir  = "annos"      (L5)
meta_dir  = "meta"       (L9)
res_dir   = "results"    (L14)
```

**[V] Com o serviço rodando de `api/`, eles resolvem errado:**
```
cfg='meta'    -> projeto/api/meta      ✗   (deveria ser projeto/src/meta)
cfg='results' -> projeto/api/results   ✗
```

Os artefatos iriam para dentro de `api/`, e o cache de legendas, as features e as anotações ficariam órfãos.

**A implementação (linhas 70–113):**
```python
_CAMPOS_DE_CAMINHO = ("anno_dir", "meta_dir", "res_dir", "video_root")

def montar_cfg(**sobrescritas):
    preparar_sys_path()
    from config import BuildArguments          # só após o sys.path estar pronto
    cfg = BuildArguments()
    for campo in _CAMPOS_DE_CAMINHO:
        valor = getattr(cfg, campo, None)
        if isinstance(valor, str) and valor and not os.path.isabs(valor):
            setattr(cfg, campo, str(RAIZ_REFCAP / valor))
    for chave, valor in sobrescritas.items():
        if not hasattr(cfg, chave):
            raise AttributeError(...)
        setattr(cfg, chave, valor)
    return cfg
```

**[J] Quatro decisões:**

1. **Caminhos absolutos em vez de `os.chdir()`.** O `chdir` mudaria o diretório de trabalho do **processo inteiro** — afetando logs, uploads temporários e qualquer caminho relativo do seu próprio código. Preencher o `cfg` é explícito e sem efeito global.

2. **Só quatro campos precisam ser convertidos.** Os outros (`captions_dir`, `framefeatures_dir`, `raw_capframe_scores_dir`, `construct_dir`) também são relativos, **mas** o RefCap sempre os usa dentro de `os.path.join(meta_dir, X)` ou `os.path.join(res_dir, X)`. Como as bases viram absolutas, eles seguem junto. Está documentado no código para não parecer omissão.

3. **`BuildArguments()` direto, sem `sys.argv`.** **[L]** O `construct.py:29-30` faz `HfArgumentParser(...).parse_args_into_dataclasses()`, que lê a linha de comando — inviável num serviço.

4. **Sobrescrita validada.** Se você passar um campo que não existe em `BuildArguments`, levanta `AttributeError` com uma mensagem que diz o que fazer, em vez de criar um atributo fantasma que ninguém lê.

**[L] Uma armadilha documentada:** o `cfg.exp_dir` **não** é definido aqui. Ele é injetado pelo `build()` do RefCap a partir de `res_dir/construct_dir/collection/construct_name` (**[L]** `construct.py:35-36`). Defini-lo antes seria inútil — seria sobrescrito.

---

# PARTE 3 — `carregador.py` (188 linhas)

**Responsabilidade:** carregar os modelos uma vez e mantê-los vivos pelo resto do processo.

## 3.1 Por que este arquivo existe

**[L]** O RefCap tem um único ponto de carregamento — `utils/model_utils.py:8-45` — e ele é **tudo-ou-nada**: carrega quatro modelos, só o captioner sendo condicional.

**[L] E o GloVe é dead weight na construção.** Ele tem um único consumidor, `capTree.py:23`; o `CapTree` só é instanciado em `retrieve.py:269`; e o `constructpipe/base.py:3` importa `CapTree` mas **nunca o instancia** (verifiquei: zero ocorrências). Carregá-lo custa o parse de um arquivo de texto grande — para nada.

## 3.2 A classe `ModelosResidentes`

**O estado (linhas 60–69).** Cinco referências de modelo, o `device`, e uma lista de `InfoDeCarga` para diagnóstico.

**`carregar()` (linhas 80–133).** Carrega os três, espelhando as linhas do RefCap:

| modelo | espelha | atende as etapas |
|---|---|---|
| `cap_gen_model` + processor | **[L]** `model_utils.py:12-13` | 1 (legendagem) |
| `blip_itrtv_model` + processor | **[L]** `model_utils.py:30-31` | 2, 3, 4, 5, 6 |
| `sentence_transformer` | **[L]** `model_utils.py:35` | 6 (consenso) |

**[J] Os imports de `transformers` e `sentence_transformers` ficam dentro do método**, não no topo do arquivo. Dois motivos: o módulo pode ser importado para inspeção sem puxar o torch, e deixa explícito que o custo pesado acontece naquela chamada — não no import.

**`como_dict()` (linhas 141–160).** Devolve o dicionário com as **seis chaves exatas** que o RefCap espera:
```python
{
    "cap_gen_model": ..., "cap_gen_processor": ...,
    "blip_itrtv_model": ..., "blip_itrtv_processor": ...,
    "sentence_transformer": ...,
    "glove_model": None,          # ← ausente de propósito
}
```

**[J] Duas decisões:**
- **O `glove_model` vai como `None`, mas a chave existe.** Nenhum componente do construct o consulta, mas manter a chave evita `KeyError` se algum código futuro fizer `models.get("glove_model")`.
- **Falha cedo se não estiver pronto.** Chamar `como_dict()` sem ter carregado levanta `RuntimeError` com instrução clara, em vez de devolver um dict com `None`s que quebraria lá dentro do pipeline.

**`liberar()` (linhas 162–176).** Solta as referências e chama `torch.cuda.empty_cache()`. O `try/except` é deliberado: no shutdown, um erro ao limpar cache não deve impedir o encerramento.

**`diagnostico()` (linhas 178–188).** Alimenta o `/health` com quais modelos carregaram, de onde, e em quantos segundos.

---

# PARTE 4 — `jobs.py` (154 linhas)

**Responsabilidade:** executar um job por vez, guardar o estado, entregar webhook.

## 4.1 Por que fila serializada

**[J]** Cada worker adicional carrega **seu próprio** conjunto de modelos na GPU — dois workers com BLIP-large são dois BLIP-large residentes. E inferência simultânea no mesmo modelo não traz ganho real, porque a GPU já serializa internamente.

**A decisão:** um processo, um conjunto de modelos, requisições uma de cada vez. Se um dia precisar de throughput, o caminho é **batch** (juntar frames de várias requisições numa chamada ao BLIP), não mais processos.

## 4.2 As peças

**`EstadoJob` (linha 36).** Enum com quatro estados: `na_fila`, `executando`, `concluido`, `falhou`. Herda de `str` para serializar em JSON sem conversão.

**`Job` (linhas 47–75).** Dataclass com id, estado, três marcos de tempo, resultado, erro, dados do callback e a entrada original. O `como_dict(incluir_resultado=False)` permite listar jobs sem arrastar resultados grandes.

**`RegistroDeJobs` (linhas 77–154).** O núcleo:

```python
def __init__(self) -> None:
    self._jobs: dict[str, Job] = {}
    self._trava = asyncio.Lock()      # ← serializa a execução
```

**`executar()` — o coração (linhas 108–133):**
```python
async with self._trava:                              # UM job por vez
    job.estado = EstadoJob.EXECUTANDO
    try:
        job.resultado = await asyncio.to_thread(tarefa, job)
        job.estado = EstadoJob.CONCLUIDO
    except Exception as exc:
        job.estado = EstadoJob.FALHOU
        job.erro = f"{type(exc).__name__}: {exc}"
        job.resultado = {"traceback": traceback.format_exc()}
    finally:
        job.terminado_em = _agora()

if job.callback_url:                                 # FORA da trava
    await self._entregar_callback(job)
```

**[J] Quatro decisões concentradas nessas linhas:**

1. **`asyncio.to_thread`.** A tarefa é **síncrona e pesada** (ffmpeg + inferência). Rodá-la direto travaria o loop de eventos e o serviço pararia de responder. Numa thread, o `/health` e o `GET /jobs` continuam funcionando durante o processamento.

2. **`except Exception` genérico — aqui é o lugar certo.** Nossos tratados condenam capturar tudo, mas este é justamente o caso legítimo: uma falha num job **não pode derrubar o serviço**. A exceção é registrada no job (tipo, mensagem e traceback completo) e o processo segue.

3. **O `traceback` vai para o resultado.** Sem isso, o cliente recebe "falhou" e você fica sem saber onde. Com ele, o `GET /jobs/{id}` te dá o diagnóstico.

4. **O callback fica FORA da trava.** Se ficasse dentro, um cliente com endpoint lento seguraria a fila inteira. Fora, a próxima requisição já começa enquanto a entrega acontece.

**`_entregar_callback()` (linhas 135–154).** POST no `callback_url` com timeout de 10 s. **[J] Falha de entrega não derruba o job** — registra `callback_entregue=False` e loga com a instrução de consultar via GET. O `import httpx` é tardio: só acontece quando há callback de fato.

**[J] Limite declarado no próprio código:** o armazenamento é **em memória**. Reiniciar o processo perde o histórico. Para persistir, troca-se `self._jobs` por SQLite/Redis — a interface pública não muda.

---

# PARTE 5 — `app.py` (231 linhas)

**Responsabilidade:** ciclo de vida, rotas, e o ponto onde o seu pipeline entra.

## 5.1 `ConfigServico` (linhas 54–60)

Tudo por variável de ambiente, com defaults:
```python
device = os.environ.get("REFCAP_DEVICE", "cuda")
caption_model = os.environ.get("REFCAP_CAPTION_MODEL", "Salesforce/blip-image-captioning-large")
...
carregar_no_startup = os.environ.get("REFCAP_CARREGAR_MODELOS", "1") == "1"
```

**[J] O `REFCAP_CARREGAR_MODELOS=0` é o interruptor de desenvolvimento:** sobe o serviço **sem** GPU e sem modelos, para testar rotas numa máquina qualquer. Foi com ele que rodei todos os testes da Parte 7.

## 5.2 O ciclo de vida (linhas 69–100)

```python
@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    preparar_sys_path()
    if ConfigServico.carregar_no_startup:
        modelos.carregar(...)          # ★ AQUI, uma única vez
    yield                              # ← o serviço vive aqui
    modelos.liberar()
```

**[J] É este bloco que realiza o "estado permanente" que você pediu.** O `lifespan` do FastAPI executa o que vem antes do `yield` no startup e o que vem depois no shutdown. Os objetos `modelos` e `registro` são de módulo — vivem enquanto o processo viver.

**Por que não uma variável global carregada no import:** o `lifespan` dá controle sobre **quando** carregar, permite falhar de forma diagnosticável, e garante a liberação no shutdown.

## 5.3 Os contratos (linhas 108–132)

`PedidoDeJob` com três campos — `videos`, `callback_url`, `parametros`. **[J] Está marcado no docstring como PROVISÓRIO**, porque você ainda vai definir o formato real. Acrescentar campos aqui não afeta nenhum outro arquivo.

## 5.4 ★ `processar_job` — o ponto de extensão (linhas 138–186)

```python
def processar_job(job: Job) -> dict:
    pedido = job.entrada

    # ################################################################### #
    # ### AQUI ENTRA O SEU PIPELINE                                     ###
    # ### 1. Tratar o que veio na requisição                            ###
    # ### 2. Conferir / atualizar as listas de annos                    ###
    # ###    (anno_path = annos/{collection}/{anno_file})               ###
    # ### 3. Decidir collection / construct_name                        ###
    # ################################################################### #

    cfg = montar_cfg(..., construct_name=job.id, **pedido.get("parametros", {}))

    from construct import build
    tree_meta = build(cfg, modelos.como_dict())      # ← modelos JÁ carregados

    return {"construct_name": ..., "exp_dir": ..., "tree_meta": tree_meta}
```

**[J] Por que o bloco marcado está exatamente aí:** os três passos que faltam são **os únicos** que dependem do formato da requisição. Tudo antes (carregamento, fila) e tudo depois (chamada ao `build`, resposta) já está resolvido. Quando você definir o contrato, preenche o bloco e nada mais muda.

**[L] O `from construct import build` é tardio** — depois que `preparar_sys_path()` já rodou no startup. No topo do arquivo, falharia.

## 5.5 As rotas (linhas 191–231)

| rota | o que faz | decisão |
|---|---|---|
| `GET /health` | estado dos modelos + fila | permite ao supervisord e a você saberem se está pronto |
| `POST /jobs` | cria job, devolve **202** + `job_id` | 202 = "aceito, processando"; devolve na hora, não espera |
| `GET /jobs/{id}` | estado + resultado | 404 se não existir |
| `GET /jobs` | lista recentes | sem os resultados, para não pesar |

**[J] O `POST` recusa com 503 se os modelos não estiverem prontos** — melhor que aceitar um job que vai falhar.

**[J] `BackgroundTasks` em vez de `asyncio.create_task`:** o FastAPI garante que a tarefa só começa **depois** que a resposta foi enviada. O cliente recebe o `job_id` imediatamente.

---

# PARTE 6 — O patch no `construct.py`

**A única modificação no RefCap.** Duas mudanças, ambas com o CLI preservado.

## 6.1 `os.environ.setdefault` (linhas 2–3)

```python
# antes
os.environ["CUDA_VISIBLE_DEVICES"]='0'
# depois
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
```

**[V] Verificado nos dois cenários:**
- sem nada definido (o CLI de hoje) → `'0'` — **idêntico ao anterior**
- supervisord define `1` → `'1'` — **respeitado** (antes seria sobrescrito para `0`)

**[J] Sem isso, o `environment=` do supervisord seria inútil**: bastaria o serviço importar o `construct.py` para a GPU 0 ser forçada.

## 6.2 Extração de `build(cfg, pretrained_models=None)`

```python
def build(cfg, pretrained_models=None):
    seed_it(cfg.seed)
    cfg.exp_dir = os.path.join(cfg.res_dir, cfg.construct_dir, cfg.collection, cfg.construct_name)
    os.makedirs(cfg.exp_dir, exist_ok=True)
    basic_utils.save_json(asdict(cfg), ...)
    if pretrained_models is None:                   # ← o CLI cai aqui
        pretrained_models = load_pretrained_models(cfg)
    ...
    return construct_pipeline.construct()           # ← agora RETORNA

def main():
    cfg = parser.parse_args_into_dataclasses(...)[0]
    build(cfg)                                      # ← delega
```

**[J] É um *Extract Function* puro.** **[V] Verifiquei que as dez operações essenciais estão preservadas e na mesma ordem.** O CLI (`bash scripts/construct.sh`) funciona idêntico; o serviço chama `build(cfg, meus_modelos)` e pula o carregamento.

**Ganho lateral:** o `build()` agora **retorna** o `tree_meta`, que antes era descartado. É esse retorno que vira a resposta da API.

---

# PARTE 7 — O que foi testado, e como

**[V] Todos os testes rodaram com o FastAPI de verdade**, usando `TestClient` e `REFCAP_CARREGAR_MODELOS=0` (sem GPU).

| # | verificação | como foi feito | resultado |
|---|---|---|---|
| 1 | serviço sobe e acha o RefCap | réplica `proj/src` + `proj/api` | `refcap_root: /tmp/proj/src` ✓ |
| 2 | `GET /health` | requisição real | 200, JSON com estado dos modelos ✓ |
| 3 | `POST /jobs` | requisição real | 202 + `job_id` imediato ✓ |
| 4 | ciclo do job | polling até terminar | `na_fila → executando → concluido` ✓ |
| 5 | job inexistente | `GET /jobs/naoexiste` | 404 ✓ |
| 6 | **fila serializa** | 5 POSTs simultâneos, contador de concorrência | **máximo 1 executando** ✓ |
| 7 | **erro isolado** | tarefa que levanta `ValueError` | estado `falhou` + traceback; `/health` 200; aceita novo job ✓ |
| 8 | **webhook entregue** | servidor receptor real na porta 8899 | `callback_entregue=True`, payload correto ✓ |
| 9 | **webhook inalcançável** | URL morta | job **concluiu**, `entregue=False` ✓ |

**[J] Os testes 6, 7 e 9 são os que mais importam**, porque verificam as garantias de robustez: que a GPU não é usada por dois jobs ao mesmo tempo, que uma falha não derruba o serviço, e que um cliente com webhook quebrado não perde o resultado.

---

# PARTE 8 — O que este esqueleto **não** faz

**[J]** Registro explícito, para não haver expectativa errada:

- **Não processou um vídeo real.** Não há GPU nem modelos neste ambiente; a tarefa foi substituída por uma função falsa nos testes.
- **Não persiste jobs.** Reiniciar o processo perde o histórico (declarado no `jobs.py`).
- **Não recebe upload de arquivo.** O `PedidoDeJob` recebe **nomes** de vídeo. Se a requisição for trazer o arquivo, será preciso `UploadFile` e gravação em `video_root`.
- **Não valida a duração dos vídeos.** O patch do `viddataset` (`max(1, int(duration))`) protege contra o crash, mas não há validação na entrada.
- **Não limita o tamanho da fila** nem tem timeout por job.
- **Não resolve a decisão de isolamento** (`collection` por job) — deliberadamente adiada, e ela vive dentro do bloco marcado.
- **Os nomes de modelo têm o prefixo `Salesforce/`**, que difere dos defaults do `cfg.py` do RefCap. Não verifiquei se resolvem no HuggingFace Hub — ajuste conforme o seu ambiente.

---

# PARTE 9 — Como colocar de pé

```
1. Aplicar o patch:      git apply construct_reutilizavel.patch
2. Copiar api/ para:     <projeto>/api/       (irmão de src/)
3. Ajustar supervisord.conf:
     - caminhos do uvicorn e do directory
     - REFCAP_ROOT
     - nomes dos modelos
     - user
4. Testar sem GPU:       REFCAP_CARREGAR_MODELOS=0 uvicorn app:app
     GET /health deve responder 200 com "pronto": false
5. Testar com modelos:   uvicorn app:app
     GET /health deve responder "pronto": true e listar os 3 modelos
6. Subir no supervisord: supervisorctl reread && supervisorctl update
```

**[J] O passo 4 é o que economiza tempo**: valida a estrutura de diretórios, o `sys.path` e as rotas antes de envolver GPU.

---

*Relatório do esqueleto de API para o RefCap. Cinco arquivos, cada um com uma responsabilidade única, mais um patch mínimo no `construct.py` que preserva o CLI. As duas armadilhas estruturais — o `sys.path` e os caminhos relativos do `cfg` — foram identificadas por teste e resolvidas no `ponte_refcap.py`. Nove verificações foram executadas com o FastAPI real, incluindo as três garantias de robustez (serialização da fila, isolamento de erro, resiliência a webhook quebrado). O ponto de extensão para o seu pipeline está isolado numa única função, de modo que preenchê-lo não exija mudar mais nada.*
