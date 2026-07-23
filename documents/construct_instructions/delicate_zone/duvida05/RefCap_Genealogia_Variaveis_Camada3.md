# A Genealogia das Variáveis até a Camada 3
## Quem é Quem quando o Fluxo Chega em `BaseCapGen.__call__`

---

> **O que é este documento.** O rastreamento completo de **cada variável** em jogo quando a execução chega na Camada 3 (`capgenerator/base.py:39-48`): de onde ela veio, que objeto ela carrega, e quais nomes diferentes apontam para o **mesmo** objeto. É a resposta à pergunta "quais as equivalências que cada variável carrega".
>
> **A tese central.** Na Camada 3 há **sete atributos em `self`** e **três variáveis locais**, mas eles representam menos objetos do que parece — porque vários nomes, em escopos diferentes, apontam para o mesmo objeto. Entender esse mapa de aliases é o que revela três perigos reais, todos verificados em execução (`LAB6_aliasing_camada3.py`).

---

# PARTE 1 — A cadeia de funções até a Camada 3

Antes das variáveis, a sequência exata do que foi executado.

## 1.1 Fase de preparação (`construct.py:29-40`)

| # | Chamada | O que produz |
|---|---|---|
| 1 | `HfArgumentParser(BuildArguments)` | o parser |
| 2 | `parser.parse_args_into_dataclasses(...)[0]` | **`cfg`** — a dataclass com todos os parâmetros |
| 3 | `seed_it(cfg.seed)` | fixa as sementes aleatórias |
| 4 | `os.path.join(...)` + `cfg.exp_dir = exp_dir` | **muta o `cfg`** (ver Perigo 1) |
| 5 | `os.makedirs(exp_dir)` | cria o diretório do experimento |
| 6 | `asdict(cfg)` + `save_json(...)` | grava `settings.json` |

## 1.2 Fase de composição (`construct.py:42-47`)

| # | Chamada | O que produz |
|---|---|---|
| 7 | `load_pretrained_models(cfg)` | **`pretrained_models`** — dict com 6 chaves |
| 8 | `get_capgen_class("blip")` | a **classe** `CapGeneratorBLIP` |
| 9 | `CapGeneratorBLIP(cfg, pretrained_models)` | → `__init__` → `super().__init__()` → **`load_jsonl`** se houver cache |
| 10 | `get_denoiser_class(...)(...)` | o denoiser |
| 11 | `get_propgen_class(...)(...)` | o propgen (**carrega o spaCy**) |
| 12 | `get_constructpipe_class(...)(...)` | → `__init__` → `os.listdir` → **`select_videos`** (pode rodar ffmpeg) → `create_dirs` |

## 1.3 Fase de execução — a entrada na Camada 3

```
construct.py:49         construct_pipeline.construct()
constructpipe/base.py:69    captions = self.caption_generator(vid_list=self.vid_list)
capgenerator/base.py:39         ★ CAMADA 3 — BaseCapGen.__call__
capgenerator/base.py:47             self.generate_caption(...)  → despacha p/ BlipCapGener:17
```

**Portanto:** ao entrar na Camada 3, já rodaram **12 chamadas de preparação**, quatro modelos estão na GPU, o spaCy está carregado, o cache de legendas foi lido do disco, e a lista de vídeos já foi filtrada.

---

# PARTE 2 — A tabela de equivalências (o mapa de aliases)

Este é o coração da sua pergunta. **Cada linha é UM objeto com vários nomes.**

| Objeto | Nome no `main()` | Nome como parâmetro | Nome como atributo | Nome na Camada 3 |
|---|---|---|---|---|
| **A dataclass de config** | `cfg` | `cfg` (em todo `__init__`) | `self.cfg` (em **todos** os colaboradores *e* no pipeline) | `self.cfg` |
| **O dict de modelos** | `pretrained_models` | `models` | `self.models` (só no `BaseCapGen`) | `self.models` |
| **A instância do gerador** | `caption_generator` | `caption_generator` (no `__init__` do pipeline) | `self.caption_generator` (no pipeline) | **`self`** |
| **A lista de vídeos** | — | `vid_list` (param do `__call__`) | `self.vid_list` (no pipeline) | `vid_list` |
| **A lista de legendas** | — | — | `self.captions` (no gerador) | `self.captions` → **devolvida** |
| **O modelo BLIP-caption** | `pretrained_models['cap_gen_model']` | `models['cap_gen_model']` | `self.cap_model` | `self.cap_model` |

