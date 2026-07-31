# RefCap — Infraestrutura de Testes e Exploração: Setup, Isolamento e Automação
## Como verificar cada afirmação da análise — do scratch flexível à suíte automatizada

---

> **O que é este documento.** O playbook para montar um ambiente que permite **confirmar cada afirmação da sua análise** do RefCap em dois regimes complementares: (a) o **scratch flexível** — cutucar um trecho e ver se a lógica anda, na hora, sem cerimônia; e (b) o **aparato formal** (pytest) — travar a lógica confirmada em regressão automatizada. Cobre: os dois eixos de organização, o ambiente (compartilhado), os pacotes, a estrutura de diretórios, os arquivos de configuração (prontos para copiar), o substrato de exploração, a estratégia de fixtures/mocks, o mapeamento afirmação→teste, a orquestração da automação, e as armadilhas fatais.
>
> **Postura.** Não é "instale pytest e teste o pipeline" — isso é a armadilha nº 1. E também não é "explore no REPL e esqueça a estrutura" — isso perde a regressão. O valor está em reconhecer que **exploração e formalização são dois pontos de um mesmo espectro que compartilham um substrato** — e configurar o ambiente para deslizar entre eles sem duplicar esforço.
>
> **Atualização desta versão.** Incorpora as descobertas empíricas da montagem do primeiro scratchpad (`scratch/scratch_construct.py`, executado com sucesso): a cascata real da cadeia de import, a falha de carregamento do `torchtext`, e a técnica de *shim* que a contorna.

---

## 0. Reformulação: dois eixos, não um

A pergunta original ("quais pacotes/diretórios/configurações instalar") tem duas dimensões ortogonais que precisam ser separadas — confundi-las é a origem da maioria dos erros de setup:

- **Eixo do PESO** (quanto o teste custa): T0 (lógica pura, sem modelos) → T1 (integração com mocks) → T2 (ponta a ponta, modelos reais). Já detalhado.
- **Eixo da FORMALIDADE** (quão cerimonioso o teste é): **scratch** (explorar, descartável, "isso anda?") → **pytest** (travar, automatizável, "isto continua andando?").

Estes eixos são **independentes**: você pode explorar lógica pura (scratch + T0), explorar integração (scratch + T1), ou automatizar qualquer camada (pytest + T0/T1/T2). A pergunta de maior impacto é: **"como configuro um ambiente que me deixa cutucar um trecho agora, sem carregar modelos, e depois promover o que confirmei a um teste formal sem reescrever nada?"**

O princípio central deriva de dois fatos do repositório (verificados no código e **confirmados em execução**):

1. **O RefCap tem perfil de dependências pesado** (torch, transformers, sentence-transformers, spaCy, torchtext) e depende de pesos volumosos (BLIP, MiniGPT, GloVe 300d ~1GB) e de GPU para operação realista. Testar "a coisa real" a cada asserção é inviável.
2. **A maioria das suas afirmações é sobre *lógica pura* ou *fluxo*** — o kernel de Foote é checkerboard ±1; a normalização min-max descarta magnitude absoluta; o denoiser propaga só para frente; `construct()` recomputa scores sobre legendas denoised. **Nenhuma requer um modelo carregado** — requer *entradas sintéticas* (ou *dublês*, para orquestradores) e a *lógica* do módulo.

**A distinção que organiza tudo — biblioteca instalada ≠ peso carregado.** *Confirmado em execução:* importar `pipeline/constructpipe/base.py` cascateia por `tqdm → torch → capTree → sentence_transformers → torchtext` — a cadeia inteira precisa **resolver** só para o `import` acontecer. Mas nenhum desses *pesos* é carregado se você mockar/dublar em runtime. Logo: você precisa das **bibliotecas** instaladas para **importar**, mas pode **evitar carregar os pesos** ao testar (via bypass de `__init__`, monkeypatch, dublês, ou shim de dependência frágil). Esta é a chave técnica de todo o setup — e vale igualmente para scratch e pytest.

---

## 1. As duas dimensões de organização

### 1.1 Eixo do peso — as três camadas

A tiragem é imposta por **se o teste carrega pesos de modelo**, não por qual biblioteca está instalada (todas estão, para satisfazer imports).

| Camada | O que testa | Carrega pesos? | GPU? | Velocidade | Quando roda |
|---|---|:---:|:---:|---|---|
| **T0 — Lógica pura** | Algoritmos/fluxo com entradas sintéticas ou dublês | **Não** | Não | ms | A cada save/commit |
| **T1 — Integração com mocks** | Fluxo entre componentes, pesos *falsos* determinísticos | Não (mocked) | Não | s | Antes de push / PR |
| **T2 — Ponta a ponta real** | Pipeline completo, micro-corpus, modelos reais | **Sim** | Sim | min | Manual / noturno |

