# RefCap — Infraestrutura de Testes: Setup, Isolamento e Automação
## Como verificar cada afirmação da análise com testes isolados e automatizáveis

---

> **O que é este documento.** O playbook para montar um ambiente de testes que permite **confirmar cada afirmação da sua análise** do RefCap de forma isolada, rápida e determinística — e depois reuni-las numa suíte automatizada. Cobre: o princípio de arquitetura, o ambiente, os pacotes, a estrutura de diretórios, os arquivos de configuração (prontos para copiar), a estratégia de fixtures/mocks, o mapeamento afirmação→teste, a orquestração da automação, e as armadilhas fatais.
>
> **Postura.** Não é "instale pytest e teste o pipeline" — isso é a armadilha nº 1 (baixa a suíte a downloads de gigabytes e dependência de GPU). O valor está na *arquitetura* que separa o que é testável em milissegundos do que exige modelos reais.

---

## 0. Reformulação: a pergunta certa e o princípio central

Você perguntou "quais pacotes/diretórios/configurações instalar". A pergunta de maior impacto é: **"que arquitetura de testes me deixa verificar as afirmações de *lógica* rápido, sem carregar BLIP/MiniGPT/GloVe, mas ainda me permite rodar verificações pesadas de ponta a ponta quando necessário?"**

O princípio central deriva de dois fatos do repositório (verificados no código):

1. **O RefCap tem um perfil de dependências pesado** (torch, transformers, sentence-transformers, spaCy, torchtext) e depende de pesos externos volumosos (BLIP, MiniGPT, GloVe 300d ~1GB) e de GPU para operação realista. Testar "a coisa real" a cada asserção é inviável.
2. **A maioria das suas afirmações de análise é sobre *lógica pura*** — o kernel de Foote é checkerboard ±1, a normalização min-max descarta a magnitude absoluta, o denoiser propaga só para frente, o corpus é definido pelas consultas. **Nenhuma delas requer um modelo carregado.** Elas requerem *entradas sintéticas* (matrizes de similaridade falsas, legendas falsas, scores falsos) e a *lógica* do módulo.

**A distinção que organiza tudo — biblioteca instalada ≠ peso carregado.** Confirmado no código: importar `pipeline/denoiser/window.py` puxa `dataset.viddataset` → `ffmpeg_python`, e `WindowSimDenoiser.__init__` carrega `models["blip_itrtv_model"]`. Mas `denoise_caption` usa **apenas** `self.cfg` — nunca o BLIP. Logo: você precisa das *bibliotecas* instaladas para **importar** o módulo, mas pode **evitar carregar os pesos** ao testar a lógica (via bypass de `__init__` ou monkeypatch). Esta é a chave técnica de todo o setup.

**A realização que destrava tudo:** ~80% da sua verificação acontece numa camada rápida, sem modelos, com entradas sintéticas. Só a fidelidade das legendas ao seu domínio exige modelos reais — e essa é qualitativa, roda raramente.

---

## 1. A arquitetura de testes em três camadas

A tiragem é imposta por **se o teste carrega pesos de modelo**, não por qual biblioteca está instalada (todas estão, para satisfazer imports).

| Camada | O que testa | Carrega pesos? | GPU? | Velocidade | Quando roda | Exemplos de afirmação |
|---|---|:---:|:---:|---|---|---|
| **T0 — Lógica pura** | Algoritmos com entradas sintéticas | **Não** | Não | ms | A cada save/commit | Kernel de Foote; min-max; denoiser causal; sobre-segmentação; `Max_Mean`; extração de keywords; achatamento da árvore; schema da `tree.json` |
| **T1 — Integração com mocks** | Fluxo entre componentes, pesos *falsos* determinísticos | Não (mocked) | Não | s | Antes de push / PR | A armadilha de acoplamento do corpus; `ts` inerte ao scoring; wiring construção↔recuperação |
| **T2 — Ponta a ponta real** | Pipeline completo, micro-corpus, modelos reais | **Sim** | Sim | min | Manual / noturno | Legendas fiéis ao domínio; `tree.json` gerada; predições saem; equivalência da Cirurgia 1 |