**A equivalência mais importante de entender:** a instância criada na linha 43 do `construct.py` tem **quatro nomes** ao longo do fluxo — `caption_generator` (local do `main`), `caption_generator` (parâmetro do construtor do pipeline), `self.caption_generator` (atributo do pipeline) e, finalmente, **`self`** dentro do `__call__`. São quatro rótulos, **um objeto**.

Isso responde diretamente à frase que gerou a dúvida: *"`self.caption_generator` é a instância de `CapGeneratorBLIP`"* — sim, e `self` dentro da Camada 3 **é essa mesma instância**, vista de dentro.

---

# PARTE 3 — O estado de `self` na Camada 3

Quando o `__call__` executa, `self` carrega **sete atributos**, criados em dois construtores encadeados:

## 3.1 Vindos de `BaseCapGen.__init__` (base.py:27-37)

| Atributo | Conteúdo | Origem |
|---|---|---|
| `self.cfg` | a dataclass inteira | passada do `main()` — **objeto compartilhado** |
| `self.models` | o dict com os 6 modelos | passado do `main()` — **objeto compartilhado** |
| `self.captions_save_file` | `meta/captions/{collection}_{caption_generator}.jsonl` | **derivado** de 3 campos do `cfg` |
| `self.captions` | `[]` ou o conteúdo do `.jsonl` | **lido do disco** se o arquivo existir |
| `self.already_video_names` | `set()` ou os nomes já processados | **derivado** de `self.captions` |

## 3.2 Vindos de `CapGeneratorBLIP.__init__` (BlipCapGener.py:12-15)

| Atributo | Conteúdo | Origem |
|---|---|---|
| `self.cap_model` | o `BlipForConditionalGeneration` | `models['cap_gen_model']` — **mesmo objeto do dict** |
| `self.cap_processor` | o `BlipProcessor` | `models['cap_gen_processor']` — **idem** |

**Observação sobre a redundância:** `self.models` guarda o dict inteiro, *e* `self.cap_model` guarda um item dele. Ou seja, `self.cap_model is self.models['cap_gen_model']` — mesmo objeto, dois caminhos de acesso. Não é erro, mas é a mesma inconsistência de estilo que encontramos no pipeline (que tem `self.it_sim_model` e usa `self.caption_denoiser.it_sim_model`).

---

# PARTE 4 — As variáveis locais do `__call__`

```python
def __call__(self, vid_list):                              # ← 1 parâmetro
    for vid in tqdm(vid_list, total=len(vid_list)):        # ← vid
        video_name = vid.split('.')[0]                     # ← video_name
        video_path = os.path.join(self.cfg.video_root, vid)# ← video_path
        if not os.path.isfile(video_path): continue
        self.generate_caption(video_name=..., video_path=...)
    return self.captions
```

| Variável | Tipo | Exemplo | Como é derivada |
|---|---|---|---|
| `vid_list` | `list[str]` | `["clipA.mp4", "clipB.mp4"]` | **é** `pipeline.self.vid_list` (mesmo objeto) |
| `vid` | `str` | `"clipA.mp4"` | item da iteração — **nome com extensão** |
| `video_name` | `str` | `"clipA"` | `vid.split('.')[0]` — **sem extensão**, é a chave do sistema todo |
| `video_path` | `str` | `"/videos/clipA.mp4"` | `video_root` + `vid` |

**A distinção que mais confunde:** `vid` tem extensão, `video_name` não. O `video_name` é a **chave canônica** — ele indexa `frame_captions`, `already_video_names`, `all_scores`, `all_frame_features` e o `tree_meta`. Toda a identidade dos vídeos no sistema é o nome-base. (E é por isso que nomes-base duplicados com extensões diferentes quebrariam tudo.)

---

# PARTE 5 — De onde vem `vid_list` (a cadeia de filtragem)

