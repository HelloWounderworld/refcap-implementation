# Reaproveitar os Modelos Carregados no Processo do Construct
## As Mudanças Mínimas Necessárias e Suficientes

---

> **O que é este documento.** A resposta precisa a: *o que exatamente precisa mudar para o `construct` usar os modelos que a API já carregou?*
>
> **A resposta curta.** **Uma única mudança é necessária e suficiente** para o reaproveitamento em si: extrair `build(cfg, pretrained_models=None)` do `main()` do `construct.py`. Todas as outras mudanças que fizemos servem a propósitos **diferentes** — e este documento separa uma coisa da outra, porque confundi-las leva a mexer mais do que o preciso.
>
> **Verificado.** Instrumentei o `load_pretrained_models` para explodir se fosse chamado, e provei que `build(cfg, modelos)` percorre toda a cadeia sem tocá-lo. E provei por identidade (`is`) que os componentes recebem **os mesmos objetos** que estão na GPU.

---

## Protocolo

| Marca | Significa |
|---|---|
| **[L]** | Lido no código — arquivo e linha |
| **[V]** | Verificado por execução nesta sessão |
| **[J]** | Julgamento de engenharia |

---

# PARTE 1 — Onde o construct carrega modelos

**[L] Rastreei todo o caminho** por `from_pretrained`, `SentenceTransformer(`, `Vectors(`, `spacy.load`. Há **dois** pontos:

| # | onde | o quê | quando roda |
|---|---|---|---|
| **1** | `utils/model_utils.py:12,30,35,36` | BLIP-cap, BLIP-ITM, SBERT, GloVe | uma vez, em `construct.py:42` |
| **2** | `QMPropGener.py:25` e `WholePropGener.py` | **spaCy** | **a cada** chamada de `build()` |

**[J] O ponto 2 é sutil e fácil de perder:** o `__init__` do propgenerator roda **dentro** do `build()`. Num serviço, isso significa `spacy.load()` a cada requisição.

**[L] E o GloVe é carregado sem ser usado:** único consumidor é `capTree.py:23`; o `CapTree` só é instanciado em `retrieve.py:269`; o `constructpipe/base.py:3` o importa mas **nunca instancia**.

---

# PARTE 2 — A mudança necessária e suficiente

## 2.1 O que é

**[L] O ponto exato:** `construct.py:42`, dentro de `main()`:
```python
pretrained_models = load_pretrained_models(cfg)
```

**[J] Por que não dá para injetar sem mexer:** o `main()` original não tem parâmetro, não tem retorno, e a chamada está no meio do corpo. **Não existe ponto de injeção.** As alternativas seriam:

| alternativa | por que é pior |
|---|---|
| *monkey-patch* de `load_pretrained_models` | frágil e implícito — quem lê o `construct.py` não vê que foi substituído |
| reimplementar as linhas 42–49 no serviço | **duplica o código** — é exatamente o "trabalho dobrado" que você quer evitar |

## 2.2 A mudança

```python
def build(cfg, pretrained_models=None):
    """O núcleo reutilizável: recebe cfg pronto e, opcionalmente, modelos já carregados."""
    seed_it(cfg.seed)
    cfg.exp_dir = os.path.join(cfg.res_dir, cfg.construct_dir, cfg.collection, cfg.construct_name)
    os.makedirs(cfg.exp_dir, exist_ok=True)
    basic_utils.save_json(asdict(cfg), os.path.join(cfg.exp_dir, "settings.json"))

    if pretrained_models is None:                 # ← o CLI cai aqui
        pretrained_models = load_pretrained_models(cfg)

    caption_generator  = get_capgen_class(cfg.caption_generator)(cfg, pretrained_models)
    caption_denoiser   = get_denoiser_class(cfg.caption_denoiser)(cfg, pretrained_models)
    proposal_generator = get_propgen_class(cfg.proposal_generator)(cfg, pretrained_models)
    construct_pipeline = get_constructpipe_class(cfg.construct_pipeline)(
        cfg, caption_generator, caption_denoiser, proposal_generator, pretrained_models)

    return construct_pipeline.construct()          # ← agora RETORNA


def main():
    print("Building parse pipeline")
    parser = HfArgumentParser(BuildArguments)
    cfg = parser.parse_args_into_dataclasses(look_for_args_file=False)[0]
    print(cfg)
    build(cfg)                                     # ← delega
    print(cfg.construct_name)
    print("DONE!")
```