**Por que esta tiragem é correta:** o loop de desenvolvimento (T0) precisa ser instantâneo para você iterar sobre a análise sem atrito; o custo pesado (T2) fica isolado atrás de marcadores, rodando quando você de fato quer validar o sistema real. Misturar as duas — a armadilha nº 1 — mata a produtividade.

---

## 2. Ambiente (isolamento e reprodutibilidade)

### 2.1 Estratégia de ambiente

**Um único ambiente de teste, isolado do restante.** Como as cadeias de import puxam tudo, o ambiente de teste precisa conter as bibliotecas do `requirements.txt` (para importar os módulos) **mais** o ferramental de teste. A tiragem T0/T1/T2 é imposta pelos *testes* (mock/bypass), não por sub-ambientes.

```bash
# Reproduza o ambiente do repo (conda, como o repo especifica), NUNCA no env de produção
conda create -n refcap-test python=3.10 -y
conda activate refcap-test

# Bibliotecas do repo (necessárias para IMPORTAR os módulos-alvo)
pip install -r requirements.txt
python -m spacy download en_core_web_sm     # ~12MB, determinístico → OK para T0

# Ferramental de teste (ver §3)
pip install -r requirements-test.txt

# Binário de sistema — SÓ para T2 (testes de vídeo real)
# Ubuntu: sudo apt-get install ffmpeg   |   macOS: brew install ffmpeg
```

### 2.2 Reprodutibilidade (obrigatória para testes determinísticos)

- **Fixe versões** — o `requirements.txt` já pina; mantenha assim. Deriva de versão de modelo/lib quebra golden files silenciosamente.
- **Semeie tudo** no `conftest.py` (§5): `torch.manual_seed`, `numpy.random.seed`, `random.seed`, e `PYTHONHASHSEED=0` (afeta ordenação de sets/dicts — relevante para o *Indexing Keyword Set*, que é um `set`).
- **Force CPU no T0/T1** (`cfg.device='cpu'`) para eliminar não-determinismo de GPU.

### 2.3 Riscos de instalação (avisos concretos)

- **`torchtext==0.17.0`** (usado para GloVe) está em depreciação e é frágil de casar com `torch 2.2`. Se a instalação falhar, isole o carregamento de GloVe atrás de T2 e faça mock no T0/T1 (você não precisa de GloVe para testar lógica).
- **Rede**: `pip` puxa de `pypi.org`/`files.pythonhosted.org`; downloads de modelo (spaCy, HuggingFace) vêm de outras origens. Em ambiente restrito, pré-baixe os pesos para T2.

---

## 3. Pacotes (com justificativa — nada de lista genérica)

`requirements-test.txt` (pronto para copiar):

```
pytest==8.*              # runner central
pytest-cov==5.*          # cobertura — saber o que está EXERCITADO (≠ verificado; ver §9)
pytest-mock==3.*         # wrapper ergonômico sobre unittest.mock (fixture `mocker`)
hypothesis==6.*          # testes baseados em propriedade — o diferencial (ver abaixo)
jsonschema==4.*          # validar o schema da tree.json e do vcmr_preds.json
pytest-randomly==3.*     # randomiza ordem dos testes → detecta vazamento de estado entre testes
pytest-xdist==3.*        # paralelismo (opcional; -n auto)
```

**Por que `hypothesis` é o pacote de nível mundial aqui.** Suas afirmações são frequentemente *invariantes*, não casos pontuais — e invariantes se testam melhor com propriedades sobre entradas geradas do que com um único exemplo:
- "min-max sempre produz saída em [0,1]" → propriedade sobre matrizes aleatórias.
- "o denoiser nunca altera um frame de alta confiança" → propriedade sobre scores aleatórios.
- "`Max_Mean ≤ Max_Max` sempre" → propriedade sobre keyword sets aleatórios.
- "sobre-segmentação: toda matriz uniforme gera ≥2 segmentos" → propriedade.

Um teste de exemplo prova que funciona *num caso*; uma propriedade prova que vale *na classe* — e ainda encolhe automaticamente o contraexemplo mínimo quando falha. É a diferença entre "testei" e "verifiquei".

**Por que `pytest-randomly`.** A `tree.json`/`CapTree` mantêm estado global via *registry pattern* (decoradores no import) e sets. Ordem de teste importando estado é um bug clássico; randomizar a ordem o expõe.