O `vid_list` que chega na Camada 3 **não** é a lista de arquivos do diretório. Ele passou por três transformações no `__init__` do pipeline (`constructpipe/base.py:43-49`):

```
os.listdir(cfg.video_root)          →  TODOS os arquivos do diretório
        ↓ select_videos(...)
filtrado pelo annos/{collection}/vcmr.jsonl  →  só os que estão nas anotações
        ↓ (dentro de select_videos) conversão .mkv → .mp4 via ffmpeg
        ↓ cfg.num_samples
truncado, se num_samples != -1      →  self.vid_list
```

**Consequência prática para você:** um vídeo seu que não esteja no `vcmr.jsonl` **é descartado em silêncio** — nunca chega na Camada 3, nunca é legendado, e não há aviso. É exatamente por isso que o `make_annos.py` existe.

---

# PARTE 6 — O que sai da Camada 3

```python
return self.captions        # base.py:48
```

**Não é uma cópia.** É a **referência** à lista interna do gerador. Provado (LAB6, Prova A):
```
captions is gen.captions  ->  True
```

Portanto, em `constructpipe/base.py:69`, a variável local `captions` **é** `self.captions` do gerador. E é essa mesma lista que segue para as seis etapas seguintes.

---

# PARTE 7 — Os três perigos de aliasing (verificados)

O mapa de equivalências não é curiosidade acadêmica: ele revela três armadilhas reais.

## Perigo 1 — `cfg.exp_dir` não existe na dataclass

`construct.py:36` faz `cfg.exp_dir = exp_dir`. Mas **`exp_dir` não está declarado em `BuildArguments`** (verifiquei o `cfg.py` inteiro). É um campo **injetado dinamicamente** — possível porque dataclasses comuns não são `frozen` nem usam `__slots__`.

**E quatro módulos dependem dele:**
```
propgenerator/QMPropGener.py:63,64    self.cfg.exp_dir
constructpipe/base.py:82,181          self.cfg.exp_dir
denoiser/base.py:32                   self.cfg.exp_dir
```

**Consequência direta para você:** se você construir `BuildArguments()` no seu próprio script (num adapter, num teste) e passar ao pipeline **sem** setar `exp_dir`, quebra com `AttributeError` — num módulo que nada tem a ver com o seu código. Provado no LAB6, Prova C.

**O que isso é, conceitualmente:** uma **dependência implícita não declarada**. O contrato real do `cfg` é maior que a sua definição — o mesmo padrão de defeito da Lei de Deméter que encontramos no pipeline.

## Perigo 2 — o denoiser destrói as legendas cruas na memória

`denoiser/window.py:34` faz `meta['frame_captions'][fid] = copy.deepcopy(...)` — **muta o dicionário no lugar**, e `return meta` (linha 35) devolve o **mesmo objeto**. Não há cópia defensiva do `meta`.

Como `captions` **é** `self.captions` do gerador (Parte 6), a cadeia é:

```
captions  ─┬─► compute_frame_features      (lê)
           ├─► compute_capframe_scores     (lê → scores CRUS)
           └─► caption_denoiser  ─── MUTA OS DICTS NO LUGAR ───► denoised_captions
                                              ↑
                       `captions` e `denoised_captions` são ALIASES
                       dos MESMOS dicionários, agora modificados
```

Provado (LAB6, Prova B): `denoised[0] is captions[0] is gen.captions[0]` → `True`.

**As consequências:**
1. As legendas **cruas deixam de existir em memória** — foram sobrescritas.
2. O estado interno do gerador (`self.captions`) fica **contaminado** com dados denoised.
3. A distinção "cru vs. denoised" existe apenas nos **objetos-lista**, não no conteúdo.

**Por que ainda funciona:** os scores crus foram calculados **antes** da mutação. É correção por **ordem de execução**, não por design — qualquer reordenação das etapas quebraria silenciosamente.

**A correção seria trivial:** `meta = copy.deepcopy(meta)` no início de `denoise_caption`.

## Perigo 3 — `cfg` e `models` são compartilhados por todos

Um único objeto `cfg` e um único dict `models` são passados por referência a **todos** os colaboradores e ao pipeline. Nenhum faz cópia.