### 1.2 Eixo da formalidade — scratch vs pytest

| Regime | Ferramenta | Para quê | Persistência | Quando |
|---|---|---|---|---|
| **Scratch** | `python scratch/x.py` / `ipython -i` / células `# %%` | "essa lógica anda?" — cutucar, visualizar, dissecar | Descartável | Durante a análise/investigação |
| **Aparato** | `pytest` | "isto continua andando?" — travar, regressão, automação | Máxima | Depois de confirmar; para a esteira |

**A ponte (o que evita duplicação):** os dois compartilham o mesmo *substrato* — os helpers de bypass de `__init__`, os geradores sintéticos, os dublês. Você explora *frouxamente* com eles no scratch e, quando a lógica se confirma, **promove** o snippet a teste formal movendo a asserção para `tests/` — os helpers vêm de graça. Promoção é *recorte*, não reescrita.

---

## 2. Ambiente (compartilhado por scratch e pytest)

### 2.1 Estratégia de ambiente

**Um único ambiente, isolado do restante, serve aos dois regimes.** Como as cadeias de import puxam tudo, o ambiente precisa conter as bibliotecas do `requirements.txt` (para importar os módulos) **mais** o ferramental de teste e de exploração. A tiragem T0/T1/T2 é imposta pelos *testes* (mock/bypass/dublê), não por sub-ambientes; o scratch usa exatamente o mesmo ambiente.

```bash
# Reproduza o ambiente do repo (conda, como o repo especifica), NUNCA no env de produção
conda create -n refcap-test python=3.10 -y
conda activate refcap-test

# Bibliotecas do repo (necessárias para IMPORTAR os módulos-alvo)
pip install -r requirements.txt
python -m spacy download en_core_web_sm     # ~12MB, determinístico → OK para T0

# Ferramental de teste + exploração (ver §3)
pip install -r requirements-test.txt

# Binário de sistema — SÓ para T2 (testes de vídeo real)
# Ubuntu: sudo apt-get install ffmpeg   |   macOS: brew install ffmpeg
```

### 2.2 Reprodutibilidade (obrigatória para determinismo)

- **Fixe versões** — o `requirements.txt` já pina; mantenha assim. Deriva de versão de modelo/lib quebra golden files silenciosamente.
- **Semeie tudo** — no `conftest.py` (pytest) e no `_bootstrap.py` (scratch): `torch.manual_seed`, `numpy.random.seed`, `random.seed`, e `PYTHONHASHSEED=0` (afeta ordenação de sets/dicts — relevante para o *Indexing Keyword Set*, que é um `set`).
- **Force CPU no T0/T1** (`cfg.device='cpu'`) para eliminar não-determinismo de GPU.

### 2.3 Riscos de instalação (avisos concretos — um deles confirmado ao vivo)

- **`torchtext==0.17.0`** (usado por `capTree` para GloVe) está descontinuado e é frágil de casar com o torch. **Confirmado em execução:** ele até *instala*, mas **falha ao carregar** com torch recente (`OSError: Could not load .../libtorchtext.so`). Como `construct()` e a maioria da lógica **não usam GloVe**, a solução é o *shim* de import (§5.6 e §6.3): um stub mínimo em `sys.modules` que desbloqueia a cadeia sem instalar a dependência frágil. No seu ambiente `refcap-test` com as versões pinadas o carregamento pode funcionar; o shim é uma blindagem inócua nesse caso.
- **Rede**: `pip` puxa de `pypi.org`/`files.pythonhosted.org`; downloads de modelo (spaCy, HuggingFace) vêm de outras origens. Em ambiente restrito, pré-baixe os pesos para T2. (Nota: o índice oficial do PyTorch — `download.pytorch.org` — pode não estar acessível em ambientes com allowlist; o PyPI serve o torch como alternativa.)

### 2.4 Ferramental interativo para o scratch

O scratch prospera com inspeção *visual* — a lógica do RefCap é matriz/tensor, e você quer **ver** (plotar a matriz de similaridade, a curva de novidade de Foote), não só afirmar. Dois modos de trabalho, ambos suportados pelo mesmo ambiente:

- **Arquivo `.py` + `ipython -i`** (o que usamos): `ipython -i scratch/x.py` roda o arquivo e te deixa no REPL com todas as variáveis vivas para cutucar (`journal`, tensores, etc.). Requer `ipython`.
- **Células interativas (`# %%`)**: no VSCode/PyCharm, marcadores `# %%` transformam um `.py` num notebook interativo — você ganha execução por célula e plots inline, mantendo um arquivo `.py` limpo e versionável (sem o estado oculto e a bagunça de ordem de um `.ipynb`). Requer a extensão do editor + `ipykernel`.