**Orquestração:** `Makefile` (sem dependência extra) em vez de `tox` — porque `tox` recria ambientes, e recriar um ambiente pesado a cada rodada é doloroso. `pre-commit` (opcional) para rodar T0 a cada commit.

---

## 4. Estrutura de diretórios (pronta para copiar)

Mantenha os testes **fora do núcleo do repo**, espelhando a estrutura dos módulos, com a tiragem explícita e uma pasta de artefatos sintéticos.

```
RefCap/                          # o repositório clonado (núcleo — você preserva)
├── pipeline/ ...
├── utils/ ...
│
├── tests/                       # ← SUA infraestrutura de testes
│   ├── conftest.py              # fixtures compartilhadas, seeds, injeção de sys.path, mocks de modelo
│   │
│   ├── unit/                    # T0 — lógica pura, sem pesos
│   │   ├── test_qmgen_kernel.py         # kernel de Foote (comportamental)
│   │   ├── test_qmgen_boundaries.py     # seleção de fronteiras + sobre-segmentação
│   │   ├── test_minmax.py               # normalize_min_max (propriedade)
│   │   ├── test_denoiser_window.py      # SWi-Den causal + gate
│   │   ├── test_keyword_extraction.py   # get_nouns_verbs (spaCy leve)
│   │   ├── test_maxmean.py              # Max_Mean vs Max_Max (propriedade)
│   │   └── test_tree_schema.py          # schema da tree.json / nó
│   │
│   ├── integration/             # T1 — fluxo com pesos MOCKADOS
│   │   ├── test_corpus_coupling.py      # a ARMADILHA (compute_tree_feature)
│   │   ├── test_ts_inert.py             # ts inerte ao scoring
│   │   └── test_output_schema.py        # vcmr_preds.json bem-formado
│   │
│   ├── e2e/                     # T2 — modelos reais, micro-corpus (marcado @slow @gpu)
│   │   ├── test_pipeline_smoke.py       # roda ponta a ponta; tree.json existe; predições saem
│   │   ├── test_surgery1_equivalence.py # listagem de diretório ≡ manifesto
│   │   └── test_captions_faithful.py    # qualitativo/estrutural (legendas não-vazias/fiéis)
│   │
│   ├── fixtures/                # artefatos sintéticos pequenos (versionados)
│   │   ├── synthetic_tree.json          # tree.json mínima feita à mão
│   │   ├── synthetic_captions.jsonl     # legendas por frame falsas
│   │   ├── schemas/                     # JSON Schemas (tree, preds)
│   │   │   ├── tree.schema.json
│   │   │   └── preds.schema.json
│   │   └── generators.py                # funções que geram sims/scores/keys sintéticos
│   │
│   └── data/
│       └── micro_corpus/        # 5–10 vídeos SEUS (só para T2; NÃO versionar vídeos grandes)
│           └── .gitkeep
│
├── requirements-test.txt
├── pytest.ini                   # (ou [tool.pytest.ini_options] em pyproject.toml)
├── .coveragerc
├── Makefile
└── .pre-commit-config.yaml      # (opcional)
```

**Princípios de diretório:** (a) testes fora do núcleo → você não polui o código que preserva; (b) espelhar a estrutura dos módulos → rastreabilidade teste↔código; (c) `fixtures/` versionado com artefatos *minúsculos* → determinismo; (d) `data/micro_corpus/` **não** versionado (vídeos são grandes) → use `.gitkeep` + `.gitignore`.

---

## 5. Arquivos de configuração (prontos para copiar)

### 5.1 `pytest.ini` — marcadores e defaults