**O lado bom:** os modelos pesados (BLIP, sentence-transformer) **não são duplicados** — o BLIP-ITM é o mesmo objeto no denoiser, no propgen e no pipeline. É o comportamento desejado.

**O lado ruim:** qualquer mutação em `cfg` por qualquer colaborador seria visível para todos os outros, instantaneamente, sem rastro. Hoje ninguém muta (exceto o `main()`), mas nada impede.

---

# PARTE 8 — O diagrama de linhagem

```
construct.py:30   cfg ──────────────────────────────────────────┐
                   │ (linha 36: cfg.exp_dir injetado)           │  MESMO objeto
                   ├──────────────┬──────────────┬──────────────┤  em 5 lugares
                   ▼              ▼              ▼              ▼
construct.py:42   load_pretrained_models(cfg) ──► pretrained_models {6 modelos}
                                                         │
                   ┌─────────────────────────────────────┤  MESMO dict
                   ▼                                     ▼
construct.py:43   CapGeneratorBLIP(cfg, models)     [denoiser, propgen, pipeline]
                   │  __init__ ─► super().__init__ ─► load_jsonl(cache)
                   │              └► self.cfg, self.models, self.captions,
                   │                 self.already_video_names, self.captions_save_file
                   │  __init__ ─► self.cap_model, self.cap_processor
                   ▼
              caption_generator ────────────────┐
                                                 │ (passado ao construtor)
construct.py:47   BaseConstructPipeline(...) ◄───┘
                   │  __init__ ─► os.listdir ─► select_videos ─► self.vid_list
                   │              └► self.caption_generator = caption_generator
                   ▼
construct.py:49   .construct()
constructpipe:69      self.caption_generator(vid_list=self.vid_list)
                              │                        │
                              ▼                        ▼
capgenerator/base.py:39   ★ CAMADA 3:  self ≡ caption_generator
                                        vid_list ≡ pipeline.self.vid_list
                          for vid → video_name, video_path
                          self.generate_caption(...) ──► BlipCapGener:17 (despacho)
                          return self.captions ──► a MESMA lista, por referência
```

---

# PARTE 9 — Resumo executivo

**Quantos objetos distintos estão em jogo na Camada 3?** Menos do que os dez nomes sugerem:
- **1** dataclass `cfg` (com 5 nomes apontando para ela)
- **1** dict `models` (com 4 nomes)
- **1** instância do gerador (com 4 nomes, incluindo `self`)
- **1** lista `vid_list` (com 2 nomes)
- **1** lista `captions` (que sairá por referência)
- **2** modelos BLIP (extraídos do dict)

**Quais funções já rodaram?** Doze chamadas de preparação, incluindo três com efeito colateral pesado (`load_pretrained_models`, `load_jsonl`, `select_videos` com possível ffmpeg).

**O que a Camada 3 realmente faz?** Muito pouco: itera, deriva dois nomes (`video_name`, `video_path`), valida a existência do arquivo, e **delega**. Todo o trabalho real está no `generate_caption` da subclasse (Camada 4). O `__call__` é puro *Template Method* — esqueleto e delegação.

**A lição de aliasing:** em Python, passar um objeto é passar uma **referência**. Nesta cadeia, isso é **desejável** para os modelos (evita duplicar gigabytes) e **perigoso** para as legendas (o denoiser destrói o original). A diferença entre os dois casos é se alguém **muta** o objeto compartilhado.

---

*Este relatório rastreou cada variável em jogo na Camada 3 — as sete de `self`, as três locais e a de entrada — mapeando quais nomes apontam para o mesmo objeto. As três provas de aliasing (`LAB6_aliasing_camada3.py`) revelaram: (1) `cfg.exp_dir` é um campo não declarado, injetado pelo `main()` e exigido por quatro módulos; (2) o denoiser muta os dicionários de legenda no lugar, destruindo as versões cruas em memória e contaminando o estado interno do gerador; (3) `cfg` e `models` são compartilhados por referência entre todos os colaboradores. Os três decorrem do mesmo fato — em Python, nomes distintos podem apontar para o mesmo objeto — e o mapa de equivalências da Parte 2 é o que torna esses riscos visíveis.*