Para visualização: `matplotlib`. Ambos entram no `requirements-test.txt` (§3).

---

## 3. Pacotes (com justificativa — nada de lista genérica)

`requirements-test.txt` (pronto para copiar):

```
# --- Aparato formal (pytest) ---
pytest==8.*              # runner central
pytest-cov==5.*          # cobertura — saber o que está EXERCITADO (≠ verificado; ver §10)
pytest-mock==3.*         # wrapper ergonômico sobre unittest.mock (fixture `mocker`)
hypothesis==6.*          # testes baseados em propriedade — o diferencial (ver abaixo)
jsonschema==4.*          # validar o schema da tree.json e do vcmr_preds.json
pytest-randomly==3.*     # randomiza ordem dos testes → detecta vazamento de estado entre testes
pytest-xdist==3.*        # paralelismo (opcional; -n auto)

# --- Track de exploração (scratch) ---
ipython==8.*             # `ipython -i scratch/x.py` — REPL com estado vivo
ipykernel==6.*           # kernel para células # %% no editor (opcional; modo notebook-em-.py)
matplotlib==3.*          # VER matrizes de similaridade e a curva de novidade de Foote
```

**Por que `hypothesis` é o pacote de nível mundial aqui.** Suas afirmações são frequentemente *invariantes*, não casos pontuais — e invariantes se testam melhor com propriedades sobre entradas geradas do que com um único exemplo: "min-max sempre produz saída em [0,1]"; "o denoiser nunca altera um frame de alta confiança"; "`Max_Mean ≤ Max_Max` sempre"; "toda matriz uniforme gera ≥2 segmentos". Um exemplo prova que funciona *num caso*; uma propriedade prova que vale *na classe* — e encolhe automaticamente o contraexemplo mínimo quando falha. É a diferença entre "testei" e "verifiquei".

**Por que `matplotlib` no scratch.** Confirmar visualmente que a convolução de Foote sobre uma matriz sintética *pica na fronteira certa* leva um segundo de olho — mais rápido e mais convincente, na fase exploratória, que decifrar asserções numéricas. A visualização é a moeda do scratch; a asserção é a moeda do pytest.

**Por que `pytest-randomly`.** A `CapTree` mantém estado global via *registry pattern* (decoradores no import) e sets. Ordem de teste importando estado é bug clássico; randomizar a ordem o expõe.

**Orquestração:** `Makefile` (sem dependência extra) em vez de `tox` — recriar um ambiente pesado a cada rodada é doloroso. `pre-commit` (opcional) para rodar T0 a cada commit.

---

## 4. Estrutura de diretórios (pronta para copiar)

Dois espaços paralelos: `tests/` (formal, coletado pelo pytest) e `scratch/` (flexível, **ignorado** pelo pytest e pelo git). Ambos fora do núcleo do repo.

```
RefCap/                          # o repositório clonado (núcleo — você preserva)
├── pipeline/ ...
├── utils/ ...
│
├── tests/                       # ← APARATO FORMAL (pytest)
│   ├── conftest.py              # fixtures compartilhadas, seeds, injeção de sys.path, mocks
│   ├── unit/                    # T0 — lógica pura, sem pesos
│   │   ├── test_qmgen_kernel.py         # kernel de Foote (comportamental)
│   │   ├── test_qmgen_boundaries.py     # seleção de fronteiras + sobre-segmentação
│   │   ├── test_minmax.py               # normalize_min_max (propriedade)
│   │   ├── test_denoiser_window.py      # SWi-Den causal + gate
│   │   ├── test_construct_flow.py       # construct() — teste de INTERAÇÃO (promovido do scratch)
│   │   ├── test_keyword_extraction.py   # get_nouns_verbs (spaCy leve)
│   │   ├── test_maxmean.py              # Max_Mean vs Max_Max (propriedade)
│   │   └── test_tree_schema.py          # schema da tree.json / nó
│   ├── integration/             # T1 — fluxo com pesos MOCKADOS
│   │   ├── test_corpus_coupling.py      # a ARMADILHA (compute_tree_feature)
│   │   ├── test_ts_inert.py             # ts inerte ao scoring
│   │   └── test_output_schema.py        # vcmr_preds.json bem-formado
│   ├── e2e/                     # T2 — modelos reais, micro-corpus (marcado @slow @gpu @e2e)
│   │   ├── test_pipeline_smoke.py
│   │   ├── test_surgery1_equivalence.py
│   │   └── test_captions_faithful.py
│   ├── fixtures/                # artefatos sintéticos pequenos (versionados)
│   │   ├── synthetic_tree.json
│   │   ├── synthetic_captions.jsonl
│   │   ├── schemas/{tree.schema.json, preds.schema.json}
│   │   └── generators.py                # geradores de sims/scores/keys sintéticos
│   └── data/micro_corpus/       # 5–10 vídeos SEUS (só T2; NÃO versionar) + .gitkeep
│
├── scratch/                     # ← TRACK FLEXÍVEL (exploração) — .gitignore + norecursedirs
│   ├── _bootstrap.py            # substrato compartilhado: sys.path, seeds, shim, bare(), geradores
│   ├── scratch_construct.py     # EXEMPLO (feito): construct() via dublês (teste de interação)
│   ├── scratch_denoise.py       # (próximo) denoise_caption via bare() (teste de valor)
│   └── ...                      # um por experimento; descartáveis
│
├── requirements-test.txt
├── pytest.ini
├── .coveragerc
├── Makefile
├── .gitignore                   # inclui scratch/ (menos _bootstrap.py, se quiser versioná-lo)
└── .pre-commit-config.yaml      # (opcional)
```