```ini
[pytest]
testpaths = tests
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

O `addopts` com `-m "not slow..."` é o coração da tiragem: **por padrão, `pytest` roda só as camadas rápidas**; as pesadas só quando você as pede explicitamente (`-m e2e`).

### 5.2 `conftest.py` — o núcleo do isolamento

Este arquivo resolve a **armadilha de instanciação** (classes carregam modelos no `__init__`) e fornece as entradas sintéticas.

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
        # SWi-Den
        figsim_denoise_thr=0.4,
        denoise_window_width=2,
        # QM-Gen
        prop_kernel_width=5,
        prop_score_thr=0.2,
        prop_min_cnt=2,
        prop_max_cnt=5,
        min_prop_size=3,
        prop_sim_type="it",
        # Retrieval
        retrieve_sent_ratio=0.5,
        key_policy="max_mean",
        max_key_cnt_per_proposal=50,
    )

# (4) INSTANCIAÇÃO SEM CARREGAR PESOS — bypass de __init__ para métodos de lógica pura
@pytest.fixture
def denoiser(cfg):
    from pipeline.denoiser.window import WindowSimDenoiser
    obj = object.__new__(WindowSimDenoiser)   # NÃO chama __init__ → não carrega BLIP
    obj.cfg = cfg                              # injeta só o que denoise_caption usa
    return obj

# (5) ENTRADAS SINTÉTICAS (delegadas a fixtures/generators.py)
@pytest.fixture
def two_block_sim():
    """Matriz de similaridade com duas metades claramente distintas → fronteira conhecida no meio."""
    import torch
    n = 20
    m = torch.zeros(n, n)
    m[:10, :10] = 1.0      # bloco A
    m[10:, 10:] = 1.0      # bloco B
    return m               # a fronteira verdadeira está em ~10

# (6) MOCK DE MODELO (para T1 — pesos falsos determinísticos)
@pytest.fixture
def fake_sentence_encoder(monkeypatch):
    """Substitui o SentenceTransformer por um encoder determinístico (hash → vetor)."""
    import numpy as np
    def _encode(texts, **kw):
        return np.stack([np.full(8, (hash(t) % 100) / 100.0) for t in texts])
    monkeypatch.setattr("sentence_transformers.SentenceTransformer.encode", _encode, raising=False)
```

**Nota sobre a armadilha de instanciação — três estratégias, e quando usar cada uma:**
- **Bypass de `__init__` (`object.__new__`)** — mostrado acima para o denoiser. Ideal quando o método sob teste usa poucos atributos (`self.cfg`). *Sem alterar o código-fonte.* Preferida para T0.
- **Monkeypatch dos carregadores** — substitui `SentenceTransformer`/BLIP/`spacy.load`/GloVe por fakes antes de instanciar normalmente. Use quando o método precisa de muitos atributos ou quando você quer exercitar o `__init__`. *Sem alterar o fonte.* Preferida para T1.
- **Refatorar para funções puras** — extrair a lógica (ex.: a construção do kernel + convolução) para uma função sem imports pesados. *Altera o fonte, mas melhora a testabilidade permanentemente.* Opcional; recomendada se você for manter o fork.

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

### 5.4 `Makefile` — a orquestração da automação