**É um *Extract Function* puro.** Nenhuma linha de lógica muda de ordem ou de efeito.

## 2.3 Por que é SUFICIENTE

**[V] Prova por instrumentação.** Substituí `load_pretrained_models` por uma função que levanta `AssertionError`, e chamei `build(cfg, MODELOS)`:

```
Chamando build(cfg, MODELOS) ...
parou adiante em: FileNotFoundError: '/tmp/prova/videos'   ← chegou ao os.listdir

load_pretrained_models foi chamado?  NÃO ✓
```

A execução avançou até o `os.listdir(video_root)` — ou seja, **passou por todas as instanciações** (capgen, denoiser, propgen, pipeline) sem tocar no carregador.

**[V] Prova por identidade.** Os componentes recebem os **mesmos objetos**, não cópias:
```
BlipCapGener.cap_model      é o MESMO objeto?  True
WindowDenoiser.it_sim_model é o MESMO objeto?  True
WholePropGen.txt_sim_model  é o MESMO objeto?  True
```

## 2.4 Por que é NECESSÁRIA

**[V] Testei reverter cada outra mudança**, mantendo só o `build()`: o reaproveitamento continua funcionando. E sem o `build()`, não há ponto de injeção (§2.1).

**Portanto: uma mudança, num arquivo, e o reaproveitamento está completo.**

---

# PARTE 3 — O contrato do dicionário de modelos

Para o `build(cfg, modelos)` funcionar, o dicionário precisa ter as chaves que os componentes consultam.

**[L] O que cada componente exige:**

| componente | chaves | etapas atendidas |
|---|---|---|
| `BlipCapGener` | `cap_gen_model`, `cap_gen_processor` | 1 |
| `BaseDenoiser` / `WindowDenoiser` | `blip_itrtv_model`, `blip_itrtv_processor` | 4 |
| `BaseConstructPipeline` | `blip_itrtv_model`, `blip_itrtv_processor` | 2, 3, 5 |
| `WholePropGenerator` | `blip_itrtv_*`, `sentence_transformer` | 6 |

**[J] Consequência prática:** **três** modelos são obrigatórios. Carregar só o de captioning faz o `build()` quebrar com `KeyError: 'blip_itrtv_model'` na criação do denoiser — **antes** de processar qualquer coisa.

**O GloVe não é exigido por ninguém no construct.** Pode ir como `None`. Manter a chave presente evita `KeyError` se algum código fizer `.get()`.

---

# PARTE 4 — As mudanças complementares (e o que cada uma compra)

**[J] Nenhuma destas é necessária para o reaproveitamento.** Cada uma resolve um problema distinto — e vale saber qual, para você decidir se aplica.

## 4.1 `os.environ.setdefault` no `construct.py` (linhas 2–3)

```python
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")   # era: os.environ[...] = '0'
```

**Compra:** que o `environment=` do supervisord seja respeitado. **[V] Sem isto**, importar o `construct.py` força a GPU 0 independentemente da configuração.

**[V] Não afeta o CLI:** sem nada definido no ambiente, o resultado é `'0'` — idêntico ao anterior.

**Precisa se:** você usa supervisord e quer controlar a GPU por configuração. **[J] No seu caso, sim.**

## 4.2 spaCy pré-carregado no `WholePropGener.py` (1 linha)

```python
self.nlp = models.get("spacy_nlp") or spacy.load("en_core_web_sm")
```

**Compra:** elimina o `spacy.load()` **a cada requisição** (Parte 1, ponto 2).

**[V] Os três cenários testados:**

| cenário | resultado |
|---|---|
| com `spacy_nlp` no dict | reaproveita; `spacy.load` **não** é chamado |
| sem a chave (o CLI) | carrega como antes — **compatibilidade preservada** |
| `QMPropGenerator` recebendo a chave extra | **ignora e não quebra** |

**Precisa se:** o serviço vai processar muitas requisições. **[J] É otimização, não correção** — sem ela tudo funciona, só desperdiça.

## 4.3 As mudanças que são de OUTRA funcionalidade

**[J] Estas não têm relação com reaproveitar modelos.** Elas fazem o `WholePropGenerator` existir e o pipeline não quebrar:

| mudança | para quê |
|---|---|
| `WholePropGener.py` (o arquivo) | o segmento único + ranking |
| linha no `propgenerator/__init__.py` | registrar `"whole"` |
| `"whole"` nos `choices` do `cfg.py` | o parser aceitar |
| `max(1, int(duration))` no `viddataset.py` | vídeos < 1 s não derrubarem |