**Princípios:** (a) `tests/` e `scratch/` fora do núcleo → você não polui o código que preserva; (b) `scratch/` ignorado pelo git → experimentos são descartáveis (versione só `_bootstrap.py` se quiser); (c) `scratch/` ignorado pelo pytest (§5.1) → liberdade total lá dentro, sem coleta acidental; (d) `data/micro_corpus/` não versionado (vídeos são grandes).

---

## 5. Arquivos de configuração (prontos para copiar)

### 5.1 `pytest.ini` — marcadores, defaults, e exclusão do scratch

```ini
[pytest]
testpaths = tests
norecursedirs = scratch          # o pytest NUNCA coleta o scratch — liberdade total lá dentro
markers =
    slow: testes lentos (modelos reais) — desligados por padrão
    gpu: exige GPU
    e2e: pipeline ponta a ponta
addopts =
    -ra
    --strict-markers
    -m "not slow and not gpu and not e2e"   # o loop rápido roda só T0+T1 por padrão
filterwarnings =
    ignore::DeprecationWarning
```

Duas linhas fazem o trabalho pesado: `norecursedirs = scratch` blinda o formal do flexível (o pytest não tenta rodar seus scratchpads), e `-m "not slow..."` impõe a tiragem por padrão (as camadas pesadas só rodam quando pedidas).

### 5.2 `conftest.py` — o núcleo do isolamento do APARATO

Resolve a **armadilha de instanciação** e fornece entradas sintéticas. (O `_bootstrap.py` do scratch, §5.6, é o espelho *independente* disto.)

```python
import os, sys, random
from types import SimpleNamespace
import numpy as np
import pytest

# (1) RESOLUÇÃO DE IMPORT — o repo não é pip-instalável; injeta a raiz no sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# (2) DETERMINISMO GLOBAL
os.environ.setdefault("PYTHONHASHSEED", "0")   # afeta ordenação de set/dict (Keyword Set é set!)

@pytest.fixture(autouse=True)
def _seed_everything():
    random.seed(0); np.random.seed(0)
    try:
        import torch; torch.manual_seed(0)
    except ImportError:
        pass

# (3) CFG FALSO — SimpleNamespace com os NOMES REAIS dos parâmetros do RefCap
@pytest.fixture
def cfg():
    return SimpleNamespace(
        device="cpu",
        figsim_denoise_thr=0.4, denoise_window_width=2,          # SWi-Den
        prop_kernel_width=5, prop_score_thr=0.2, prop_min_cnt=2,  # QM-Gen
        prop_max_cnt=5, min_prop_size=3, prop_sim_type="it",
        retrieve_sent_ratio=0.5, key_policy="max_mean",           # Retrieval
        max_key_cnt_per_proposal=50,
    )

# (4) INSTANCIAÇÃO SEM CARREGAR PESOS — bypass de __init__ para métodos de lógica pura
@pytest.fixture
def denoiser(cfg):
    from pipeline.denoiser.window import WindowSimDenoiser
    obj = object.__new__(WindowSimDenoiser)   # NÃO chama __init__ → não carrega BLIP
    obj.cfg = cfg                              # injeta só o que denoise_caption usa
    return obj

# (5) ENTRADA SINTÉTICA (exemplo)
@pytest.fixture
def two_block_sim():
    """Matriz com duas metades distintas → fronteira conhecida no meio."""
    import torch
    n = 20; m = torch.zeros(n, n); m[:10, :10] = 1.0; m[10:, 10:] = 1.0
    return m
```

### 5.3 `.coveragerc` — cobertura honesta

```ini
[run]
source = pipeline,utils,dataset
omit =
    */genCaptions_minigpt.py   # script externo, não testável isoladamente
    */__init__.py

[report]
show_missing = True
skip_covered = False
```

### 5.4 `Makefile` — a orquestração (com alvo de scratch)