```makefile
.PHONY: test test-fast test-int test-e2e cov

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

---

## 6. Estratégia de fixtures e mocks (a técnica que viabiliza o isolamento)

O gerador de entradas sintéticas (`tests/fixtures/generators.py`) é o que substitui os modelos. Princípios:

- **Para o kernel de Foote:** matrizes com estrutura de bloco *conhecida* (duas ou três metades), para que a fronteira verdadeira seja um valor que você calculou à mão — não uma reimplementação do algoritmo (ver a armadilha da reimplementação em §9).
- **Para o denoiser:** dicionários `frame_captions` + tensores `raw_scores` construídos para exercitar cada ramo (âncora alta seguida de baixa dentro/fora da janela; baixa *antes* de qualquer âncora).
- **Para `Max_Mean`:** conjuntos de keywords com similaridades controladas, onde você conhece o resultado esperado.
- **Para modelos:** fakes *determinísticos* (hash→vetor), nunca aleatórios — senão o teste vira flaky.

---

## 7. Mapeamento afirmação → teste (operacionalizando seu objetivo)

Esta é a ponte entre a sua análise e a suíte. Cada afirmação que auditamos vira um teste, na camada certa:

| Afirmação da análise | Camada | Abordagem de teste | Asserção |
|---|---|---|---|
| Kernel de Foote detecta fronteiras | **T0** | Alimentar `two_block_sim` → rodar a detecção | Pico de novidade em ~o índice da fronteira verdadeira |
| min-max descarta magnitude absoluta | **T0** (hypothesis) | Escalar a matriz por constante c>0 | Fronteiras idênticas (documenta o defeito) |
| SWi-Den propaga só para frente | **T0** | Score baixo *antes* de âncora vs *depois* na janela | Antes: inalterado; depois: legenda copiada da âncora |
| SWi-Den pode cruzar fronteira real de cena | **T0** | Âncora + frame baixo na fronteira | Substituição indevida ocorre (documenta o defeito) |
| Sobre-segmentação de vídeo uniforme | **T0** (hypothesis) | Matriz uniforme | ≥2 segmentos sempre (documenta o defeito) |
| `Max_Mean ≤ Max_Max` | **T0** (hypothesis) | Keyword sets aleatórios | Invariante sempre válida |
| Nó da árvore tem {st,ed,cap,keys} | **T0** | Validar `synthetic_tree.json` contra schema | `jsonschema.validate` passa |
| Corpus definido pelas consultas (a ARMADILHA) | **T1** | Árvore com vídeo X; dataset sem X em `vid_name_to_id` | X **não** é buscável / `KeyError` — prova o acoplamento |
| `ts` inerte ao scoring | **T1** | Mesma query com `ts` dummy diferente | Predições idênticas |
| `vcmr_preds.json` bem-formado | **T1** | Validar saída contra schema | Estrutura `[vid_id, st, ed, score, ...]` |
| Legendas fiéis ao seu domínio | **T2** | BLIP real no micro-corpus | Não-vazias; inspeção qualitativa (o diagnóstico de domínio) |
| Cirurgia 1: listagem ≡ manifesto | **T2** | Construir com os dois caminhos | `tree.json` idênticas |

**Repare no padrão:** os *defeitos* que identificamos (min-max, cruzar fronteira, sobre-segmentação) viram **testes que documentam o comportamento** — asserções que passam confirmando que o defeito existe. Isso transforma a crítica em conhecimento executável: se um dia o comportamento mudar, o teste avisa.

---

## 8. Automação: como reunir tudo

O fluxo de automação tem **dois loops de velocidades diferentes**:

```
LOOP RÁPIDO (a cada save/commit)
  make test-fast   → T0 (segundos, sem modelos)
  [pre-commit hook opcional trava regressão]
        │
        ▼
LOOP DE INTEGRAÇÃO (antes de push/PR)
  make test-int    → T0 + T1 (segundos, mocks)
        │
        ▼
LOOP PESADO (manual / noturno)
  make test-e2e    → T2 (minutos, modelos reais + GPU + micro_corpus)