Você já as aplicou e estão validadas por 48 testes.

---

# PARTE 5 — O que NÃO precisa mudar

**[J]** Vale listar, porque a tentação de mexer é grande:

| não mexer em | por quê |
|---|---|
| `utils/model_utils.py` | continua servindo o CLI; a API simplesmente não o chama |
| `pipeline/capgenerator/*` | já recebe os modelos pelo dicionário |
| `pipeline/denoiser/*` | idem |
| `pipeline/constructpipe/base.py` | idem |
| `QMPropGener.py` | intocado; ignora a chave extra |
| `retrieve.py` | fora do escopo da API |

**[J] E não reimplemente as etapas do construct no serviço.** O `build()` já orquestra as sete. Reescrevê-las seria o trabalho dobrado que você quer evitar — e perderia o cache incremental, o tratamento de erro e as suas implementações.

---

# PARTE 6 — Como fica o fluxo completo

```
STARTUP (uma vez)
    ModelosResidentes.carregar()
        ├── BLIP-cap        → GPU
        ├── BLIP-ITM        → GPU
        ├── sentence-transf → GPU
        └── spaCy           → RAM
    (GloVe NÃO é carregado)

POST /jobs  →  processar_job(job)
    │
    ├── [seu pipeline: tratar requisição, annos, decidir collection]
    │
    ├── cfg = montar_cfg(...)                    # sem sys.argv, caminhos absolutos
    │
    └── build(cfg, modelos.como_dict())          # ★ o ponto de reaproveitamento
            │
            ├── if pretrained_models is None:  ← NÃO entra (recebeu o dict)
            │
            ├── 1. captioning        usa cap_gen_model      (residente)
            ├── 2. frame features    usa blip_itrtv_model   (residente)
            ├── 3. capframe scores   usa blip_itrtv_model   (residente)
            ├── 4. denoising         usa blip_itrtv_model   (residente)
            ├── 5. scores denoised   usa blip_itrtv_model   (residente)
            ├── 6. propostas+ranking usa sentence_transf + spaCy (residentes)
            └── 7. árvore            (sem modelo)
            │
            └── return tree_meta                 # a resposta da API
```

**[J] O ponto central:** a linha `if pretrained_models is None` é o **único** lugar onde o reaproveitamento acontece. Todo o resto do RefCap funciona sem saber que os modelos vieram de fora — porque eles chegam pelo mesmo dicionário de sempre.

---

# PARTE 7 — Checklist

| # | mudança | arquivo | necessária p/ reaproveitar? |
|---|---|---|---|
| 1 | extrair `build(cfg, pretrained_models=None)` | `construct.py` | **★ SIM — a única** |
| 2 | dicionário com as 3 chaves obrigatórias | (no serviço) | **★ SIM** |
| 3 | `os.environ.setdefault` | `construct.py` | não — é para o supervisord |
| 4 | spaCy pré-carregado | `WholePropGener.py` | não — é otimização |
| 5 | `WholePropGener.py` + registro + `choices` | RefCap | não — é a funcionalidade do ranking |
| 6 | `max(1, int(duration))` | `viddataset.py` | não — é robustez |

**[J] Se você só quisesse reaproveitar os modelos**, aplicaria 1 e 2 e pararia. As demais você já aplicou por outros motivos, e todas estão validadas.

---

# PARTE 8 — O que ainda falta

**[J]** Para o processo rodar de ponta a ponta pela API:

1. **Preencher o bloco marcado** em `processar_job` — tratar a requisição, conferir/atualizar annos, decidir `collection`.
2. **A decisão de isolamento** — `collection` por job, adiada. Sem ela, requisições com vídeos de mesmo nome-base reutilizam o cache e **pulam** o processamento.
3. **Validar com um vídeo real** — nada foi processado de verdade; as provas usaram objetos falsos para verificar o *fluxo*, não o resultado do captioning.

---

*A resposta à pergunta é enxuta: **uma** mudança no `construct.py` — extrair `build(cfg, pretrained_models=None)` — é necessária e suficiente para reaproveitar os modelos. Verifiquei por instrumentação (o carregador não é chamado) e por identidade (os componentes recebem os mesmos objetos da GPU). As demais mudanças que fizemos servem a propósitos distintos — supervisord, otimização do spaCy, a funcionalidade do ranking, robustez — e este documento as separa para que você saiba exatamente o que cada uma compra.*