```makefile
.PHONY: test test-fast test-int test-e2e cov scratch

test-fast:            ## T0 — lógica pura, segundos
	pytest tests/unit -q

test-int:             ## T0 + T1
	pytest tests/unit tests/integration -q

test-e2e:             ## T2 — modelos reais (exige GPU + micro_corpus + ffmpeg)
	pytest tests/e2e -m "e2e" -q

test:                 ## loop padrão (rápido)
	pytest

cov:                  ## cobertura das camadas rápidas
	pytest tests/unit tests/integration --cov --cov-report=term-missing

scratch:              ## roda um scratchpad:  make scratch F=scratch/scratch_construct.py
	python $(F)
```

### 5.5 `.pre-commit-config.yaml` (opcional — trava a regressão no commit)

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest-fast
        name: pytest (T0)
        entry: pytest tests/unit -q
        language: system
        pass_filenames: false
        always_run: true
```

### 5.6 `scratch/_bootstrap.py` — o substrato de EXPLORAÇÃO (novo)

O substrato mínimo que resolve as duas fricções do RefCap de uma vez, para qualquer scratchpad importar. É **independente** do `conftest.py` (o scratch não depende do aparato), mas usa **as mesmas técnicas** — é isso que torna a promoção a teste um recorte, não uma reescrita. Inclui o *shim* de `torchtext` que provamos necessário.

```python
# scratch/_bootstrap.py — carregue no topo de um scratchpad:  from _bootstrap import *
# (ou embuta este bloco no próprio scratchpad, para torná-lo 100% autossuficiente)
import os, sys, random, types
import numpy as np

# (1) RESOLUÇÃO DE IMPORT (= source setup.sh): o repo não é pip-instalável
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# (2) DETERMINISMO
os.environ.setdefault("PYTHONHASHSEED", "0")
random.seed(0); np.random.seed(0)
try:
    import torch; torch.manual_seed(0)
except ImportError:
    pass

# (3) SHIM DE DEPENDÊNCIA FRÁGIL — torchtext quebra ao carregar com torch recente.
#     A maioria da lógica (construct, denoise, kernel) NÃO usa GloVe; então stubamos
#     torchtext em sys.modules para a cadeia de import resolver, sem instalar nada.
#     Inócuo se torchtext funcionar (o try passa).
try:
    from torchtext.vocab import Vectors  # noqa: F401
except Exception:
    _tt = types.ModuleType("torchtext"); _ttv = types.ModuleType("torchtext.vocab")
    _ttv.Vectors = object; _tt.vocab = _ttv
    sys.modules.setdefault("torchtext", _tt); sys.modules.setdefault("torchtext.vocab", _ttv)

# (4) BYPASS DE __init__ — instancia sem carregar pesos e injeta só os atributos usados
def bare(cls, **attrs):
    obj = object.__new__(cls)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj

# (5) CFG FALSO reutilizável
from types import SimpleNamespace
def make_cfg(**overrides):
    base = dict(device="cpu", figsim_denoise_thr=0.4, denoise_window_width=2,
                prop_kernel_width=5, prop_score_thr=0.2, prop_min_cnt=2, prop_max_cnt=5,
                min_prop_size=3, prop_sim_type="it", retrieve_sent_ratio=0.5,
                key_policy="max_mean", max_key_cnt_per_proposal=50)
    base.update(overrides); return SimpleNamespace(**base)

# (6) DUBLÊ (spy) para testar ORQUESTRADORES por interação
class Spy:
    def __init__(self, name, journal, return_value):
        self.name, self.journal, self.return_value = name, journal, return_value
    def __call__(self, *a, **kw):
        self.journal.append((self.name, kw)); return self.return_value