```

- **Localmente:** o `Makefile` é suficiente. `make test` no dia a dia; `make test-e2e` quando quiser validar o sistema real.
- **CI (opcional):** se usar GitHub Actions, rode **só T0+T1** no CI (rápido, sem GPU, sem downloads); deixe T2 como job manual/agendado num runner com GPU. **Nunca** faça o CI baixar GloVe/BLIP no loop rápido — é a armadilha nº 1 na esteira.
- **Reunião final:** a suíte inteira é `pytest` com marcadores; a "automação" é a combinação de (a) `pytest.ini` impondo a tiragem por padrão, (b) `Makefile` dando os alvos, (c) `pre-commit`/CI disparando o loop rápido automaticamente.

---

## 9. Armadilhas e defeitos fatais (análise crítica implacável)

1. **A armadilha de instanciação.** Classes carregam modelos no `__init__` (`WindowSimDenoiser` carrega BLIP; `QMPropGenerator` carrega spaCy+SentenceTransformer). Instanciar naivemente num teste unitário baixa gigabytes. *Solução:* bypass de `__init__` ou monkeypatch (§5.2). **Se você ignorar isto, "teste unitário" vira "teste de integração pesado" sem perceber.**
2. **A armadilha da reimplementação (defeito fatal silencioso).** Se você testa reimplementando o algoritmo no teste e comparando com o módulo, um bug *compartilhado* passa despercebido — o teste dá verde sobre código errado. *Solução:* teste contra **verdade independente** — valores esperados calculados à mão para entradas minúsculas, ou testes *comportamentais* (a fronteira aparece onde eu sei que deveria), nunca uma cópia da lógica.
3. **A armadilha do determinismo em T2.** MiniGPT usa `temperature=0.3`; GPU tem não-determinismo; versões de modelo derivam. Asserções de igualdade exata sobre saídas de modelo são **flaky por construção**. *Solução:* em T2, asserte **propriedades** (legendas não-vazias, N proposals gerados, timestamps monotônicos), não conteúdo exato. Se usar golden files, tolere ou capture só a *estrutura*.
4. **A armadilha do golden file obsoleto.** Snapshot da `tree.json` inteira quebra a cada troca de modelo/versão. *Solução:* snapshot só do **schema/estrutura** (via `jsonschema`) ou de saídas de *lógica pura*, nunca de conteúdo gerado por modelo.
5. **A ilusão de cobertura.** 100% de cobertura ≠ correto. Cobertura diz o que foi *exercitado*, não o que foi *verificado*. *Solução:* não persiga 100%; priorize asserções significativas sobre a lógica-núcleo (T0).
6. **Efeitos colaterais de import.** O *registry pattern* roda decoradores no import, e o `PYTHONPATH` precisa estar setado. *Solução:* a injeção de `sys.path` no `conftest` (§5.2) resolve; sem ela, `import pipeline...` falha.
7. **Poluição do repositório.** O pipeline escreve em `meta/`, `results/`. Testes que rodam o real podem sujar o repo. *Solução:* use `tmp_path` (fixture do pytest) para todas as saídas de T2; nunca escreva em caminhos do repo.
8. **Vazamento de estado entre testes.** Sets/dicts globais + ordenação dependente de hash. *Solução:* `PYTHONHASHSEED=0` + `pytest-randomly` para detectar dependência de ordem.
9. **`torchtext`/GloVe frágil.** Pode nem instalar com torch 2.2. *Solução:* isole GloVe atrás de T2 e faça mock no T0/T1 — você não precisa dele para lógica.

---

## 10. Respostas comuns, porém incorretas

1. **"Basta `pip install pytest` e testar o pipeline."** *Errado:* baixa gigabytes de pesos, exige GPU, cada teste leva minutos — o loop de desenvolvimento morre. A tiragem (T0 sem modelos) é o que torna a verificação viável.
2. **"Mocke tudo para ficar rápido."** *Errado:* se você mocka a lógica sob teste, não testa nada real. Mocke só os *pesos* (fronteira de I/O de modelo); teste a *lógica* de verdade com entradas sintéticas.
3. **"100% de cobertura significa verificado."** *Errado:* cobertura ≠ correção (armadilha 5). Uma linha exercitada sem asserção significativa não prova nada.
4. **"Snapshot da `tree.json` como golden garante regressão."** *Errado:* quebra a cada deriva de modelo (armadilha 4). Snapshot o *schema*, não o conteúdo gerado.
5. **"Teste as saídas do BLIP/MiniGPT com igualdade exata."** *Errado:* não-determinístico (armadilha 3). Teste propriedades.
6. **"Testar reimplementando o algoritmo e comparando."** *Errado:* bug compartilhado passa (armadilha 2, a mais perigosa). Use verdade independente calculada à mão.
7. **"Um ambiente por camada (T0/T1/T2)."** *Errado:* as cadeias de import puxam tudo; você precisa das bibliotecas em um só ambiente. A tiragem é imposta pelos *testes* (mock/bypass), não por sub-ambientes.

---

## 11. O que falta para excelência (informações a fornecer)

Para eu afinar este setup ao seu caso concreto:
- **Seu SO** (Ubuntu/macOS/Windows): muda os comandos de `ffmpeg`/conda e a viabilidade de `torchtext`.
- **Você tem GPU?** Se não, T2 roda em CPU (lento, mas possível para micro-corpus) — e isso muda o quanto você depende de mocks.
- **Gerenciador de ambiente** (conda/venv/`uv`): o repo assume conda; se você preferir `uv`/`venv`, ajusto os comandos.
- **Você vai modificar o código-fonte do RefCap?** Se sim, a estratégia "refatorar para funções puras" (§5.2) passa a ser a preferida e simplifica muito o T0. Se não, ficamos com bypass/monkeypatch.
- **CI ou só local?** Define se preparo um workflow do GitHub Actions (T0+T1) ou só o `Makefile`.

---

*Próximo passo natural:* com o seu sinal, eu materializo este scaffold como arquivos reais (o `conftest.py` completo, os `pytest.ini`/`Makefile`/schemas, e 3–4 testes-semente já mapeados às afirmações da §7), prontos para você colar na pasta `tests/` e rodar `make test-fast`. A partir daí, cada afirmação que você for verificando na análise vira um teste novo na camada correta.*