# (7) GERADORES SINTÉTICOS reutilizáveis (para testes de VALOR)
def two_block_sim(n=20):
    import torch
    m = torch.zeros(n, n); m[:n//2, :n//2] = 1.0; m[n//2:, n//2:] = 1.0; return m

# (8) visualização
import matplotlib.pyplot as plt
```

### 5.7 `.gitignore` — o scratch é descartável

```gitignore
# Scratch é exploração descartável — não versione (exceto o substrato, se quiser)
scratch/*
!scratch/_bootstrap.py

# Artefatos gerados pelo pipeline (não poluir o repo)
meta/
results/
tests/data/micro_corpus/*
!tests/data/micro_corpus/.gitkeep
```

---

## 6. O fluxo de scratch (exploração flexível)

### 6.1 A taxonomia que decide COMO testar cada trecho

Antes de escrever o scratchpad de um trecho, pergunte: **"este trecho COMPUTA UM VALOR ou COORDENA outras peças?"** — a resposta escolhe a técnica:

| Tipo de trecho | O que a "lógica" significa | Técnica de teste | Exemplo no RefCap |
|---|---|---|---|
| **Orquestrador** | A ordem e o fluxo de dados entre chamadas | **Dublês (spies)** — teste de *interação* | `construct()`; `__call__` dos pipelines |
| **Lógica pura** | Uma transformação entrada→saída | **Amostra sintética + `assert`** — teste de *valor* | kernel de Foote; min-max; `Max_Mean` |
| **Método c/ estado leve** | Transformação que usa `self.cfg` + poucos atributos | **`bare()` + amostra** — teste de *valor* | `denoise_caption` |

O erro de categoria a evitar: associar "abstrato/combinado" com "biblioteca robusta". Combinar trechos é *composição de código* (Python puro + `assert`); a robustez de biblioteca (`hypothesis`) só entra quando o **número de casos** explode, não quando a lógica é complexa.

### 6.2 As duas fricções, resolvidas pelo `_bootstrap.py`

Cutucar qualquer trecho do RefCap esbarra em duas fricções — o `_bootstrap.py` (§5.6) mata as duas:
1. **Resolução de import** — o repo não é instalável; precisa do `sys.path` (bootstrap item 1).
2. **Armadilha de instanciação** — as classes carregam modelos no `__init__`. *Confirmado no código:* `BaseConstructPipeline.__init__` (base.py:37) faz `os.listdir(video_root)`, lê `annos/` via `select_videos`, carrega o BLIP e cria diretórios — quatro razões independentes pelas quais instanciar normalmente é impossível. O `bare()` (bootstrap item 4) pula tudo isso.

### 6.3 A técnica do *shim* (lição confirmada ao vivo)

Ao montar o primeiro scratchpad, a cadeia de import cascateou até `torchtext`, que **falhou ao carregar** (não ao instalar) por incompatibilidade com o torch. Como `construct()` não usa GloVe, a solução não é instalar a dependência frágil — é **stubá-la** em `sys.modules` *antes* do import (bootstrap item 3). Princípio geral, transferível: **quando uma dependência transitiva frágil bloqueia o import mas o caminho sob teste não a usa, faça um shim — não a instale.** É o análogo, em nível de import, do "mocke o GloVe" da estratégia de camadas.

### 6.4 Exemplo trabalhado (feito e executado): `scratch_construct.py`

O primeiro scratchpad verifica a **lógica de `construct()`** — que é um orquestrador, logo um teste de *interação*. Ele importa `construct` do módulo real (não copia), instancia via `bare()` (sem BLIP), substitui os sete pontos de dependência por `Spy`s, roda o fluxo real, e verifica: (1) as 7 etapas rodaram na ordem correta (com `compute_capframe_scores` 2×); (2) o encadeamento de dados — em particular os dois pontos que auditamos: **scores recomputados sobre legendas *denoised*** (não brutas) e **segmentação recebendo scores recomputados**. Executou instantaneamente, sem carregar um modelo. Estrutura reutilizável: `_bootstrap` → dublês → montagem → execução → asserções.

### 6.5 A ponte: promoção scratch → pytest

Quando um scratchpad confirma uma lógica que vale travar, o recorte é mínimo: mova as asserções para `tests/`, embrulhe numa função `def test_...():`. Os helpers (`bare`, `Spy`, geradores) já existem em ambos os lados — no scratch via `_bootstrap.py`, no aparato via `conftest.py` (que espelha as mesmas técnicas). **Promoção é recorte, não reescrita.** É isso que faz exploração e regressão se reforçarem em vez de duplicarem esforço.

---

## 7. Estratégia de fixtures e mocks (a técnica que viabiliza o isolamento)

O gerador de entradas sintéticas (`tests/fixtures/generators.py` no aparato; itens 6–7 do `_bootstrap.py` no scratch) é o que substitui os modelos. Princípios:

- **Kernel de Foote:** matrizes com estrutura de bloco *conhecida* (duas/três metades), para que a fronteira verdadeira seja um valor calculado à mão — não uma reimplementação do algoritmo (armadilha da reimplementação, §10).
- **Denoiser:** `frame_captions` + `raw_scores` construídos para exercitar cada ramo (âncora alta seguida de baixa dentro/fora da janela; baixa *antes* de qualquer âncora).
- **Orquestradores:** dublês (`Spy`) que gravam chamadas/args, com marcadores rastreáveis por etapa.
- **`Max_Mean`:** keyword sets com similaridades controladas, resultado conhecido.
- **Modelos:** fakes *determinísticos* (hash→vetor), nunca aleatórios — senão o teste vira flaky.

---

## 8. Mapeamento afirmação → teste (operacionalizando seu objetivo)

Cada afirmação que auditamos vira um teste, na camada certa. A coluna "Explora primeiro?" indica se o scratch é o ponto de partida natural.

| Afirmação da análise | Camada | Explora 1º? | Asserção |
|---|---|:---:|---|
| `construct()`: ordem + encadeamento (scores denoised) | **T0** (interação) | sim (feito) | 7 etapas na ordem; segmentação recebe scores recomputados |
| Kernel de Foote detecta fronteiras | **T0** | sim | Pico de novidade em ~o índice da fronteira verdadeira |
| min-max descarta magnitude absoluta | **T0** (hypothesis) | sim | Escalar a matriz não muda as fronteiras (documenta o defeito) |
| SWi-Den propaga só para frente | **T0** | sim | Antes da âncora: inalterado; depois na janela: copiado |
| SWi-Den cruza fronteira real de cena | **T0** | sim | Substituição indevida ocorre (documenta o defeito) |
| Sobre-segmentação de vídeo uniforme | **T0** (hypothesis) | sim | Matriz uniforme → ≥2 segmentos sempre |
| `Max_Mean ≤ Max_Max` | **T0** (hypothesis) | sim | Invariante sempre válida |
| Nó da árvore tem {st,ed,cap,keys} | **T0** | não | `jsonschema.validate` passa |
| Corpus definido pelas consultas (a ARMADILHA) | **T1** | sim | Vídeo não referenciado → não buscável / `KeyError` |
| `ts` inerte ao scoring | **T1** | sim | `ts` dummy diferente → predições idênticas |
| `vcmr_preds.json` bem-formado | **T1** | não | Estrutura `[vid_id, st, ed, score, ...]` |
| Legendas fiéis ao seu domínio | **T2** | n/a | Não-vazias; inspeção qualitativa (diagnóstico de domínio) |
| Cirurgia 1: listagem ≡ manifesto | **T2** | não | `tree.json` idênticas |

**O padrão:** os *defeitos* que identificamos (min-max, cruzar fronteira, sobre-segmentação) viram **testes que documentam o comportamento** — asserções que passam confirmando que o defeito existe. A crítica vira conhecimento executável: se o comportamento mudar, o teste avisa.

---

## 9. Automação: como reunir tudo

O fluxo tem **três loops de velocidade/formalidade crescentes**:

```
LOOP 0 — EXPLORAÇÃO (durante a análise, informal)
  python scratch/x.py  /  ipython -i scratch/x.py  /  células # %%
  → "essa lógica anda?" — cutuca, visualiza, disseca. Descartável.
        │  [confirmou? vale travar?]  → PROMOVE (recorte para tests/)
        ▼
LOOP RÁPIDO (a cada save/commit, formal)
  make test-fast   → T0 (segundos, sem modelos)   [pre-commit opcional]
        │
        ▼
LOOP DE INTEGRAÇÃO (antes de push/PR)
  make test-int    → T0 + T1 (segundos, mocks)
        │
        ▼
LOOP PESADO (manual / noturno)
  make test-e2e    → T2 (minutos, modelos reais + GPU + micro_corpus)
```

- **Localmente:** o `Makefile` cobre tudo. `make scratch F=...` para explorar; `make test` no dia a dia; `make test-e2e` para validar o real.
- **CI (opcional):** rode **só T0+T1** (rápido, sem GPU, sem downloads); T2 como job manual/agendado num runner com GPU. **Nunca** faça o CI baixar GloVe/BLIP no loop rápido. O `scratch/` é ignorado pelo git, então nunca chega ao CI — correto.
- **Reunião final:** a "automação" é (a) `pytest.ini` impondo a tiragem + excluindo o scratch, (b) `Makefile` dando os alvos, (c) `pre-commit`/CI disparando o loop rápido. O scratch alimenta a suíte por *promoção*, não por execução automática.

---

## 10. Armadilhas e defeitos fatais (análise crítica implacável)

1. **A armadilha de instanciação.** Classes carregam modelos no `__init__`. Instanciar naivemente baixa gigabytes. *Solução:* `bare()`/monkeypatch. Confirmado no `construct()` (o `__init__` também toca disco e lê `annos/`).
2. **A armadilha da reimplementação (defeito fatal silencioso).** Testar reimplementando o algoritmo e comparando faz um bug *compartilhado* passar verde. *Solução:* verdade independente calculada à mão, ou testes *comportamentais* — nunca uma cópia da lógica.
3. **A armadilha do determinismo em T2.** MiniGPT `temperature=0.3`, não-determinismo de GPU, deriva de versão. *Solução:* asserte **propriedades** (legendas não-vazias, N proposals, timestamps monotônicos), não conteúdo exato.
4. **A armadilha do golden file obsoleto.** Snapshot da `tree.json` inteira quebra a cada troca de modelo. *Solução:* snapshot só do **schema**, não do conteúdo gerado.
5. **A ilusão de cobertura.** 100% ≠ correto. *Solução:* priorize asserções significativas na lógica-núcleo.
6. **Efeitos colaterais de import + cadeia de import (confirmado ao vivo).** O *registry pattern* roda decoradores no import, o `PYTHONPATH` precisa estar setado, **e a cadeia inteira de bibliotecas precisa resolver só para importar**. *Solução:* injeção de `sys.path` + shim para dependências frágeis (§6.3).
7. **Poluição do repositório.** O pipeline escreve em `meta/`, `results/`. *Solução:* `tmp_path` para saídas de T2; `.gitignore` para os diretórios gerados.
8. **Vazamento de estado entre testes.** Sets/dicts globais + ordenação por hash. *Solução:* `PYTHONHASHSEED=0` + `pytest-randomly`.
9. **`torchtext`/GloVe frágil (confirmado ao vivo).** Instala mas não carrega com torch recente. *Solução:* shim em `sys.modules`; isole GloVe atrás de T2.
10. **[Scratch] Excesso de shim.** Stubar demais pode mascarar que o caminho sob teste *de fato* usa a dependência. *Solução:* só shime dependências que o trecho comprovadamente não exercita; se a lógica toca GloVe, teste-a em T2, não com shim.
11. **[Scratch] Divergência do modo "colar".** Colar um trecho no scratchpad (em vez de importar) cria uma *cópia* que diverge do original quando este muda. *Solução:* prefira **importar** (Modo A); use o colar (Modo B) só para dissecar lógica entrelaçada, e nunca como regressão.

---

## 11. Respostas comuns, porém incorretas

1. **"Basta `pip install pytest` e testar o pipeline."** *Errado:* baixa gigabytes, exige GPU, cada teste leva minutos. A tiragem (T0 sem modelos) é o que viabiliza.
2. **"Mocke tudo para ficar rápido."** *Errado:* se você mocka a lógica sob teste, não testa nada. Mocke só os *pesos*; teste a *lógica* com entradas sintéticas.
3. **"100% de cobertura significa verificado."** *Errado:* cobertura ≠ correção. Linha exercitada sem asserção não prova nada.
4. **"Teste as saídas do BLIP/MiniGPT com igualdade exata."** *Errado:* não-determinístico. Teste propriedades.
5. **"Testar reimplementando o algoritmo e comparando."** *Errado:* bug compartilhado passa (a mais perigosa). Verdade independente.
6. **"Um ambiente por camada (T0/T1/T2)."** *Errado:* as cadeias de import puxam tudo; um só ambiente. A tiragem é imposta pelos testes.
7. **"Para testar combinação de trechos preciso de framework robusto."** *Errado (erro de eixo):* combinar trechos é composição de código (Python puro + `assert`); robustez de biblioteca responde a "quantos casos e com que garantia?", não a "quão complexa a lógica?".
8. **"Scratch e pytest são coisas concorrentes; escolha um."** *Errado:* são pontos de um espectro que compartilham substrato; o scratch alimenta o pytest por promoção. Usar os dois é o fluxo correto.
9. **"Importar o módulo já carrega os modelos."** *Errado (distinção-chave):* importar exige as *bibliotecas*, não carrega os *pesos*. Os pesos só carregam no `__init__`/uso — que você evita com `bare()`/mock.

---

## 12. O que falta para excelência (informações a fornecer)

Para afinar este setup ao seu caso concreto:
- **Seu SO** (Ubuntu/macOS/Windows): muda os comandos de `ffmpeg`/conda e a viabilidade de `torchtext`.
- **Você tem GPU?** Se não, T2 roda em CPU (lento, mas possível para micro-corpus).
- **Gerenciador de ambiente** (conda/venv/`uv`): o repo assume conda; ajusto os comandos se preferir outro.
- **Editor** (VSCode/PyCharm/outro): define se as células `# %%` são viáveis para o scratch visual, ou se ficamos em `ipython -i`.
- **Você vai modificar o código-fonte do RefCap?** Se sim, "refatorar para funções puras" simplifica muito o T0. Se não, ficamos com bypass/monkeypatch/dublês.
- **CI ou só local?** Define se preparo um workflow do GitHub Actions (T0+T1) ou só o `Makefile`.

---

*Próximo passo natural:* materializar o `scratch/_bootstrap.py` como arquivo real (o `scratch_construct.py` já existe e roda) e um segundo scratchpad-exemplo do tipo *valor* — `scratch_denoise.py`, sobre `denoise_caption` com `bare()` — para você ter os dois moldes (interação e valor) lado a lado. A partir daí, cada afirmação da §8 vira um scratchpad durante a análise e, quando confirmada, um teste promovido em `tests/`.*